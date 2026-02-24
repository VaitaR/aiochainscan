"""
Chunked block range fetcher to prevent database timeouts on explorers.

This module provides automatic block range chunking for getLogs and similar
methods that can timeout when requesting large block ranges (e.g., 0 to latest).
The chunker splits large ranges into smaller chunks and fetches them in parallel
with intelligent rate limiting.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from aiochainscan.constants import (
    API_CHUNK_SIZE_BLOCKS,
    API_MAX_OFFSET_ETHERSCAN,
    BATCH_MAX_CONCURRENT_CHUNKS,
)
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry


class ChunkedBlockFetcher:
    """Fetches data by splitting large block ranges into manageable chunks.

    This strategy is useful when querying popular contracts from block 0 to latest,
    which can cause database timeouts on explorers BEFORE pagination limits are reached.

    Example:
        >>> fetcher = ChunkedBlockFetcher(
        ...     http=http_client,
        ...     endpoint_builder=endpoint_builder,
        ...     chunk_size=API_CHUNK_SIZE_BLOCKS
        ... )
        >>> logs = await fetcher.fetch_logs(
        ...     address="0x...",
        ...     from_block=0,
        ...     to_block=20_000_000,
        ...     api_kind="eth",
        ...     network="ethereum",
        ...     api_key="..."
        ... )
    """

    def __init__(
        self,
        http: HttpClient,
        endpoint_builder: EndpointBuilder,
        chunk_size: int | None = None,
        rate_limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
        telemetry: Telemetry | None = None,
        max_concurrent_chunks: int | None = None,
    ):
        """Initialize the chunked block fetcher.

        Args:
            http: HTTP client for making requests
            endpoint_builder: Endpoint builder for constructing API URLs
            chunk_size: Default block range size per chunk (default: API_CHUNK_SIZE_BLOCKS)
            rate_limiter: Optional rate limiter
            retry: Optional retry policy
            telemetry: Optional telemetry for monitoring
            max_concurrent_chunks: Maximum number of chunks to fetch in parallel
                (default: BATCH_MAX_CONCURRENT_CHUNKS)
        """
        self.http = http
        self.endpoint_builder = endpoint_builder
        self.chunk_size = chunk_size if chunk_size is not None else API_CHUNK_SIZE_BLOCKS
        self.rate_limiter = rate_limiter
        self.retry = retry
        self.telemetry = telemetry
        self.max_concurrent_chunks = (
            max_concurrent_chunks
            if max_concurrent_chunks is not None
            else BATCH_MAX_CONCURRENT_CHUNKS
        )

    async def _resolve_latest_block(
        self,
        *,
        api_kind: str,
        network: str,
        api_key: str,
    ) -> int:
        """Resolve 'latest' to actual block number using eth_blockNumber."""
        endpoint = self.endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
        url: str = endpoint.api_url
        params_proxy: dict[str, Any] = {'module': 'proxy', 'action': 'eth_blockNumber'}
        signed_params, headers = endpoint.filter_and_sign(params_proxy, headers=None)

        async def _do() -> Any:
            if self.rate_limiter is not None:
                await self.rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.blockNumber')
            return await self.http.get(url, params=signed_params, headers=headers)

        response: Any = await (self.retry.run(_do) if self.retry is not None else _do())
        latest_hex = response.get('result') if isinstance(response, dict) else None
        return (
            int(latest_hex, 16)
            if isinstance(latest_hex, str) and latest_hex.startswith('0x')
            else int(latest_hex)  # type: ignore[arg-type]
        )

    def _split_into_chunks(
        self,
        from_block: int,
        to_block: int,
        chunk_size: int | None = None,
    ) -> list[tuple[int, int]]:
        """Split a block range into chunks.

        Args:
            from_block: Starting block number (inclusive)
            to_block: Ending block number (inclusive)
            chunk_size: Size of each chunk (default: self.chunk_size)

        Returns:
            List of (start, end) tuples for each chunk
        """
        effective_chunk_size = chunk_size if chunk_size is not None else self.chunk_size
        chunks: list[tuple[int, int]] = []

        current = from_block
        while current <= to_block:
            chunk_end = min(current + effective_chunk_size - 1, to_block)
            chunks.append((current, chunk_end))
            current = chunk_end + 1

        return chunks

    async def _fetch_logs_chunk(
        self,
        *,
        address: str,
        from_block: int,
        to_block: int,
        api_kind: str,
        network: str,
        api_key: str,
        topics: list[str] | None = None,
        topic_operators: list[str] | None = None,
        page: int = 1,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch logs for a single chunk.

        This is a low-level method that fetches one chunk without pagination.
        It returns up to `offset` results for the given block range.
        """
        effective_offset = offset if offset is not None else API_MAX_OFFSET_ETHERSCAN
        endpoint = self.endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
        url: str = endpoint.api_url

        params: dict[str, Any] = {
            'module': 'logs',
            'action': 'getLogs',
            'fromBlock': from_block,
            'toBlock': to_block,
            'address': address,
            'page': page,
            'offset': effective_offset,
        }

        if topics:
            for idx, topic in enumerate(topics[:4]):
                params[f'topic{idx}'] = topic
        if topic_operators:
            for idx, op in enumerate(topic_operators[:3]):
                params[f'topic{idx}_{idx + 1}_opr'] = op

        signed_params, headers = endpoint.filter_and_sign(params, headers=None)

        async def _do() -> Any:
            if self.rate_limiter is not None:
                await self.rate_limiter.acquire(key=f'{api_kind}:{network}:logs')
            return await self.http.get(url, params=signed_params, headers=headers)

        response: Any = await (self.retry.run(_do) if self.retry is not None else _do())

        # Handle different response formats
        if isinstance(response, dict):
            result = response.get('result', [])
            if isinstance(result, list):
                return result
            # No logs found
            return []

        return []

    async def fetch_logs(
        self,
        *,
        address: str,
        from_block: int | str,
        to_block: int | str,
        api_kind: str,
        network: str,
        api_key: str,
        topics: list[str] | None = None,
        topic_operators: list[str] | None = None,
        chunk_size: int | None = None,
        on_chunk_complete: Callable[[int, int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch logs across a large block range using chunking.

        Args:
            address: Contract address to query
            from_block: Starting block (can be int or 'latest')
            to_block: Ending block (can be int or 'latest')
            api_kind: API kind (e.g., 'eth', 'blockscout_eth')
            network: Network name (e.g., 'ethereum')
            api_key: API key for authentication
            topics: Optional list of topic filters
            topic_operators: Optional list of topic operators
            chunk_size: Override default chunk size
            on_chunk_complete: Optional callback(chunk_num, total_chunks, items_fetched)

        Returns:
            Deduplicated and sorted list of log entries
        """
        # Resolve 'latest' to actual block number
        resolved_from = (
            await self._resolve_latest_block(api_kind=api_kind, network=network, api_key=api_key)
            if from_block == 'latest'
            else int(from_block)
        )
        resolved_to = (
            await self._resolve_latest_block(api_kind=api_kind, network=network, api_key=api_key)
            if to_block == 'latest'
            else int(to_block)
        )

        if resolved_from > resolved_to:
            return []

        # Split into chunks
        chunks = self._split_into_chunks(resolved_from, resolved_to, chunk_size)
        total_chunks = len(chunks)

        if self.telemetry:
            await self.telemetry.record_event(
                'chunked_fetcher.start',
                {
                    'total_chunks': total_chunks,
                    'chunk_size': chunk_size or self.chunk_size,
                    'from_block': resolved_from,
                    'to_block': resolved_to,
                },
            )

        # Fetch chunks with controlled concurrency
        all_logs: list[dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.max_concurrent_chunks)

        async def fetch_chunk_with_semaphore(
            chunk_num: int, chunk_from: int, chunk_to: int
        ) -> tuple[int, list[dict[str, Any]]]:
            async with semaphore:
                logs = await self._fetch_logs_chunk(
                    address=address,
                    from_block=chunk_from,
                    to_block=chunk_to,
                    api_kind=api_kind,
                    network=network,
                    api_key=api_key,
                    topics=topics,
                    topic_operators=topic_operators,
                )

                if self.telemetry:
                    await self.telemetry.record_event(
                        'chunked_fetcher.chunk_complete',
                        {
                            'chunk': chunk_num,
                            'from_block': chunk_from,
                            'to_block': chunk_to,
                            'items': len(logs),
                        },
                    )

                if on_chunk_complete:
                    on_chunk_complete(chunk_num, total_chunks, len(logs))

                return chunk_num, logs

        # Fetch all chunks in parallel (with semaphore limiting concurrency)
        tasks = [
            fetch_chunk_with_semaphore(idx + 1, chunk_from, chunk_to)
            for idx, (chunk_from, chunk_to) in enumerate(chunks)
        ]
        results = await asyncio.gather(*tasks)

        # Sort by chunk number to maintain order
        results.sort(key=lambda x: x[0])

        # Combine results
        for _, logs in results:
            all_logs.extend(logs)

        # Deduplicate by transaction hash + log index
        seen_keys: set[str] = set()
        deduplicated: list[dict[str, Any]] = []

        for log in all_logs:
            # Create unique key from transaction hash and log index
            tx_hash = log.get('transactionHash') or log.get('hash')
            log_index = log.get('logIndex')

            if tx_hash and log_index is not None:
                key = f'{tx_hash}:{log_index}'
                if key not in seen_keys:
                    seen_keys.add(key)
                    deduplicated.append(log)
            else:
                # If we can't create a unique key, include it anyway
                deduplicated.append(log)

        # Sort by block number and log index for stable ordering
        def sort_key(log: dict[str, Any]) -> tuple[int, int]:
            block_num = log.get('blockNumber', 0)
            log_idx = log.get('logIndex', 0)
            # Handle hex strings
            if isinstance(block_num, str):
                block_num = int(block_num, 16) if block_num.startswith('0x') else int(block_num)
            if isinstance(log_idx, str):
                log_idx = int(log_idx, 16) if log_idx.startswith('0x') else int(log_idx)
            return (int(block_num), int(log_idx))

        deduplicated.sort(key=sort_key)

        if self.telemetry:
            await self.telemetry.record_event(
                'chunked_fetcher.complete',
                {
                    'total_chunks': total_chunks,
                    'total_logs': len(deduplicated),
                    'duplicates_removed': len(all_logs) - len(deduplicated),
                },
            )

        return deduplicated

    async def fetch_transactions(
        self,
        *,
        address: str,
        from_block: int | str,
        to_block: int | str,
        api_kind: str,
        network: str,
        api_key: str,
        chunk_size: int | None = None,
        on_chunk_complete: Callable[[int, int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch account transactions across a large block range using chunking.

        Similar to fetch_logs but for account transaction history.

        Args:
            address: Account address to query
            from_block: Starting block (can be int or 'latest')
            to_block: Ending block (can be int or 'latest')
            api_kind: API kind (e.g., 'eth', 'blockscout_eth')
            network: Network name (e.g., 'ethereum')
            api_key: API key for authentication
            chunk_size: Override default chunk size
            on_chunk_complete: Optional callback(chunk_num, total_chunks, items_fetched)

        Returns:
            Deduplicated and sorted list of transactions
        """
        # Resolve 'latest' to actual block number
        resolved_from = (
            await self._resolve_latest_block(api_kind=api_kind, network=network, api_key=api_key)
            if from_block == 'latest'
            else int(from_block)
        )
        resolved_to = (
            await self._resolve_latest_block(api_kind=api_kind, network=network, api_key=api_key)
            if to_block == 'latest'
            else int(to_block)
        )

        if resolved_from > resolved_to:
            return []

        # Split into chunks
        chunks = self._split_into_chunks(resolved_from, resolved_to, chunk_size)
        total_chunks = len(chunks)

        # Fetch chunks with controlled concurrency
        all_txs: list[dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.max_concurrent_chunks)

        async def fetch_chunk(
            chunk_num: int, chunk_from: int, chunk_to: int
        ) -> tuple[int, list[dict[str, Any]]]:
            async with semaphore:
                endpoint = self.endpoint_builder.open(
                    api_key=api_key, api_kind=api_kind, network=network
                )
                url: str = endpoint.api_url

                params: dict[str, Any] = {
                    'module': 'account',
                    'action': 'txlist',
                    'address': address,
                    'startblock': chunk_from,
                    'endblock': chunk_to,
                    'sort': 'asc',
                }

                signed_params, headers = endpoint.filter_and_sign(params, headers=None)

                async def _do() -> Any:
                    if self.rate_limiter is not None:
                        await self.rate_limiter.acquire(key=f'{api_kind}:{network}:account.txlist')
                    return await self.http.get(url, params=signed_params, headers=headers)

                response: Any = await (self.retry.run(_do) if self.retry is not None else _do())

                txs: list[dict[str, Any]] = []
                if isinstance(response, dict):
                    result = response.get('result', [])
                    if isinstance(result, list):
                        txs = result

                if on_chunk_complete:
                    on_chunk_complete(chunk_num, total_chunks, len(txs))

                return chunk_num, txs

        # Fetch all chunks in parallel
        tasks = [
            fetch_chunk(idx + 1, chunk_from, chunk_to)
            for idx, (chunk_from, chunk_to) in enumerate(chunks)
        ]
        results = await asyncio.gather(*tasks)

        # Sort by chunk number and combine
        results.sort(key=lambda x: x[0])
        for _, txs in results:
            all_txs.extend(txs)

        # Deduplicate by transaction hash
        seen_hashes: set[str] = set()
        deduplicated: list[dict[str, Any]] = []

        for tx in all_txs:
            tx_hash = tx.get('hash')
            if tx_hash and tx_hash not in seen_hashes:
                seen_hashes.add(tx_hash)
                deduplicated.append(tx)

        # Sort by block number and transaction index
        def sort_key(tx: dict[str, Any]) -> tuple[int, int]:
            block_num = tx.get('blockNumber', 0)
            tx_idx = tx.get('transactionIndex', 0)
            if isinstance(block_num, str):
                block_num = int(block_num)
            if isinstance(tx_idx, str):
                tx_idx = int(tx_idx)
            return (int(block_num), int(tx_idx))

        deduplicated.sort(key=sort_key)

        return deduplicated
