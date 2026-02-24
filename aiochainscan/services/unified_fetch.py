from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from aiochainscan.constants import (
    API_CHUNK_SIZE_BLOCKS,
    API_MAX_OFFSET_ETHERSCAN,
    API_MAX_OFFSET_LOGS,
    BATCH_DEFAULT_CONCURRENCY,
    BATCH_MAX_CONCURRENT_CHUNKS,
)
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services.account import (
    get_internal_transactions,
    get_normal_transactions,
    get_token_transfers,
)
from aiochainscan.services.chunked_fetcher import ChunkedBlockFetcher
from aiochainscan.services.logs import get_logs
from aiochainscan.services.paging_engine import (
    FetchSpec,
    ProviderPolicy,
    ResolveEndBlock,
    fetch_all_generic,
    resolve_policy_for_provider,
)

if TYPE_CHECKING:
    from aiochainscan.scanners.base import Scanner

DataType = Literal[
    'transactions',
    'internal_transactions',
    'token_transfers',
    'logs',
]

Strategy = Literal['basic', 'fast', 'chunked']


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


def _is_blockscout_v2(api_kind: str, scanner: Scanner | None) -> bool:
    """Check if we should use BlockScout V2 API.

    V2 API should be used when:
    1. Scanner is explicitly BlockScoutV2Scanner, OR
    2. api_kind indicates blockscout_v2
    """
    if scanner is not None:
        # Check if scanner is BlockScoutV2Scanner
        scanner_name = getattr(scanner, 'name', '')
        scanner_version = getattr(scanner, 'version', '')
        if scanner_name == 'blockscout' and scanner_version == 'v2':
            return True
    # Also check api_kind for cases where scanner isn't passed
    return api_kind == 'blockscout_v2'


async def _fetch_all_via_v2_scanner(
    *,
    data_type: DataType,
    address: str,
    scanner: Scanner,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    """Fetch all data using BlockScout V2 scanner's native API.

    This function uses the scanner's call() method to leverage the modern
    V2 API with proper cursor-based pagination (next_page_params).

    Currently supports: transactions
    Other data types will fall back to legacy fetching.
    """
    from aiochainscan.core.method import Method
    from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner

    if not isinstance(scanner, BlockScoutV2Scanner):
        raise TypeError(f'Expected BlockScoutV2Scanner, got {type(scanner).__name__}')

    if data_type != 'transactions':
        # V2 scanner currently only has ACCOUNT_TRANSACTIONS
        # Other types will need to fall back to legacy API
        raise NotImplementedError(f'BlockScout V2 bulk fetch for {data_type} not yet implemented')

    all_items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    # Build initial request
    spec = scanner.SPECS[Method.ACCOUNT_TRANSACTIONS]
    url = scanner._build_url(spec, address=address)
    query_params = scanner._build_query_params(spec, address=address)

    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip, deflate',
    }

    # Use scanner's network client
    if scanner._network_client is None:
        from aiochainscan.network import Network

        scanner._network_client = Network(scanner.url_builder)

    # Pagination loop using next_page_params
    page_count = 0
    while True:
        raw_response = await scanner._network_client.request(
            method='GET',
            url=url,
            params=query_params if query_params else None,
            headers=headers,
        )

        # Extract items and pagination cursor
        if isinstance(raw_response, dict):
            items = raw_response.get('items', [])
            next_page_params = raw_response.get('next_page_params')
        else:
            items = raw_response if isinstance(raw_response, list) else []
            next_page_params = None

        # Deduplicate by hash
        for item in items:
            tx_hash = item.get('hash')
            if tx_hash and tx_hash not in seen_keys:
                seen_keys.add(tx_hash)
                all_items.append(item)

        page_count += 1

        if telemetry:
            await telemetry.record_event(
                'unified_fetch.v2_page',
                {'page': page_count, 'items': len(items), 'total': len(all_items)},
            )

        # Stop if no more pages
        if not next_page_params:
            break

        # Update query params for next page
        query_params = {**query_params, **next_page_params}

    return all_items


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
    # Scanner-aware fetching (fixes V2 bypass bug)
    scanner: Scanner | None = None,
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
            applicable; "basic" uses conservative paged mode; "chunked" splits large
            block ranges into chunks to avoid database timeouts.
        max_offset: Optional override for page size. Defaults depend on data type.
        max_concurrent: Optional override for concurrency when strategy is "fast".
        token_standard: Token standard for token transfers (default: "erc20").
        contract_address: Optional contract address filter for token transfers.
        topics: Optional topics for logs.
        topic_operators: Optional topic operators for logs.
        scanner: Optional scanner instance for proper V2 API routing.
            When provided and scanner is BlockScoutV2Scanner, this function
            will use the modern V2 API with cursor-based pagination instead
            of the legacy V1 API. This fixes the "split-brain" bug where
            users specify blockscout_v2 but bulk fetching silently uses V1.

    Returns:
        A list of provider items (dicts) deduplicated and stably sorted.
    """

    # Route to V2 scanner when appropriate (fixes split-brain bug)
    # BlockScout V2 uses modern REST API with cursor pagination (next_page_params)
    # which is more efficient and correct than the legacy V1 API
    if (
        _is_blockscout_v2(api_kind, scanner)
        and scanner is not None
        and data_type == 'transactions'
    ):
        try:
            return await _fetch_all_via_v2_scanner(
                data_type=data_type,
                address=address,
                scanner=scanner,
                telemetry=telemetry,
            )
        except (NotImplementedError, TypeError):
            # Fall back to legacy fetching if V2 doesn't support this data type
            pass

    # Handle chunked strategy separately
    if strategy == 'chunked':
        chunk_size = int(max_offset) if max_offset else API_CHUNK_SIZE_BLOCKS
        max_chunks = int(max_concurrent) if max_concurrent else BATCH_MAX_CONCURRENT_CHUNKS

        fetcher = ChunkedBlockFetcher(
            http=http,
            endpoint_builder=endpoint_builder,
            chunk_size=chunk_size,
            rate_limiter=rate_limiter,
            retry=retry,
            telemetry=telemetry,
            max_concurrent_chunks=max_chunks,
        )

        # Convert None to default values
        from_block = start_block if start_block is not None else 0
        to_block = end_block if end_block is not None else 'latest'

        if data_type == 'logs':
            return await fetcher.fetch_logs(
                address=address,
                from_block=from_block,
                to_block=to_block,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                topics=topics,
                topic_operators=topic_operators,
            )
        elif data_type == 'transactions':
            return await fetcher.fetch_transactions(
                address=address,
                from_block=from_block,
                to_block=to_block,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
            )
        else:
            # For other data types, fall back to fast strategy
            strategy = 'fast'

    # Defaults per data type
    default_max_offset: int = (
        API_MAX_OFFSET_LOGS if data_type == 'logs' else API_MAX_OFFSET_ETHERSCAN
    )
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
            int(max_concurrent)
            if isinstance(max_concurrent, int) and max_concurrent > 0
            else BATCH_DEFAULT_CONCURRENCY
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
                return f'{h}:{it.get("contractAddress")}:{it.get("from")}:{it.get("to")}:{it.get("value")}'
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

    # Persistent state for adaptive offset reduction (only for internal_transactions in basic mode)
    class _AdaptiveOffsetState:
        def __init__(self, initial_offset: int):
            self.current_offset = initial_offset
            self.reduction_count = 0

        def reduce_offset(self) -> None:
            old_offset = self.current_offset
            self.current_offset = max(API_MAX_OFFSET_LOGS, self.current_offset // 2)
            self.reduction_count += 1
            logging.debug(
                'adaptive_offset_reduction: %d -> %d (reduction #%d)',
                old_offset,
                self.current_offset,
                self.reduction_count,
            )

    offset_state = _AdaptiveOffsetState(effective_max_offset)

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
                # Use persistent offset state; ignore the 'offset' parameter from engine after first reduction
                effective_offset = offset_state.current_offset
                attempts_left = 3
                while True:
                    try:
                        return await get_internal_transactions(
                            address=address,
                            start_block=start_block,
                            end_block=end_block,
                            sort='asc',
                            page=page,
                            offset=effective_offset,
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
                        import httpx  # local import

                        if (
                            isinstance(exc, httpx.HTTPStatusError)
                            and exc.response.status_code in {502, 503, 504, 520, 524}
                            and attempts_left > 0
                        ):
                            attempts_left -= 1
                            offset_state.reduce_offset()
                            effective_offset = offset_state.current_offset
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
