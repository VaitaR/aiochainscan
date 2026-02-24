"""
Streaming decoder for on-the-fly decoding during data fetching.

This module provides memory-efficient streaming decoding for large datasets
by fetching and decoding in batches, never holding the entire dataset in memory.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from aiochainscan.constants import MAX_BLOCK_NUMBER
from aiochainscan.decode import (
    decode_log_data,
    decode_transaction_inputs_batch,
)
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services.paging_engine import (
    ProviderPolicy,
    resolve_policy_for_provider,
)


class StreamingDecoder:
    """
    Memory-efficient streaming decoder for transactions and event logs.

    Fetches data in configurable batches, decodes each batch in a thread pool
    to avoid blocking the event loop, and yields items one at a time.

    This ensures memory usage stays constant regardless of total dataset size,
    making it ideal for processing whale addresses with millions of transactions.

    Example:
        ```python
        decoder = StreamingDecoder(
            api_kind='eth',
            network='ethereum',
            api_key='YOUR_API_KEY',
            http=http_client,
            endpoint_builder=endpoint_builder,
            batch_size=1000
        )

        # Stream 1M transactions using only ~10MB RAM
        async for tx in decoder.stream_transactions(
            address='0x...whale...',
            abi=contract_abi,
            from_block=0
        ):
            await process_transaction(tx)
        ```
    """

    def __init__(
        self,
        *,
        api_kind: str,
        network: str,
        api_key: str,
        http: HttpClient,
        endpoint_builder: EndpointBuilder,
        batch_size: int = 1000,
        rate_limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
        telemetry: Telemetry | None = None,
        max_concurrent: int = 1,
    ):
        """
        Initialize streaming decoder.

        Args:
            api_kind: API kind (e.g., 'eth', 'blockscout_eth')
            network: Network name (e.g., 'ethereum', 'polygon')
            api_key: API key for authentication
            http: HTTP client instance
            endpoint_builder: Endpoint builder for URL construction
            batch_size: Number of items to fetch/decode per batch (default: 1000)
            rate_limiter: Rate limiter for API requests
            retry: Retry policy for failed requests
            telemetry: Telemetry for tracking metrics
            max_concurrent: Maximum concurrent requests for batch fetching
        """
        self.api_kind = api_kind
        self.network = network
        self.api_key = api_key
        self.http = http
        self.endpoint_builder = endpoint_builder
        self.batch_size = batch_size
        self.rate_limiter = rate_limiter
        self.retry = retry
        self.telemetry = telemetry
        self.max_concurrent = max_concurrent

    async def stream_transactions(
        self,
        address: str,
        abi: list[dict[str, Any]],
        from_block: int = 0,
        to_block: int | str | None = 'latest',
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream decoded transactions one at a time.

        Fetches transactions in batches, decodes each batch using the Rust FFI
        in a thread pool (to avoid blocking the event loop), and yields decoded
        transactions one by one.

        Args:
            address: Wallet address to fetch transactions for
            abi: Contract ABI for decoding transaction inputs
            from_block: Starting block number (default: 0)
            to_block: Ending block number or 'latest' (default: 'latest')

        Yields:
            Decoded transaction dictionaries with 'decoded_func' and 'decoded_data' fields

        Example:
            ```python
            async for tx in decoder.stream_transactions(whale_address, abi):
                print(f"Function: {tx['decoded_func']}")
                print(f"Args: {tx['decoded_data']}")
            ```
        """
        async for batch in self._fetch_transaction_batches(
            address=address,
            from_block=from_block,
            to_block=to_block,
        ):
            # Decode batch in thread pool to avoid blocking event loop
            # The Rust FFI decode functions are synchronous and can be CPU-intensive
            decoded_batch = await asyncio.to_thread(
                decode_transaction_inputs_batch,
                batch,
                abi,
            )

            # Yield each decoded transaction
            for tx in decoded_batch:
                yield tx

    async def stream_logs(
        self,
        address: str,
        abi: list[dict[str, Any]],
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        topics: list[str] | None = None,
        topic_operators: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream decoded event logs one at a time.

        Fetches logs in batches, decodes each batch in a thread pool,
        and yields decoded logs one by one.

        Args:
            address: Contract address to fetch logs for
            abi: Contract ABI for decoding event logs
            from_block: Starting block number (default: 0)
            to_block: Ending block number or 'latest' (default: 'latest')
            topics: Event topic filters (optional)
            topic_operators: Topic filter operators (optional)

        Yields:
            Decoded log dictionaries with 'decoded_event' and 'decoded_data' fields

        Example:
            ```python
            async for log in decoder.stream_logs(contract_address, abi):
                print(f"Event: {log['decoded_event']}")
                print(f"Args: {log['decoded_data']}")
            ```
        """
        async for batch in self._fetch_log_batches(
            address=address,
            from_block=from_block,
            to_block=to_block,
            topics=topics,
            topic_operators=topic_operators,
        ):
            # Decode each log in the batch
            # We decode logs one-by-one in a thread pool since decode_log_data
            # is a synchronous function
            decoded_batch = await asyncio.to_thread(
                self._decode_log_batch,
                batch,
                abi,
            )

            # Yield each decoded log
            for log in decoded_batch:
                yield log

    async def _fetch_transaction_batches(
        self,
        address: str,
        from_block: int,
        to_block: int | str | None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Fetch transactions in batches using the paging engine.

        Yields batches instead of accumulating all transactions in memory.
        """
        from aiochainscan.services.account import get_normal_transactions

        # Resolve end block
        effective_end_block: int
        if to_block is None or to_block == 'latest':
            effective_end_block = await self._resolve_end_block()
        else:
            effective_end_block = int(to_block)

        effective_start_block = int(from_block)

        if effective_end_block <= effective_start_block:
            return

        # Determine provider policy
        policy = resolve_policy_for_provider(
            api_kind=self.api_kind,
            network=self.network,
            max_concurrent=self.max_concurrent,
        )

        # Fetch in batches based on provider policy
        if policy.mode == 'sliding' or policy.mode == 'sliding_bi':
            # Sliding window mode (Etherscan-style)
            async for batch in self._fetch_sliding_batches(
                fetch_fn=lambda sb, eb, p, o: get_normal_transactions(
                    address=address,
                    start_block=sb,
                    end_block=eb,
                    sort='asc',
                    page=p,
                    offset=o,
                    api_kind=self.api_kind,
                    network=self.network,
                    api_key=self.api_key,
                    http=self.http,
                    _endpoint_builder=self.endpoint_builder,
                    _rate_limiter=None,
                    _retry=None,
                    _telemetry=self.telemetry,
                ),
                start_block=effective_start_block,
                end_block=effective_end_block,
                policy=policy,
            ):
                yield batch
        else:
            # Paged mode (Blockscout-style)
            async for batch in self._fetch_paged_batches(
                fetch_fn=lambda sb, eb, p, o: get_normal_transactions(
                    address=address,
                    start_block=sb,
                    end_block=eb,
                    sort='asc',
                    page=p,
                    offset=o,
                    api_kind=self.api_kind,
                    network=self.network,
                    api_key=self.api_key,
                    http=self.http,
                    _endpoint_builder=self.endpoint_builder,
                    _rate_limiter=None,
                    _retry=None,
                    _telemetry=self.telemetry,
                ),
                start_block=effective_start_block,
                end_block=effective_end_block,
            ):
                yield batch

    async def _fetch_log_batches(
        self,
        address: str,
        from_block: int,
        to_block: int | str | None,
        topics: list[str] | None = None,
        topic_operators: list[str] | None = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Fetch event logs in batches using the paging engine.

        Yields batches instead of accumulating all logs in memory.
        """
        from aiochainscan.services.logs import get_logs

        # Resolve end block
        effective_end_block: int
        if to_block is None or to_block == 'latest':
            effective_end_block = await self._resolve_end_block()
        else:
            effective_end_block = int(to_block)

        effective_start_block = int(from_block)

        if effective_end_block <= effective_start_block:
            return

        # Logs typically use paged mode (policy resolved internally)
        async for batch in self._fetch_paged_batches(
            fetch_fn=lambda sb, eb, p, o: get_logs(
                start_block=sb,
                end_block=eb,
                address=address,
                api_kind=self.api_kind,
                network=self.network,
                api_key=self.api_key,
                http=self.http,
                _endpoint_builder=self.endpoint_builder,
                topics=topics,
                topic_operators=topic_operators,
                page=p,
                offset=o,
                _rate_limiter=None,
                _retry=None,
                _telemetry=self.telemetry,
            ),
            start_block=effective_start_block,
            end_block=effective_end_block,
        ):
            yield batch

    async def _fetch_sliding_batches(
        self,
        fetch_fn: Any,
        start_block: int,
        end_block: int,
        policy: ProviderPolicy,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Fetch batches using sliding window strategy (Etherscan-style).

        Keeps page=1 and advances start_block after each batch.
        """
        current_block = start_block
        offset = min(self.batch_size, policy.window_cap or self.batch_size)

        while current_block <= end_block:
            # Apply rate limiting
            if self.rate_limiter and policy.rps_key:
                await self.rate_limiter.acquire(policy.rps_key)

            # Fetch one batch
            async def _do_fetch() -> list[dict[str, Any]]:  # noqa: B023
                result = await fetch_fn(current_block, end_block, 1, offset)  # noqa: B023
                return result if isinstance(result, list) else []

            # Apply retry policy
            if self.retry:
                batch = await self.retry.run(_do_fetch)
            else:
                batch = await _do_fetch()

            if not batch:
                break

            yield batch

            # Stop if we got less than requested (no more data)
            if len(batch) < offset:
                break

            # Advance start_block to last seen block + 1
            last_block = max(int(item.get('blockNumber', 0)) for item in batch)
            current_block = last_block + 1

            # Safety: prevent infinite loops
            if current_block <= start_block:
                current_block = start_block + 1

    async def _fetch_paged_batches(
        self,
        fetch_fn: Any,
        start_block: int,
        end_block: int,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Fetch batches using page-based strategy (Blockscout-style).

        Increments page number for each batch.
        """
        page = 1
        offset = self.batch_size

        while True:
            # Apply rate limiting
            if self.rate_limiter:
                rps_key = f'{self.api_kind}:{self.network}:fetch'
                await self.rate_limiter.acquire(rps_key)

            # Fetch one batch
            async def _do_fetch() -> list[dict[str, Any]]:  # noqa: B023
                result = await fetch_fn(start_block, end_block, page, offset)  # noqa: B023
                return result if isinstance(result, list) else []

            # Apply retry policy
            if self.retry:
                batch = await self.retry.run(_do_fetch)
            else:
                batch = await _do_fetch()

            if not batch:
                break

            yield batch

            # Stop if we got less than requested (no more data)
            if len(batch) < offset:
                break

            page += 1

    async def _resolve_end_block(self) -> int:
        """Resolve 'latest' to actual block number."""
        endpoint = self.endpoint_builder.open(
            api_key=self.api_key,
            api_kind=self.api_kind,
            network=self.network,
        )
        url: str = endpoint.api_url
        params: dict[str, Any] = {'module': 'proxy', 'action': 'eth_blockNumber'}
        signed_params, headers = endpoint.filter_and_sign(params, headers=None)

        async def _do() -> Any:
            if self.rate_limiter:
                rps_key = f'{self.api_kind}:{self.network}:proxy.blockNumber'
                await self.rate_limiter.acquire(key=rps_key)
            return await self.http.get(url, params=signed_params, headers=headers)

        response: Any = await (self.retry.run(_do) if self.retry else _do())
        latest_hex = response.get('result') if isinstance(response, dict) else None

        if isinstance(latest_hex, str):
            if latest_hex.startswith('0x'):
                return int(latest_hex, 16)
            if latest_hex.isdigit():
                return int(latest_hex)

        return MAX_BLOCK_NUMBER

    @staticmethod
    def _decode_log_batch(
        logs: list[dict[str, Any]],
        abi: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Decode a batch of logs synchronously.

        This is run in a thread pool via asyncio.to_thread.
        """
        decoded_logs = []
        for log in logs:
            decoded_log = decode_log_data(log, abi)
            decoded_logs.append(decoded_log)
        return decoded_logs
