from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

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

DataType = Literal[
    'transactions',
    'internal_transactions',
    'token_transfers',
    'logs',
]

Strategy = Literal['basic', 'fast']


def _to_int(value: Any) -> int:
    try:
        if isinstance(value, str):
            s = value.strip()
            if s.startswith('0x'):
                return int(s, 16)
            return int(s)
        return int(value)
    except Exception:  # noqa: BLE001
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
        return (
            int(latest_hex, 16)
            if isinstance(latest_hex, str) and latest_hex.startswith('0x')
            else int(latest_hex)  # type: ignore[arg-type]
        )

    return _resolve


def _is_blockscout(api_kind: str) -> bool:
    return isinstance(api_kind, str) and api_kind.startswith('blockscout_')


async def fetch_all(
    *,
    data_type: DataType,
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
    strategy: Strategy = 'fast',
    max_offset: int | None = None,
    max_concurrent: int | None = None,
    # Data-type specific optional arguments
    token_standard: str = 'erc20',
    contract_address: str | None = None,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Unified, provider-aware paged fetch for EVM account-scoped data.

    This facade encapsulates paging policy selection and page fetching for
    multiple data types while preserving a simple public API. It deduplicates
    results and returns a stable, ascending order.

    Args:
        data_type: Which dataset to fetch: "transactions", "internal_transactions",
            "token_transfers", or "logs".
        address: Account or contract address used by the provider endpoints.
        start_block: Inclusive start block, or None for provider default.
        end_block: Inclusive end block, or None to snapshot latest.
        api_kind: Provider kind identifier (e.g., "eth", "blockscout_base", ...).
        network: Network identifier used by the provider.
        api_key: API key for the provider.
        http: HTTP client port.
        endpoint_builder: Endpoint builder port.
        rate_limiter: Optional rate limiter.
        retry: Optional retry policy.
        telemetry: Optional telemetry sink.
        strategy: "fast" uses provider-aware concurrency and sliding windows when
            applicable; "basic" uses conservative paged mode.
        max_offset: Optional override for page size. Defaults depend on data type.
        max_concurrent: Optional override for concurrency when strategy is "fast".
        token_standard: Token standard for token transfers (default: "erc20").
        contract_address: Optional contract address filter for token transfers.
        topics: Optional topics for logs.
        topic_operators: Optional topic operators for logs.

    Returns:
        A list of provider items (dicts) deduplicated and stably sorted.
    """

    # Defaults per data type
    default_max_offset: int = 1000 if data_type == 'logs' else 10_000
    effective_max_offset: int = (
        int(max_offset) if isinstance(max_offset, int) else default_max_offset
    )

    # Decide provider policy (may be overridden later for special cases)
    if strategy == 'basic':
        policy = ProviderPolicy(
            mode='paged', prefetch=1, window_cap=None, rps_key=f'{api_kind}:{network}:paging'
        )
        engine_max_concurrent: int = 1
    else:
        engine_max_concurrent = (
            int(max_concurrent) if isinstance(max_concurrent, int) and max_concurrent > 0 else 8
        )
        policy = resolve_policy_for_provider(
            api_kind=api_kind, network=network, max_concurrent=engine_max_concurrent
        )

    # End-block snapshot resolver decision
    def _make_resolver() -> ResolveEndBlock | None:
        if strategy == 'basic' and _is_blockscout(api_kind):
            # Historically, basic mode skipped resolving end block for Blockscout
            return None
        if data_type == 'transactions' and _is_blockscout(api_kind):
            # Keep legacy behavior for transaction lists on Blockscout
            return None
        return _resolve_end_block_factory(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            endpoint_builder=endpoint_builder,
            rate_limiter=rate_limiter,
            retry=retry,
        )

    # Key and order functions per data type
    if data_type in ('transactions', 'internal_transactions'):

        def key_fn(it: dict[str, Any]) -> str | None:
            return it.get('hash') if isinstance(it.get('hash'), str) else None

        def order_fn(it: dict[str, Any]) -> tuple[int, int]:
            return _to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex'))
    elif data_type == 'token_transfers':

        def _key_fn_token(it: dict[str, Any]) -> str | None:
            h = it.get('hash')
            log_idx = it.get('logIndex')
            if isinstance(h, str) and isinstance(log_idx, str | int):
                return f'{h}:{log_idx}'
            if isinstance(h, str):
                return f"{h}:{it.get('contractAddress')}:{it.get('from')}:{it.get('to')}:{it.get('value')}"
            return None

        key_fn = _key_fn_token

        def order_fn(it: dict[str, Any]) -> tuple[int, int]:
            return _to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex'))
    else:  # logs

        def _key_fn_logs(it: dict[str, Any]) -> str | None:
            txh = it.get('transactionHash') or it.get('hash')
            log_idx = it.get('logIndex')
            if isinstance(txh, str) and isinstance(log_idx, str | int):
                return f'{txh}:{log_idx}'
            return None

        key_fn = _key_fn_logs

        def order_fn(it: dict[str, Any]) -> tuple[int, int]:
            return _to_int(it.get('blockNumber')), _to_int(it.get('logIndex'))

    # Page fetchers per data type
    fetch_page_desc: Callable[..., Any] | None
    if data_type == 'transactions':

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

        fetch_page_desc = None

    elif data_type == 'internal_transactions':

        async def _fetch_page(
            *, page: int, start_block: int, end_block: int, offset: int
        ) -> list[dict[str, Any]]:
            # Adaptive payload reduction for Blockscout gateway timeouts in basic mode
            if strategy == 'basic':
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
            else:
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

        fetch_page_desc = None

    elif data_type == 'token_transfers':

        async def _fetch_page(
            *, page: int, start_block: int, end_block: int, offset: int
        ) -> list[dict[str, Any]]:
            return await get_token_transfers(
                address=address,
                contract_address=contract_address,
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

        fetch_page_desc = None

    else:  # logs
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

        fetch_page_desc = None

    spec = FetchSpec(
        name={
            'transactions': 'account.txs',
            'internal_transactions': 'account.internal',
            'token_transfers': 'account.erc20',
            'logs': 'logs',
        }[data_type],
        fetch_page=_fetch_page,
        key_fn=key_fn,
        order_fn=order_fn,
        max_offset=effective_max_offset,
        fetch_page_desc=fetch_page_desc,
        resolve_end_block=_make_resolver(),
    )

    return await fetch_all_generic(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=engine_max_concurrent,
    )
