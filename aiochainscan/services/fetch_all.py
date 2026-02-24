from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiochainscan.constants import MAX_BLOCK_NUMBER
from aiochainscan.domain.dto_v2 import parse_hex_or_int_zero as _to_int
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.progress import ProgressCallback
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services._block_utils import _resolve_end_block_factory
from aiochainscan.services.account import (
    get_internal_transactions,
    get_normal_transactions,
    get_token_transfers,
)
from aiochainscan.services.logs import get_logs
from aiochainscan.services.paging_engine import (
    FetchSpec,
    ProviderPolicy,
    fetch_all_generic,
    resolve_policy_for_provider,
)

if TYPE_CHECKING:
    from aiochainscan.scanners.base import Scanner


def _is_blockscout_v2(api_kind: str, scanner: Scanner | None) -> bool:
    """Check if we should use BlockScout V2 API.

    V2 API should be used when:
    1. Scanner is explicitly BlockScoutV2Scanner, OR
    2. api_kind indicates blockscout_v2

    This fixes the "split-brain" bug where users configure blockscout_v2
    but bulk fetching silently uses V1 API endpoints.
    """
    if scanner is not None:
        # Check if scanner is BlockScoutV2Scanner
        scanner_name = getattr(scanner, 'name', '')
        scanner_version = getattr(scanner, 'version', '')
        if scanner_name == 'blockscout' and scanner_version == 'v2':
            return True
    # Also check api_kind for cases where scanner isn't passed
    return api_kind == 'blockscout_v2'


async def _fetch_all_transactions_via_v2_scanner(
    *,
    address: str,
    scanner: Scanner,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    """Fetch all transactions using BlockScout V2 scanner's native API.

    This function uses the scanner's call() method to leverage the modern
    V2 API with proper cursor-based pagination (next_page_params).

    Args:
        address: Wallet address to fetch transactions for
        scanner: BlockScoutV2Scanner instance
        telemetry: Optional telemetry for tracking

    Returns:
        List of all transactions for the address

    Raises:
        TypeError: If scanner is not BlockScoutV2Scanner
    """
    from aiochainscan.core.method import Method
    from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner

    if not isinstance(scanner, BlockScoutV2Scanner):
        raise TypeError(f'Expected BlockScoutV2Scanner, got {type(scanner).__name__}')

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
                'fetch_all.v2_page',
                {'page': page_count, 'items': len(items), 'total': len(all_items)},
            )

        # Stop if no more pages
        if not next_page_params:
            break

        # Update query params for next page
        query_params = {**query_params, **next_page_params}

    return all_items


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
    on_progress: ProgressCallback | None = None,
    # Scanner-aware fetching (fixes V2 bypass bug)
    scanner: Scanner | None = None,
) -> list[dict[str, Any]]:
    """Provider-agnostic paged fetch. Deduplicated and stably sorted.

    Args:
        address: Wallet address to fetch transactions for
        start_block: Starting block number
        end_block: Ending block number
        api_kind: API kind for URL building
        network: Network name
        api_key: API key for authentication
        http: HTTP client instance
        endpoint_builder: Endpoint builder for URL construction
        rate_limiter: Rate limiter for API requests
        retry: Retry policy for failed requests
        telemetry: Telemetry for tracking metrics
        max_offset: Maximum items per API page
        on_progress: Optional callback for progress updates
        scanner: Optional scanner instance for proper V2 API routing.
            When provided and scanner is BlockScoutV2Scanner, uses the
            modern V2 API with cursor-based pagination instead of V1.
            This fixes the "split-brain" bug where blockscout_v2 config
            silently uses V1 endpoints.

    Returns:
        List of transactions, deduplicated and sorted by block/index.
    """
    # Route to V2 scanner when appropriate (fixes split-brain bug)
    if _is_blockscout_v2(api_kind, scanner) and scanner is not None:
        try:
            return await _fetch_all_transactions_via_v2_scanner(
                address=address,
                scanner=scanner,
                telemetry=telemetry,
            )
        except (NotImplementedError, TypeError):
            # Fall back to legacy fetching
            pass

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
    on_progress: ProgressCallback | None = None,
    # Scanner-aware fetching (fixes V2 bypass bug)
    scanner: Scanner | None = None,
) -> list[dict[str, Any]]:
    """Provider-aware fast fetch using the generic paging engine.

    Args:
        address: Wallet address to fetch transactions for
        start_block: Starting block number
        end_block: Ending block number
        api_kind: API kind for URL building
        network: Network name
        api_key: API key for authentication
        http: HTTP client instance
        endpoint_builder: Endpoint builder for URL construction
        rate_limiter: Rate limiter for API requests
        retry: Retry policy for failed requests
        telemetry: Telemetry for tracking metrics
        max_offset: Maximum items per API page
        max_concurrent: Maximum concurrent requests
        on_progress: Optional callback for progress updates
        scanner: Optional scanner instance for proper V2 API routing.
            When provided and scanner is BlockScoutV2Scanner, uses the
            modern V2 API with cursor-based pagination instead of V1.
            This fixes the \"split-brain\" bug.

    Returns:
        List of transactions, deduplicated and sorted.
    """
    # Route to V2 scanner when appropriate (fixes split-brain bug)
    if _is_blockscout_v2(api_kind, scanner) and scanner is not None:
        try:
            return await _fetch_all_transactions_via_v2_scanner(
                address=address,
                scanner=scanner,
                telemetry=telemetry,
            )
        except (NotImplementedError, TypeError):
            # Fall back to legacy fetching
            pass

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
    on_progress: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    """Provider-agnostic paged fetch for internal transactions."""

    # Persistent state for adaptive offset reduction across all page fetches
    class _AdaptiveOffsetState:
        def __init__(self, initial_offset: int):
            self.current_offset = initial_offset
            self.reduction_count = 0

        def reduce_offset(self) -> None:
            old_offset = self.current_offset
            self.current_offset = max(1000, self.current_offset // 2)
            self.reduction_count += 1
            logging.debug(
                'adaptive_offset_reduction: %d -> %d (reduction #%d)',
                old_offset,
                self.current_offset,
                self.reduction_count,
            )

    offset_state = _AdaptiveOffsetState(max_offset)

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
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
                # Retry with smaller payload on gateway/proxy timeouts typical for Blockscout
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
    on_progress: ProgressCallback | None = None,
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
            return f'{h}:{it.get("contractAddress")}:{it.get("from")}:{it.get("to")}:{it.get("value")}'
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
            return f'{h}:{it.get("contractAddress")}:{it.get("from")}:{it.get("to")}:{it.get("value")}'
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
            end_block=end_block or MAX_BLOCK_NUMBER,
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
            f'{it.get("transactionHash") or it.get("hash")}:{it.get("logIndex")}'
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
            f'{it.get("transactionHash") or it.get("hash")}:{it.get("logIndex")}'
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
