from __future__ import annotations

from typing import Any

from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services.account import (
    get_internal_transactions,
    get_normal_transactions,
    get_token_transfers,
)
from aiochainscan.services.logs import get_logs
from aiochainscan.services.paging_engine import (
    FetchSpec,
    ProviderPolicy,
    ResolveEndBlock,
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
        if isinstance(latest_hex, str):
            if latest_hex.startswith('0x'):
                return int(latest_hex, 16)
            if latest_hex.isdigit():
                return int(latest_hex)
        return 99_999_999

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

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
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
        resolve_end_block=(
            None
            if (isinstance(api_kind, str) and api_kind.startswith('blockscout_'))
            else _resolve_end_block_factory(
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                endpoint_builder=endpoint_builder,
                rate_limiter=rate_limiter,
                retry=retry,
            )
        ),
    )
    policy = ProviderPolicy(
        mode='paged', prefetch=1, window_cap=None, rps_key=f'{api_kind}:{network}:paging'
    )
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

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
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
        resolve_end_block=(
            None
            if (isinstance(api_kind, str) and api_kind.startswith('blockscout_'))
            else _resolve_end_block_factory(
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                endpoint_builder=endpoint_builder,
                rate_limiter=rate_limiter,
                retry=retry,
            )
        ),
    )
    policy = resolve_policy_for_provider(
        api_kind=api_kind, network=network, max_concurrent=max_concurrent
    )
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

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
        # Some Blockscout endpoints time out with very large offsets; adaptively reduce
        current_offset = int(offset)
        attempts_left = 3
        while True:
            try:
                return await get_internal_transactions(
                    address=address,
                    start_block=start_block,
                    end_block=end_block,
                    sort='asc',
                    page=page,
                    offset=current_offset,
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
            except Exception as exc:  # noqa: BLE001
                # Retry with smaller payload on gateway/proxy timeouts typical for Blockscout
                from aiohttp import ClientResponseError  # local import

                if (
                    isinstance(exc, ClientResponseError)
                    and exc.status in {502, 503, 504, 520, 524}
                    and attempts_left > 0
                ):
                    attempts_left -= 1
                    current_offset = max(1000, current_offset // 2)
                    continue
                raise

    spec = FetchSpec(
        name='account.internal',
        fetch_page=_fetch_page,
        key_fn=lambda it: it.get('hash') if isinstance(it.get('hash'), str) else None,
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex'))),
        max_offset=max_offset,
        resolve_end_block=(
            None
            if (isinstance(api_kind, str) and api_kind.startswith('blockscout_'))
            else _resolve_end_block_factory(
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                endpoint_builder=endpoint_builder,
                rate_limiter=rate_limiter,
                retry=retry,
            )
        ),
    )
    policy = ProviderPolicy(
        mode='paged', prefetch=1, window_cap=None, rps_key=f'{api_kind}:{network}:paging'
    )
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

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
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
    policy = resolve_policy_for_provider(
        api_kind=api_kind, network=network, max_concurrent=max_concurrent
    )
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


# --- ERC-20 token transfers (fast/basic) ---


async def fetch_all_token_transfers_basic(
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
    token_standard: str = 'erc20',
) -> list[dict[str, Any]]:
    """Provider-agnostic paged fetch for ERC-20 token transfers (tokentx)."""

    def _key_fn(it: dict[str, Any]) -> str | None:
        h = it.get('hash')
        log_idx = it.get('logIndex')
        if isinstance(h, str) and isinstance(log_idx, str | int):
            return f'{h}:{log_idx}'
        if isinstance(h, str):
            return f"{h}:{it.get('contractAddress')}:{it.get('from')}:{it.get('to')}:{it.get('value')}"
        return None

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
        return await get_token_transfers(
            address=address,
            contract_address=None,
            start_block=start_block,
            end_block=end_block,
            sort='asc',
            page=page,
            offset=offset,
            token_standard=token_standard,
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
        name='account.erc20',
        fetch_page=_fetch_page,
        key_fn=_key_fn,
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex'))),
        max_offset=max_offset,
        resolve_end_block=(
            None
            if (isinstance(api_kind, str) and api_kind.startswith('blockscout_'))
            else _resolve_end_block_factory(
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                endpoint_builder=endpoint_builder,
                rate_limiter=rate_limiter,
                retry=retry,
            )
        ),
    )
    policy = ProviderPolicy(
        mode='paged', prefetch=1, window_cap=None, rps_key=f'{api_kind}:{network}:paging'
    )
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


async def fetch_all_token_transfers_fast(
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
    token_standard: str = 'erc20',
) -> list[dict[str, Any]]:
    """Provider-aware fast fetch for ERC-20 token transfers using the generic engine."""

    def _key_fn(it: dict[str, Any]) -> str | None:
        h = it.get('hash')
        log_idx = it.get('logIndex')
        if isinstance(h, str) and isinstance(log_idx, str | int):
            return f'{h}:{log_idx}'
        if isinstance(h, str):
            return f"{h}:{it.get('contractAddress')}:{it.get('from')}:{it.get('to')}:{it.get('value')}"
        return None

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
        return await get_token_transfers(
            address=address,
            contract_address=None,
            start_block=start_block,
            end_block=end_block,
            sort='asc',
            page=page,
            offset=offset,
            token_standard=token_standard,
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
        name='account.erc20',
        fetch_page=_fetch_page,
        key_fn=_key_fn,
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
    policy = resolve_policy_for_provider(
        api_kind=api_kind, network=network, max_concurrent=max_concurrent
    )
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

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
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
            and isinstance(it.get('logIndex'), str | int)
            else None
        ),
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('logIndex'))),
        max_offset=max_offset,
        resolve_end_block=(
            None
            if (isinstance(api_kind, str) and api_kind.startswith('blockscout_'))
            else _resolve_end_block_factory(
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                endpoint_builder=endpoint_builder,
                rate_limiter=rate_limiter,
                retry=retry,
            )
        ),
    )
    policy = ProviderPolicy(
        mode='paged', prefetch=1, window_cap=None, rps_key=f'{api_kind}:{network}:paging'
    )
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

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
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
            and isinstance(it.get('logIndex'), str | int)
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
    policy = resolve_policy_for_provider(
        api_kind=api_kind, network=network, max_concurrent=max_concurrent
    )
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


# --- Etherscan-only explicit sliding variants (normal transactions) ---


async def fetch_all_transactions_eth_sliding(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    max_offset: int = 10_000,
) -> list[dict[str, Any]]:
    """Etherscan-specific sliding window (page=1, ascend, respect 10k window).

    This is equivalent to the 'eth' fast path but exposed explicitly.
    """

    api_kind = 'eth'

    spec = FetchSpec(
        name='account.txs.eth.sliding',
        fetch_page=lambda *, page, start_block, end_block, offset: get_normal_transactions(
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
        ),
        fetch_page_desc=lambda *, page, start_block, end_block, offset: get_normal_transactions(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort='desc',
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
        ),
        key_fn=lambda it: it.get('hash') if isinstance(it.get('hash'), str) else None,
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex'))),
        max_offset=min(10_000, int(max_offset)),
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
    policy = ProviderPolicy(
        mode='sliding', prefetch=1, window_cap=10_000, rps_key=f'{api_kind}:{network}:txlist'
    )
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


async def fetch_all_transactions_eth_sliding_fast(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    max_offset: int = 10_000,
) -> list[dict[str, Any]]:
    """Etherscan sliding fast: alternate asc/desc pages to utilize window from both ends.

    - Always page=1 with offset<=10_000; adjust [low..up] after each page
    - Stop when low > up or short/empty page on a side
    """

    api_kind = 'eth'
    spec = FetchSpec(
        name='account.txs.eth.sliding_bi',
        fetch_page=lambda *, page, start_block, end_block, offset: get_normal_transactions(
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
        ),
        fetch_page_desc=lambda *, page, start_block, end_block, offset: get_normal_transactions(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort='desc',
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
        ),
        key_fn=lambda it: it.get('hash') if isinstance(it.get('hash'), str) else None,
        order_fn=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex'))),
        max_offset=min(10_000, int(max_offset)),
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
    policy = ProviderPolicy(
        mode='sliding_bi', prefetch=1, window_cap=10_000, rps_key=f'{api_kind}:{network}:txlist'
    )
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
