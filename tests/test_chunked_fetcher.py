"""Tests for chunked block range fetcher.

This test suite verifies that the ChunkedBlockFetcher correctly:
- Splits large block ranges into chunks
- Fetches chunks in parallel with rate limiting
- Deduplicates results at chunk boundaries
- Handles 'latest' block resolution
- Adjusts chunk sizes based on result density
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.services.chunked_fetcher import ChunkedBlockFetcher


@pytest.fixture
def mock_http():
    """Mock HTTP client."""
    return AsyncMock()


@pytest.fixture
def mock_endpoint_builder():
    """Mock endpoint builder."""
    builder = MagicMock()
    endpoint = MagicMock()
    endpoint.api_url = 'https://api.example.com/api'
    endpoint.filter_and_sign = MagicMock(return_value=({}, {}))
    builder.open = MagicMock(return_value=endpoint)
    return builder


@pytest.fixture
def chunked_fetcher(mock_http, mock_endpoint_builder):
    """Create a ChunkedBlockFetcher instance for testing."""
    return ChunkedBlockFetcher(
        http=mock_http,
        endpoint_builder=mock_endpoint_builder,
        chunk_size=1000,
        max_concurrent_chunks=2,
    )


class TestChunkSplitting:
    """Test block range splitting logic."""

    def test_split_exact_multiple(self, chunked_fetcher):
        """Test splitting when range is exact multiple of chunk size."""
        chunks = chunked_fetcher._split_into_chunks(0, 2999, chunk_size=1000)
        assert len(chunks) == 3
        assert chunks == [(0, 999), (1000, 1999), (2000, 2999)]

    def test_split_with_remainder(self, chunked_fetcher):
        """Test splitting when range is not exact multiple."""
        chunks = chunked_fetcher._split_into_chunks(0, 2500, chunk_size=1000)
        assert len(chunks) == 3
        assert chunks == [(0, 999), (1000, 1999), (2000, 2500)]

    def test_split_single_chunk(self, chunked_fetcher):
        """Test when range fits in single chunk."""
        chunks = chunked_fetcher._split_into_chunks(100, 500, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks == [(100, 500)]

    def test_split_custom_chunk_size(self, chunked_fetcher):
        """Test with custom chunk size."""
        chunks = chunked_fetcher._split_into_chunks(0, 10000, chunk_size=2500)
        assert len(chunks) == 5
        assert chunks == [(0, 2499), (2500, 4999), (5000, 7499), (7500, 9999), (10000, 10000)]

    def test_split_single_block(self, chunked_fetcher):
        """Test single block range."""
        chunks = chunked_fetcher._split_into_chunks(100, 100, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks == [(100, 100)]


@pytest.mark.asyncio
class TestLatestBlockResolution:
    """Test resolving 'latest' to actual block number."""

    async def test_resolve_latest_hex_format(self, chunked_fetcher, mock_http):
        """Test resolving latest block from hex response."""
        mock_http.get = AsyncMock(return_value={'result': '0x1234567'})

        latest = await chunked_fetcher._resolve_latest_block(
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
        )

        assert latest == 0x1234567
        assert latest == 19088743

    async def test_resolve_latest_decimal_format(self, chunked_fetcher, mock_http):
        """Test resolving latest block from decimal response."""
        mock_http.get = AsyncMock(return_value={'result': 19088743})

        latest = await chunked_fetcher._resolve_latest_block(
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
        )

        assert latest == 19088743


@pytest.mark.asyncio
class TestLogsFetching:
    """Test log fetching with chunking."""

    async def test_fetch_logs_basic(self, chunked_fetcher, mock_http):
        """Test basic log fetching across multiple chunks."""
        # Mock responses for each chunk
        call_count = {'n': 0}

        async def mock_get(*args, **kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                # Latest block number
                return {'result': '0x64'}  # 100
            elif call_count['n'] == 2:
                # Chunk 1 (0-49)
                return {
                    'result': [
                        {'blockNumber': '10', 'logIndex': '0', 'transactionHash': '0x1'},
                        {'blockNumber': '20', 'logIndex': '0', 'transactionHash': '0x2'},
                    ]
                }
            else:
                # Chunk 2 (50-99)
                return {
                    'result': [
                        {'blockNumber': '60', 'logIndex': '0', 'transactionHash': '0x3'},
                        {'blockNumber': '80', 'logIndex': '0', 'transactionHash': '0x4'},
                    ]
                }

        mock_http.get = mock_get

        logs = await chunked_fetcher.fetch_logs(
            address='0xtest',
            from_block=0,
            to_block='latest',
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
            chunk_size=50,
        )

        assert len(logs) == 4
        assert logs[0]['blockNumber'] == '10'
        assert logs[-1]['blockNumber'] == '80'

    async def test_fetch_logs_deduplication(self, chunked_fetcher, mock_http):
        """Test that duplicate logs at chunk boundaries are deduplicated."""
        call_count = {'n': 0}

        async def mock_get(*args, **kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                return {
                    'result': [
                        {'blockNumber': '10', 'logIndex': '0', 'transactionHash': '0x1'},
                        {'blockNumber': '50', 'logIndex': '0', 'transactionHash': '0x2'},
                    ]
                }
            else:
                return {
                    'result': [
                        {'blockNumber': '50', 'logIndex': '0', 'transactionHash': '0x2'},
                        {'blockNumber': '80', 'logIndex': '0', 'transactionHash': '0x3'},
                    ]
                }

        mock_http.get = mock_get

        logs = await chunked_fetcher.fetch_logs(
            address='0xtest',
            from_block=0,
            to_block=100,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
            chunk_size=50,
        )

        # Should have 3 unique logs, not 4
        assert len(logs) == 3
        tx_hashes = [log['transactionHash'] for log in logs]
        assert tx_hashes == ['0x1', '0x2', '0x3']

    async def test_fetch_logs_empty_chunks(self, chunked_fetcher, mock_http):
        """Test handling empty chunks."""
        call_count = {'n': 0}

        async def mock_get(*args, **kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                return {'result': []}  # Empty chunk 1
            else:
                return {
                    'result': [
                        {'blockNumber': '80', 'logIndex': '0', 'transactionHash': '0x1'},
                    ]
                }  # Non-empty chunk 2

        mock_http.get = mock_get

        logs = await chunked_fetcher.fetch_logs(
            address='0xtest',
            from_block=0,
            to_block=100,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
            chunk_size=50,
        )

        assert len(logs) == 1
        assert logs[0]['transactionHash'] == '0x1'

    async def test_fetch_logs_with_topics(self, chunked_fetcher, mock_http):
        """Test log fetching with topic filters."""
        mock_http.get = AsyncMock(return_value={'result': []})

        await chunked_fetcher.fetch_logs(
            address='0xtest',
            from_block=0,
            to_block=100,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
            topics=['0xtopic1', '0xtopic2'],
            topic_operators=['and'],
        )

        # Verify mock was called (topics are handled in the implementation)
        assert mock_http.get.called

    async def test_fetch_logs_sorting(self, chunked_fetcher, mock_http):
        """Test that logs are sorted by block number and log index."""
        mock_http.get = AsyncMock(
            return_value={
                'result': [
                    {'blockNumber': '50', 'logIndex': '1', 'transactionHash': '0x3'},
                    {'blockNumber': '10', 'logIndex': '0', 'transactionHash': '0x1'},
                    {'blockNumber': '50', 'logIndex': '0', 'transactionHash': '0x2'},
                ]
            }
        )

        logs = await chunked_fetcher.fetch_logs(
            address='0xtest',
            from_block=0,
            to_block=100,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
        )

        assert len(logs) == 3
        assert logs[0]['blockNumber'] == '10'
        assert logs[1]['blockNumber'] == '50'
        assert logs[1]['logIndex'] == '0'
        assert logs[2]['logIndex'] == '1'

    async def test_fetch_logs_hex_block_numbers(self, chunked_fetcher, mock_http):
        """Test handling logs with hex-encoded block numbers."""
        mock_http.get = AsyncMock(
            return_value={
                'result': [
                    {'blockNumber': '0x32', 'logIndex': '0x1', 'transactionHash': '0x2'},
                    {'blockNumber': '0xa', 'logIndex': '0x0', 'transactionHash': '0x1'},
                ]
            }
        )

        logs = await chunked_fetcher.fetch_logs(
            address='0xtest',
            from_block=0,
            to_block=100,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
        )

        # Should be sorted: block 10 (0xa) before block 50 (0x32)
        assert len(logs) == 2
        assert logs[0]['blockNumber'] == '0xa'
        assert logs[1]['blockNumber'] == '0x32'


@pytest.mark.asyncio
class TestTransactionsFetching:
    """Test transaction fetching with chunking."""

    async def test_fetch_transactions_basic(self, chunked_fetcher, mock_http):
        """Test basic transaction fetching."""
        call_count = {'n': 0}

        async def mock_get(*args, **kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                return {
                    'result': [
                        {'blockNumber': '10', 'transactionIndex': '0', 'hash': '0x1'},
                    ]
                }
            else:
                return {
                    'result': [
                        {'blockNumber': '80', 'transactionIndex': '0', 'hash': '0x2'},
                    ]
                }

        mock_http.get = mock_get

        txs = await chunked_fetcher.fetch_transactions(
            address='0xtest',
            from_block=0,
            to_block=100,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
            chunk_size=50,
        )

        assert len(txs) == 2
        assert txs[0]['hash'] == '0x1'
        assert txs[1]['hash'] == '0x2'

    async def test_fetch_transactions_deduplication(self, chunked_fetcher, mock_http):
        """Test transaction deduplication by hash."""
        call_count = {'n': 0}

        async def mock_get(*args, **kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                return {
                    'result': [
                        {'blockNumber': '10', 'transactionIndex': '0', 'hash': '0x1'},
                        {'blockNumber': '50', 'transactionIndex': '0', 'hash': '0x2'},
                    ]
                }
            else:
                return {
                    'result': [
                        {'blockNumber': '50', 'transactionIndex': '0', 'hash': '0x2'},  # Duplicate
                        {'blockNumber': '80', 'transactionIndex': '0', 'hash': '0x3'},
                    ]
                }

        mock_http.get = mock_get

        txs = await chunked_fetcher.fetch_transactions(
            address='0xtest',
            from_block=0,
            to_block=100,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
            chunk_size=50,
        )

        assert len(txs) == 3
        hashes = [tx['hash'] for tx in txs]
        assert hashes == ['0x1', '0x2', '0x3']


@pytest.mark.asyncio
class TestProgressCallback:
    """Test progress reporting callback."""

    async def test_progress_callback_called(self, chunked_fetcher, mock_http):
        """Test that progress callback is called for each chunk."""
        call_count = {'n': 0}

        async def mock_get(*args, **kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                return {
                    'result': [{'blockNumber': '10', 'logIndex': '0', 'transactionHash': '0x1'}]
                }
            else:
                return {
                    'result': [{'blockNumber': '60', 'logIndex': '0', 'transactionHash': '0x2'}]
                }

        mock_http.get = mock_get

        callback_calls = []

        def on_chunk_complete(chunk_num: int, total_chunks: int, items_fetched: int):
            callback_calls.append((chunk_num, total_chunks, items_fetched))

        await chunked_fetcher.fetch_logs(
            address='0xtest',
            from_block=0,
            to_block=100,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
            chunk_size=50,
            on_chunk_complete=on_chunk_complete,
        )

        # 0-100 with chunk_size=50 creates 3 chunks: [0-49], [50-99], [100-100]
        assert len(callback_calls) == 3
        assert callback_calls[0][1] == 3  # total_chunks should be 3
        assert callback_calls[1][1] == 3
        assert callback_calls[2][1] == 3


@pytest.mark.asyncio
class TestConcurrencyControl:
    """Test parallel chunk fetching with concurrency limits."""

    async def test_concurrent_chunk_fetching(self, mock_http, mock_endpoint_builder):
        """Test that chunks are fetched in parallel up to max_concurrent_chunks."""
        fetcher = ChunkedBlockFetcher(
            http=mock_http,
            endpoint_builder=mock_endpoint_builder,
            chunk_size=50,
            max_concurrent_chunks=2,
        )

        # Track concurrent calls
        active_calls = []
        max_concurrent = 0

        async def mock_get(*args, **kwargs):
            active_calls.append(1)
            current = len(active_calls)
            nonlocal max_concurrent
            max_concurrent = max(max_concurrent, current)
            await asyncio.sleep(0.01)  # Simulate API delay
            active_calls.pop()
            return {'result': []}

        import asyncio

        mock_http.get = mock_get

        # Fetch 4 chunks with max_concurrent_chunks=2
        await fetcher.fetch_logs(
            address='0xtest',
            from_block=0,
            to_block=199,  # Will create 4 chunks of 50 each
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
        )

        # Should never exceed 2 concurrent calls
        assert max_concurrent <= 2


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error conditions."""

    async def test_from_block_greater_than_to_block(self, chunked_fetcher):
        """Test when from_block > to_block."""
        logs = await chunked_fetcher.fetch_logs(
            address='0xtest',
            from_block=100,
            to_block=50,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
        )

        assert logs == []

    async def test_invalid_response_format(self, chunked_fetcher, mock_http):
        """Test handling of unexpected response format."""
        mock_http.get = AsyncMock(return_value={'error': 'Something went wrong'})

        logs = await chunked_fetcher.fetch_logs(
            address='0xtest',
            from_block=0,
            to_block=100,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
        )

        # Should return empty list instead of crashing
        assert logs == []

    async def test_non_dict_response(self, chunked_fetcher, mock_http):
        """Test handling of non-dict response."""
        mock_http.get = AsyncMock(return_value=[])

        logs = await chunked_fetcher.fetch_logs(
            address='0xtest',
            from_block=0,
            to_block=100,
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
        )

        assert logs == []
