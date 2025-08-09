from __future__ import annotations

from typing import Any, Callable

from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services.account import (
    get_internal_transactions,
    get_normal_transactions,
)
from aiochainscan.services.logs import get_logs
from aiochainscan.services.paging_engine import (
    FetchSpec,
    ResolveEndBlock,
    ProviderPolicy,
    fetch_all_generic,
    resolve_policy_for_provider,
)


def _to_int(value: Any) -> int:
    try:
        if isinstance(value, str):
            s = value.strip()
            if s.startswith('0x'):
                return int(s, 16)
            return int(s)
        return int(value)
    except Exception:
        return 0


def _resolve_end_block_factory(
    *,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    rate_limiter: RateLimiter | None,
    retry: RetryPolicy | None,
) -> ResolveEndBlock:
    async def _resolve() -> int:
        endpoint = endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
        url: str = endpoint.api_url
        params_proxy: dict[str, Any] = {'module': 'proxy', 'action': 'eth_blockNumber'}
        signed_params, headers = endpoint.filter_and_sign(params_proxy, headers=None)

        async def _do() -> Any:
            if rate_limiter is not None:
                await rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.blockNumber')
            return await http.get(url, params=signed_params, headers=headers)

        response: Any = await (retry.run(_do) if retry is not None else _do())
        latest_hex = response.get('result') if isinstance(response, dict) else None
        return int(latest_hex, 16) if isinstance(latest_hex, str) and latest_hex.startswith('0x') else int(latest_hex)  # type: ignore[arg-type]

    return _resolve


async def fetch_all_transactions_basic(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    max_offset: int = 10_000,
) -> list[dict[str, Any]]:
    """Provider-agnostic paged fetch. Deduplicated and stably sorted."""

    async def _fetch_page(*, page: int, start_block: int, end_block: int, offset: int) -> list[dict[str, Any]]:
        return await get_normal_transactions(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort='asc',
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint_builder,
            _rate_limiter=None,
            _retry=None,
            _telemetry=telemetry,
        )

    spec = FetchSpec(
        name='account.txs',
        fetch_page=_fetch_page,
        key_fn=lambda it: it.get('hash') if isinstance(it.get('hash'), str) else None,
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex'))),
        max_offset=max_offset,
        resolve_end_block=_resolve_end_block_factory(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            endpoint_builder=endpoint_builder,
            rate_limiter=rate_limiter,
            retry=retry,
        ),
    )
    policy = ProviderPolicy(mode='paged', prefetch=1, window_cap=None, rps_key=f'{api_kind}:{network}:paging')
    return await fetch_all_generic(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=1,
    )


async def fetch_all_transactions_fast(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    max_offset: int = 10_000,
    max_concurrent: int = 8,
) -> list[dict[str, Any]]:
    """Provider-aware fast fetch using the generic paging engine."""

    async def _fetch_page(*, page: int, start_block: int, end_block: int, offset: int) -> list[dict[str, Any]]:
        # For sliding mode, the engine will keep page=1; for paged, engine supplies page numbers
        return await get_normal_transactions(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort='asc',
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint_builder,
            _rate_limiter=None,
            _retry=None,
            _telemetry=telemetry,
        )

    spec = FetchSpec(
        name='account.txs',
        fetch_page=_fetch_page,
        key_fn=lambda it: it.get('hash') if isinstance(it.get('hash'), str) else None,
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex'))),
        max_offset=max_offset,
        resolve_end_block=_resolve_end_block_factory(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            endpoint_builder=endpoint_builder,
            rate_limiter=rate_limiter,
            retry=retry,
        ),
    )
    policy = resolve_policy_for_provider(api_kind=api_kind, network=network, max_concurrent=max_concurrent)
    return await fetch_all_generic(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=max_concurrent,
    )


async def fetch_all_internal_basic(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    max_offset: int = 10_000,
) -> list[dict[str, Any]]:
    """Provider-agnostic paged fetch for internal transactions."""

    async def _fetch_page(*, page: int, start_block: int, end_block: int, offset: int) -> list[dict[str, Any]]:
        return await get_internal_transactions(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort='asc',
            page=page,
            offset=offset,
            txhash=None,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint_builder,
            _rate_limiter=None,
            _retry=None,
            _telemetry=telemetry,
        )

    spec = FetchSpec(
        name='account.internal',
        fetch_page=_fetch_page,
        key_fn=lambda it: it.get('hash') if isinstance(it.get('hash'), str) else None,
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex'))),
        max_offset=max_offset,
        resolve_end_block=_resolve_end_block_factory(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            endpoint_builder=endpoint_builder,
            rate_limiter=rate_limiter,
            retry=retry,
        ),
    )
    policy = ProviderPolicy(mode='paged', prefetch=1, window_cap=None, rps_key=f'{api_kind}:{network}:paging')
    return await fetch_all_generic(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=1,
    )


async def fetch_all_internal_fast(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    max_offset: int = 10_000,
    max_concurrent: int = 8,
) -> list[dict[str, Any]]:
    """Provider-aware fast fetch for internal transactions using the generic engine."""

    async def _fetch_page(*, page: int, start_block: int, end_block: int, offset: int) -> list[dict[str, Any]]:
        return await get_internal_transactions(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort='asc',
            page=page,
            offset=offset,
            txhash=None,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint_builder,
            _rate_limiter=None,
            _retry=None,
            _telemetry=telemetry,
        )

    spec = FetchSpec(
        name='account.internal',
        fetch_page=_fetch_page,
        key_fn=lambda it: it.get('hash') if isinstance(it.get('hash'), str) else None,
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex'))),
        max_offset=max_offset,
        resolve_end_block=_resolve_end_block_factory(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            endpoint_builder=endpoint_builder,
            rate_limiter=rate_limiter,
            retry=retry,
        ),
    )
    policy = resolve_policy_for_provider(api_kind=api_kind, network=network, max_concurrent=max_concurrent)
    return await fetch_all_generic(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=max_concurrent,
    )


async def fetch_all_logs_basic(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    max_offset: int = 1000,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Provider-agnostic paged fetch for logs."""

    topics = topics or None
    topic_operators = topic_operators or None

    async def _fetch_page(*, page: int, start_block: int, end_block: int, offset: int) -> list[dict[str, Any]]:
        return await get_logs(
            start_block=start_block or 0,
            end_block=end_block or 99_999_999,
            address=address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint_builder,
            topics=topics,
            topic_operators=topic_operators,
            page=page,
            offset=offset,
            _rate_limiter=None,
            _retry=None,
            _telemetry=telemetry,
        )

    spec = FetchSpec(
        name='logs',
        fetch_page=_fetch_page,
        key_fn=lambda it: (
            f"{it.get('transactionHash') or it.get('hash')}:{it.get('logIndex')}"
            if isinstance(it.get('transactionHash') or it.get('hash'), str)
            and isinstance(it.get('logIndex'), (str, int))
            else None
        ),
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('logIndex'))),
        max_offset=max_offset,
        resolve_end_block=_resolve_end_block_factory(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            endpoint_builder=endpoint_builder,
            rate_limiter=rate_limiter,
            retry=retry,
        ),
    )
    policy = ProviderPolicy(mode='paged', prefetch=1, window_cap=None, rps_key=f'{api_kind}:{network}:paging')
    return await fetch_all_generic(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=1,
    )


async def fetch_all_logs_fast(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    max_offset: int = 1000,
    max_concurrent: int = 6,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Provider-aware fast fetch for logs using the generic engine."""

    topics = topics or None
    topic_operators = topic_operators or None

    async def _fetch_page(*, page: int, start_block: int, end_block: int, offset: int) -> list[dict[str, Any]]:
        return await get_logs(
            start_block=start_block,
            end_block=end_block,
            address=address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint_builder,
            topics=topics,
            topic_operators=topic_operators,
            page=page,
            offset=offset,
            _rate_limiter=None,
            _retry=None,
            _telemetry=telemetry,
        )

    spec = FetchSpec(
        name='logs',
        fetch_page=_fetch_page,
        key_fn=lambda it: (
            f"{it.get('transactionHash') or it.get('hash')}:{it.get('logIndex')}"
            if isinstance(it.get('transactionHash') or it.get('hash'), str)
            and isinstance(it.get('logIndex'), (str, int))
            else None
        ),
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('logIndex'))),
        max_offset=max_offset,
        resolve_end_block=_resolve_end_block_factory(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            endpoint_builder=endpoint_builder,
            rate_limiter=rate_limiter,
            retry=retry,
        ),
    )
    policy = resolve_policy_for_provider(api_kind=api_kind, network=network, max_concurrent=max_concurrent)
    return await fetch_all_generic(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=max_concurrent,
    )

