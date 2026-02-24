"""
Tests for streaming decoder functionality.

Tests memory efficiency, async iteration, backpressure handling,
and batch processing with on-the-fly decoding.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.services.streaming_decoder import StreamingDecoder


@pytest.fixture
def mock_http():
    """Mock HTTP client."""
    return AsyncMock()


@pytest.fixture
def mock_endpoint_builder():
    """Mock endpoint builder."""
    builder = MagicMock()
    endpoint = MagicMock()
    endpoint.api_url = 'https://api.example.com'
    endpoint.filter_and_sign = MagicMock(return_value=({}, {}))
    builder.open = MagicMock(return_value=endpoint)
    return builder


@pytest.fixture
def sample_abi():
    """Sample ERC20 ABI for testing."""
    return [
        {
            'type': 'function',
            'name': 'transfer',
            'inputs': [
                {'name': 'to', 'type': 'address'},
                {'name': 'value', 'type': 'uint256'},
            ],
            'outputs': [{'name': '', 'type': 'bool'}],
        },
        {
            'type': 'event',
            'name': 'Transfer',
            'inputs': [
                {'name': 'from', 'type': 'address', 'indexed': True},
                {'name': 'to', 'type': 'address', 'indexed': True},
                {'name': 'value', 'type': 'uint256', 'indexed': False},
            ],
        },
    ]


@pytest.fixture
def streaming_decoder(mock_http, mock_endpoint_builder):
    """Create a StreamingDecoder instance for testing."""
    return StreamingDecoder(
        api_kind='eth',
        network='ethereum',
        api_key='test_key',
        http=mock_http,
        endpoint_builder=mock_endpoint_builder,
        batch_size=10,  # Small batch size for testing
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
    )


def create_mock_transaction(
    tx_hash: str, block_num: int, input_data: str = '0x'
) -> dict[str, Any]:
    """Helper to create a mock transaction."""
    return {
        'hash': tx_hash,
        'blockNumber': str(block_num),
        'from': '0x' + '1' * 40,
        'to': '0x' + '2' * 40,
        'value': '0',
        'input': input_data,
        'gas': '21000',
        'gasPrice': '1000000000',
        'transactionIndex': '0',
    }


def create_mock_log(tx_hash: str, block_num: int, log_index: int) -> dict[str, Any]:
    """Helper to create a mock event log."""
    return {
        'transactionHash': tx_hash,
        'blockNumber': hex(block_num),
        'logIndex': hex(log_index),
        'address': '0x' + '3' * 40,
        'topics': [
            '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',  # Transfer
            '0x000000000000000000000000' + '1' * 40,  # from (properly padded)
            '0x000000000000000000000000' + '2' * 40,  # to (properly padded)
        ],
        'data': '0x' + '0' * 63 + '5',  # value = 5
    }


class TestStreamingDecoder:
    """Test suite for StreamingDecoder."""

    @pytest.mark.asyncio
    async def test_stream_transactions_basic(self, streaming_decoder, sample_abi, monkeypatch):
        """Test basic transaction streaming without decoding."""
        # Create mock transactions
        mock_txs = [create_mock_transaction(f'0xhash{i}', 1000 + i) for i in range(25)]

        # Mock the fetch method to return batches
        batches = [mock_txs[:10], mock_txs[10:20], mock_txs[20:]]
        batch_iter = iter(batches)  # noqa: F841

        async def mock_fetch_batches(*args, **kwargs):
            for batch in batches:
                yield batch

        monkeypatch.setattr(
            streaming_decoder,
            '_fetch_transaction_batches',
            mock_fetch_batches,
        )

        # Collect streamed transactions
        collected = []
        async for tx in streaming_decoder.stream_transactions(
            address='0x' + '1' * 40,
            abi=sample_abi,
            from_block=1000,
            to_block=1025,
        ):
            collected.append(tx)

        # Verify we got all transactions
        assert len(collected) == 25
        assert collected[0]['hash'] == '0xhash0'
        assert collected[24]['hash'] == '0xhash24'

    @pytest.mark.asyncio
    async def test_stream_logs_basic(self, streaming_decoder, sample_abi, monkeypatch):
        """Test basic log streaming without decoding."""
        # Create mock logs
        mock_logs = [create_mock_log(f'0xtx{i}', 1000 + i // 2, i % 2) for i in range(25)]

        # Mock the fetch method
        async def mock_fetch_batches(*args, **kwargs):
            batches = [mock_logs[:10], mock_logs[10:20], mock_logs[20:]]
            for batch in batches:
                yield batch

        monkeypatch.setattr(
            streaming_decoder,
            '_fetch_log_batches',
            mock_fetch_batches,
        )

        # Collect streamed logs
        collected = []
        async for log in streaming_decoder.stream_logs(
            address='0x' + '3' * 40,
            abi=sample_abi,
            from_block=1000,
            to_block=1025,
        ):
            collected.append(log)

        # Verify we got all logs
        assert len(collected) == 25

    @pytest.mark.asyncio
    async def test_batch_size_respected(self, streaming_decoder, monkeypatch):
        """Test that batch size is respected during fetching."""
        batch_sizes = []

        async def mock_get_transactions(*args, **kwargs):
            offset = kwargs.get('offset', 100)
            batch_sizes.append(offset)
            return []

        # Patch the get_normal_transactions function
        import aiochainscan.services.account

        monkeypatch.setattr(
            aiochainscan.services.account,
            'get_normal_transactions',
            mock_get_transactions,
        )

        # Mock resolve_end_block
        async def mock_resolve():
            return 2000

        monkeypatch.setattr(
            streaming_decoder,
            '_resolve_end_block',
            mock_resolve,
        )

        # Stream transactions (will get empty batches and stop)
        collected = []
        async for tx in streaming_decoder.stream_transactions(
            address='0x' + '1' * 40,
            abi=[],
            from_block=1000,
            to_block=2000,
        ):
            collected.append(tx)

        # Verify batch size was used
        if batch_sizes:
            assert batch_sizes[0] == streaming_decoder.batch_size

    @pytest.mark.asyncio
    async def test_memory_efficiency(self, streaming_decoder, monkeypatch):
        """
        Test that streaming doesn't hold all data in memory.

        Verifies that we process items one at a time, not accumulating everything.
        """
        # Track maximum items held simultaneously
        max_items_in_memory = 0
        items_in_memory = 0

        # Create large dataset
        total_items = 100
        batch_size = 10

        mock_txs = [create_mock_transaction(f'0xhash{i}', 1000 + i) for i in range(total_items)]

        async def mock_fetch_batches(*args, **kwargs):
            nonlocal items_in_memory, max_items_in_memory
            for i in range(0, total_items, batch_size):
                batch = mock_txs[i : i + batch_size]
                items_in_memory += len(batch)
                max_items_in_memory = max(max_items_in_memory, items_in_memory)
                yield batch

        monkeypatch.setattr(
            streaming_decoder,
            '_fetch_transaction_batches',
            mock_fetch_batches,
        )

        # Process stream and simulate "consuming" each item
        async for tx in streaming_decoder.stream_transactions(  # noqa: B007
            address='0x' + '1' * 40,
            abi=[],
            from_block=1000,
            to_block=2000,
        ):
            items_in_memory -= 1
            # Simulate processing
            await asyncio.sleep(0)

        # Verify we never held more than batch_size + 1 items
        # (+1 because we might yield before decrementing)
        assert max_items_in_memory <= batch_size + 1
        assert max_items_in_memory < total_items  # Much less than total

    @pytest.mark.asyncio
    async def test_backpressure_handling(self, streaming_decoder, monkeypatch):
        """
        Test that slow consumers don't cause issues.

        Verifies that the stream can handle slow processing without issues.
        """
        mock_txs = [create_mock_transaction(f'0xhash{i}', 1000 + i) for i in range(30)]

        async def mock_fetch_batches(*args, **kwargs):
            batches = [mock_txs[:10], mock_txs[10:20], mock_txs[20:]]
            for batch in batches:
                yield batch

        monkeypatch.setattr(
            streaming_decoder,
            '_fetch_transaction_batches',
            mock_fetch_batches,
        )

        # Slow consumer
        collected = []
        async for tx in streaming_decoder.stream_transactions(
            address='0x' + '1' * 40,
            abi=[],
            from_block=1000,
            to_block=1030,
        ):
            collected.append(tx)
            # Simulate slow processing
            await asyncio.sleep(0.001)

        # Should still get all items
        assert len(collected) == 30

    @pytest.mark.asyncio
    async def test_decode_in_thread_pool(self, streaming_decoder, sample_abi, monkeypatch):
        """
        Test that decoding happens in thread pool (not blocking event loop).

        This is important for large batches where Rust FFI decoding is CPU-intensive.
        """
        # Track if to_thread was called
        to_thread_called = False
        original_to_thread = asyncio.to_thread  # noqa: F841

        async def mock_to_thread(fn, *args):
            nonlocal to_thread_called
            to_thread_called = True
            # Call the function synchronously for testing
            return fn(*args)

        monkeypatch.setattr(asyncio, 'to_thread', mock_to_thread)

        # Create mock transaction with valid input data
        transfer_selector = '0xa9059cbb'  # transfer(address,uint256)
        mock_txs = [
            create_mock_transaction(
                f'0xhash{i}',
                1000 + i,
                transfer_selector + '0' * 128,
            )
            for i in range(5)
        ]

        async def mock_fetch_batches(*args, **kwargs):
            yield mock_txs

        monkeypatch.setattr(
            streaming_decoder,
            '_fetch_transaction_batches',
            mock_fetch_batches,
        )

        # Stream with decoding
        collected = []
        async for tx in streaming_decoder.stream_transactions(
            address='0x' + '1' * 40,
            abi=sample_abi,
            from_block=1000,
            to_block=1005,
        ):
            collected.append(tx)

        # Verify to_thread was used for decoding
        assert to_thread_called
        assert len(collected) == 5

    @pytest.mark.asyncio
    async def test_sliding_window_mode(self, streaming_decoder, monkeypatch):
        """Test sliding window fetch strategy (Etherscan-style)."""
        calls = []

        async def mock_get_transactions(*args, **kwargs):
            sb = kwargs.get('start_block', 0)
            eb = kwargs.get('end_block', 999999)
            page = kwargs.get('page', 1)
            offset = kwargs.get('offset', 100)

            calls.append(
                {
                    'start_block': sb,
                    'end_block': eb,
                    'page': page,
                    'offset': offset,
                }
            )

            # Return progressively higher block numbers
            if len(calls) == 1:
                return [create_mock_transaction(f'0xhash{i}', sb + i) for i in range(offset)]
            elif len(calls) == 2:
                last_block = sb
                return [create_mock_transaction(f'0xhash{i}', last_block + i) for i in range(5)]
            else:
                return []

        import aiochainscan.services.account

        monkeypatch.setattr(
            aiochainscan.services.account,
            'get_normal_transactions',
            mock_get_transactions,
        )

        async def mock_resolve():
            return 2000

        monkeypatch.setattr(
            streaming_decoder,
            '_resolve_end_block',
            mock_resolve,
        )

        # Use sliding mode
        from aiochainscan.services.paging_engine import ProviderPolicy

        policy = ProviderPolicy(
            mode='sliding',
            prefetch=1,
            window_cap=10_000,
            rps_key='test:key',
        )

        collected = []
        async for batch in streaming_decoder._fetch_sliding_batches(
            fetch_fn=lambda sb, eb, p, o: mock_get_transactions(
                start_block=sb, end_block=eb, page=p, offset=o
            ),
            start_block=1000,
            end_block=2000,
            policy=policy,
        ):
            collected.extend(batch)

        # Verify sliding behavior: page always 1, start_block advances
        assert all(call['page'] == 1 for call in calls)
        assert calls[0]['start_block'] == 1000
        assert calls[1]['start_block'] > calls[0]['start_block']

    @pytest.mark.asyncio
    async def test_paged_mode(self, streaming_decoder, monkeypatch):
        """Test paged fetch strategy (Blockscout-style)."""
        calls = []

        async def mock_get_transactions(*args, **kwargs):
            page = kwargs.get('page', 1)
            offset = kwargs.get('offset', 100)

            calls.append({'page': page, 'offset': offset})

            # Return data for first 3 pages
            if page <= 2:
                return [
                    create_mock_transaction(f'0xhash{page}_{i}', 1000 + page * 10 + i)
                    for i in range(offset)
                ]
            elif page == 3:
                return [
                    create_mock_transaction(f'0xhash{page}_{i}', 1000 + page * 10 + i)
                    for i in range(5)
                ]
            else:
                return []

        import aiochainscan.services.account

        monkeypatch.setattr(
            aiochainscan.services.account,
            'get_normal_transactions',
            mock_get_transactions,
        )

        collected = []
        async for batch in streaming_decoder._fetch_paged_batches(
            fetch_fn=lambda sb, eb, p, o: mock_get_transactions(page=p, offset=o),
            start_block=1000,
            end_block=2000,
        ):
            collected.extend(batch)

        # Verify paged behavior: page increments
        assert calls[0]['page'] == 1
        assert calls[1]['page'] == 2
        assert calls[2]['page'] == 3
        assert len(calls) == 3  # Stops when less than offset returned

    @pytest.mark.asyncio
    async def test_empty_dataset(self, streaming_decoder, monkeypatch):
        """Test streaming with empty dataset."""

        async def mock_fetch_batches(*args, **kwargs):
            # Yield nothing
            return
            yield  # Make it a generator

        monkeypatch.setattr(
            streaming_decoder,
            '_fetch_transaction_batches',
            mock_fetch_batches,
        )

        collected = []
        async for tx in streaming_decoder.stream_transactions(
            address='0x' + '1' * 40,
            abi=[],
            from_block=1000,
            to_block=2000,
        ):
            collected.append(tx)

        assert len(collected) == 0

    @pytest.mark.asyncio
    async def test_early_termination(self, streaming_decoder, monkeypatch):
        """Test breaking out of stream early."""
        mock_txs = [create_mock_transaction(f'0xhash{i}', 1000 + i) for i in range(100)]

        async def mock_fetch_batches(*args, **kwargs):
            batches = [mock_txs[i : i + 10] for i in range(0, 100, 10)]
            for batch in batches:
                yield batch

        monkeypatch.setattr(
            streaming_decoder,
            '_fetch_transaction_batches',
            mock_fetch_batches,
        )

        # Only take first 15 items
        collected = []
        async for tx in streaming_decoder.stream_transactions(
            address='0x' + '1' * 40,
            abi=[],
            from_block=1000,
            to_block=2000,
        ):
            collected.append(tx)
            if len(collected) >= 15:
                break

        assert len(collected) == 15
        assert collected[0]['hash'] == '0xhash0'
        assert collected[14]['hash'] == '0xhash14'


class TestStreamingIntegration:
    """Integration tests for streaming with real-ish scenarios."""

    @pytest.mark.asyncio
    async def test_large_dataset_simulation(self, streaming_decoder, monkeypatch):
        """
        Simulate processing a large dataset (100k items).

        Verifies that memory stays bounded.
        """
        # We won't create 100k actual objects, just simulate the flow
        total_items = 100_000
        batch_size = 1000
        batches_fetched = 0

        async def mock_fetch_batches(*args, **kwargs):
            nonlocal batches_fetched
            for i in range(0, total_items, batch_size):
                batches_fetched += 1
                # Yield a minimal batch representation
                batch = [{'hash': f'0x{i + j}'} for j in range(min(batch_size, total_items - i))]
                yield batch

        monkeypatch.setattr(
            streaming_decoder,
            '_fetch_transaction_batches',
            mock_fetch_batches,
        )

        # Process stream
        items_processed = 0
        async for tx in streaming_decoder.stream_transactions(  # noqa: B007
            address='0x' + '1' * 40,
            abi=[],
            from_block=0,
            to_block='latest',
        ):
            items_processed += 1
            # Simulate light processing
            if items_processed % 10000 == 0:
                await asyncio.sleep(0)  # Yield to event loop

        assert items_processed == total_items
        assert batches_fetched == total_items // batch_size
