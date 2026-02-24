"""
Streaming versions of fetch_all functions for memory-efficient data fetching.

This module provides AsyncIterator-based streaming versions of all fetch_all
functions to handle whale addresses with millions of transactions without OOM.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.progress import ProgressCallback
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
    ResolveEndBlock,
    resolve_policy_for_provider,
)
from aiochainscan.services.paging_streaming import fetch_all_generic_streaming

if TYPE_CHECKING:
    from aiochainscan.scanners.base import Scanner


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


def _is_blockscout_v2(api_kind: str, scanner: Scanner | None) -> bool:
    """Check if we should use BlockScout V2 API for streaming."""
    if scanner is not None:
        scanner_name = getattr(scanner, 'name', '')
        scanner_version = getattr(scanner, 'version', '')
        if scanner_name == 'blockscout' and scanner_version == 'v2':
            return True
    return api_kind == 'blockscout_v2'


async def _stream_v2_transactions(
    *,
    address: str,
    scanner: Scanner,
    batch_size: int = 1000,
    telemetry: Telemetry | None = None,
    on_progress: ProgressCallback | None = None,
) -> AsyncIterator[list[dict[str, Any]]]:
    """
    Stream transactions using BlockScout V2's native cursor pagination.

    This uses the modern V2 API with next_page_params for efficient pagination.
    """
    from aiochainscan.core.method import Method
    from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner

    if not isinstance(scanner, BlockScoutV2Scanner):
        raise TypeError(f'Expected BlockScoutV2Scanner, got {type(scanner).__name__}')

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

    batch: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    total_fetched = 0
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

        page_count += 1

        # Deduplicate and accumulate into batch
        for item in items:
            tx_hash = item.get('hash')
            if tx_hash and tx_hash not in seen_keys:
                seen_keys.add(tx_hash)
                batch.append(item)
                total_fetched += 1

                # Yield batch when full
                if len(batch) >= batch_size:
                    if on_progress:
                        await on_progress(
                            fetched=total_fetched,
                            total_expected=None,
                            current_page=page_count,
                            operation='streaming_v2',
                        )
                    yield batch
                    batch = []

        if telemetry:
            await telemetry.record_event(
                'streaming.v2_page',
                {'page': page_count, 'items': len(items), 'total': total_fetched},
            )

        # Stop if no more pages
        if not next_page_params:
            break

        # Update query params for next page
        query_params = {**query_params, **next_page_params}

    # Yield remaining items
    if batch:
        if on_progress:
            await on_progress(
                fetched=total_fetched,
                total_expected=total_fetched,
                current_page=page_count,
                operation='streaming_v2_complete',
            )
        yield batch


async def fetch_all_transactions_streaming(
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
    batch_size: int = 1000,
    on_progress: ProgressCallback | None = None,
    # Scanner-aware fetching (fixes V2 bypass bug)
    scanner: Scanner | None = None,
) -> AsyncIterator[list[dict[str, Any]]]:
    """
    Stream normal transactions in batches for memory-efficient processing.

    This streaming version yields batches of transactions instead of accumulating
    everything in memory, making it suitable for whale addresses with millions
    of transactions.

    Args:
        address: Wallet address to fetch transactions for
        start_block: Starting block number (None for 0)
        end_block: Ending block number (None for latest)
        api_kind: API kind (e.g., 'eth', 'blockscout_polygon')
        network: Network name
        api_key: API key for authentication
        http: HTTP client instance
        endpoint_builder: Endpoint builder for URL construction
        rate_limiter: Rate limiter for API requests
        retry: Retry policy for failed requests
        telemetry: Telemetry for tracking metrics
        max_offset: Maximum items per API page
        batch_size: Number of items to yield per batch (default: 1000)
        on_progress: Optional callback for progress updates
        scanner: Optional scanner instance for proper V2 API routing.
            When provided and scanner is BlockScoutV2Scanner, uses the
            modern V2 API with cursor-based pagination.

    Yields:
        Batches of transaction dictionaries

    Example:
        ```python
        async for batch in fetch_all_transactions_streaming(
            address='0x...whale...',
            start_block=0,
            end_block=None,
            api_kind='eth',
            network='ethereum',
            api_key=api_key,
            http=http_client,
            endpoint_builder=builder,
            batch_size=1000,
        ):
            # Process 1000 transactions at a time
            for tx in batch:
                print(tx['hash'])
        ```
    """
    # Route to V2 scanner when appropriate (fixes split-brain bug)
    if _is_blockscout_v2(api_kind, scanner) and scanner is not None:
        try:
            async for batch in _stream_v2_transactions(
                address=address,
                scanner=scanner,
                batch_size=batch_size,
                telemetry=telemetry,
                on_progress=on_progress,
            ):
                yield batch
            return  # Successfully used V2, don't fall through
        except (NotImplementedError, TypeError):
            # Fall back to legacy streaming
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
    policy = resolve_policy_for_provider(api_kind=api_kind, network=network, max_concurrent=1)

    async for batch in fetch_all_generic_streaming(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=1,
        batch_size=batch_size,
        on_progress=on_progress,
    ):
        yield batch


async def fetch_all_internal_streaming(
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
    batch_size: int = 1000,
    on_progress: ProgressCallback | None = None,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Stream internal transactions in batches for memory-efficient processing."""

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
    policy = resolve_policy_for_provider(api_kind=api_kind, network=network, max_concurrent=1)

    async for batch in fetch_all_generic_streaming(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=1,
        batch_size=batch_size,
        on_progress=on_progress,
    ):
        yield batch


async def fetch_all_token_transfers_streaming(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    contract_address: str | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    max_offset: int = 10_000,
    batch_size: int = 1000,
    on_progress: ProgressCallback | None = None,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Stream ERC20 token transfers in batches for memory-efficient processing."""

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
        return await get_token_transfers(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort='asc',
            page=page,
            offset=offset,
            contract_address=contract_address,
            token_standard='erc20',
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
        name='account.tokentx',
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
    policy = resolve_policy_for_provider(api_kind=api_kind, network=network, max_concurrent=1)

    async for batch in fetch_all_generic_streaming(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=1,
        batch_size=batch_size,
        on_progress=on_progress,
    ):
        yield batch


async def fetch_all_logs_streaming(
    *,
    address: str | None,
    start_block: int | None,
    end_block: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    endpoint_builder: EndpointBuilder,
    topic0: str | None = None,
    topic1: str | None = None,
    topic2: str | None = None,
    topic3: str | None = None,
    topic0_1_opr: str | None = None,
    topic1_2_opr: str | None = None,
    topic2_3_opr: str | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    max_offset: int = 1_000,
    batch_size: int = 1000,
    on_progress: ProgressCallback | None = None,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Stream event logs in batches for memory-efficient processing."""
    # Build topics list from individual topic params
    topics: list[str] | None = None
    if any([topic0, topic1, topic2, topic3]):
        topics = [t for t in [topic0, topic1, topic2, topic3] if t is not None]

    # Build topic operators list
    topic_operators: list[str] | None = None
    if any([topic0_1_opr, topic1_2_opr, topic2_3_opr]):
        topic_operators = [
            op for op in [topic0_1_opr, topic1_2_opr, topic2_3_opr] if op is not None
        ]

    async def _fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, Any]]:
        # address is required by get_logs, use empty string if None
        effective_address = address if address is not None else ''
        return await get_logs(
            address=effective_address,
            start_block=start_block,
            end_block=end_block,
            page=page,
            offset=offset,
            topics=topics,
            topic_operators=topic_operators,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint_builder,
            _rate_limiter=None,
            _retry=None,
            _telemetry=telemetry,
        )

    def _log_key(it: dict[str, Any]) -> str | None:
        tx_hash = it.get('transactionHash')
        log_index = it.get('logIndex')
        if isinstance(tx_hash, str) and log_index is not None:
            return f'{tx_hash}:{log_index}'
        return None

    spec = FetchSpec(
        name='logs.getLogs',
        fetch_page=_fetch_page,
        key_fn=_log_key,
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
    policy = resolve_policy_for_provider(api_kind=api_kind, network=network, max_concurrent=1)

    async for batch in fetch_all_generic_streaming(
        start_block=start_block,
        end_block=end_block,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=1,
        batch_size=batch_size,
        on_progress=on_progress,
    ):
        yield batch
