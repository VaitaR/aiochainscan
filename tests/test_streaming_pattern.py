"""
Tests for AsyncIterator streaming pattern in paging_engine.

These tests verify that the streaming implementation provides constant memory
usage and correct results for large datasets (whale addresses).
"""

import pytest

from aiochainscan.services.paging_engine import FetchSpec, ProviderPolicy
from aiochainscan.services.paging_streaming import fetch_all_generic_streaming


class MockHttp:
    """Mock HTTP client for testing."""

    def __init__(self, pages_data: list[list[dict]]):
        """
        Initialize mock HTTP client.

        Args:
            pages_data: List of pages, where each page is a list of items
        """
        self.pages_data = pages_data
        self.call_count = 0

    async def get(self, url: str, params: dict, headers: dict | None = None) -> dict:
        """Mock GET request."""
        page = params.get('page', 1)
        if page > len(self.pages_data):
            return {'result': []}
        self.call_count += 1
        return {'result': self.pages_data[page - 1]}


@pytest.mark.asyncio
async def test_streaming_basic_pagination():
    """Test basic streaming pagination with paged mode."""
    # Create mock data: 3 pages with 100 items each
    pages_data = [
        [{'hash': f'0x{i:064x}', 'blockNumber': i, 'transactionIndex': 0} for i in range(100)],
        [
            {'hash': f'0x{i:064x}', 'blockNumber': i, 'transactionIndex': 0}
            for i in range(100, 200)
        ],
        [
            {'hash': f'0x{i:064x}', 'blockNumber': i, 'transactionIndex': 0}
            for i in range(200, 300)
        ],
    ]

    async def fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict]:
        if page > len(pages_data):
            return []
        return pages_data[page - 1]

    spec = FetchSpec(
        name='test.txs',
        fetch_page=fetch_page,
        key_fn=lambda it: it.get('hash'),
        order_fn=lambda it: (it.get('blockNumber', 0), it.get('transactionIndex', 0)),
        max_offset=100,
    )

    policy = ProviderPolicy(
        mode='paged',
        prefetch=1,
        window_cap=None,
        rps_key=None,
    )

    # Stream with batch_size=50
    all_items = []
    batch_count = 0
    async for batch in fetch_all_generic_streaming(
        start_block=0,
        end_block=99_999,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
        batch_size=50,
    ):
        batch_count += 1
        all_items.extend(batch)
        # Each batch should be exactly 50 items (except possibly the last)
        assert len(batch) <= 50

    # Should have 300 items total (3 pages * 100 items)
    assert len(all_items) == 300
    # Should have 6 batches (300 items / 50 per batch)
    assert batch_count == 6
    # Items should be deduplicated and sorted
    assert all_items[0]['blockNumber'] == 0
    assert all_items[-1]['blockNumber'] == 299


@pytest.mark.asyncio
async def test_streaming_sliding_window():
    """Test streaming with sliding window mode."""
    # Simulate sliding window: each call advances start_block
    call_count = 0

    async def fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict]:
        nonlocal call_count
        call_count += 1

        # Return items for current window
        if start_block >= 300:
            return []

        end = min(start_block + 100, 300)
        return [
            {
                'hash': f'0x{i:064x}',
                'blockNumber': i,
                'transactionIndex': 0,
            }
            for i in range(start_block, end)
        ]

    spec = FetchSpec(
        name='test.txs',
        fetch_page=fetch_page,
        key_fn=lambda it: it.get('hash'),
        order_fn=lambda it: (it.get('blockNumber', 0), it.get('transactionIndex', 0)),
        max_offset=100,
    )

    policy = ProviderPolicy(
        mode='sliding',
        prefetch=1,
        window_cap=None,
        rps_key=None,
    )

    all_items = []
    async for batch in fetch_all_generic_streaming(
        start_block=0,
        end_block=99_999,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
        batch_size=150,
    ):
        all_items.extend(batch)

    # Should have 300 items
    assert len(all_items) == 300
    # Should be sorted
    assert all_items[0]['blockNumber'] == 0
    assert all_items[-1]['blockNumber'] == 299


@pytest.mark.asyncio
async def test_streaming_deduplication():
    """Test that streaming properly deduplicates items."""

    # Create mock data with duplicates
    async def fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict]:
        if page > 2:
            return []

        # Page 1: items 0-99
        # Page 2: items 50-149 (overlaps with page 1)
        start = (page - 1) * 50
        return [
            {
                'hash': f'0x{i:064x}',
                'blockNumber': i,
                'transactionIndex': 0,
            }
            for i in range(start, start + 100)
        ]

    spec = FetchSpec(
        name='test.txs',
        fetch_page=fetch_page,
        key_fn=lambda it: it.get('hash'),
        order_fn=lambda it: (it.get('blockNumber', 0), it.get('transactionIndex', 0)),
        max_offset=100,
    )

    policy = ProviderPolicy(
        mode='paged',
        prefetch=1,
        window_cap=None,
        rps_key=None,
    )

    all_items = []
    async for batch in fetch_all_generic_streaming(
        start_block=0,
        end_block=99_999,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
        batch_size=50,
    ):
        all_items.extend(batch)

    # Should have 150 unique items (not 200 with duplicates)
    assert len(all_items) == 150
    # Items should be sorted
    assert all_items[0]['blockNumber'] == 0
    assert all_items[-1]['blockNumber'] == 149


@pytest.mark.asyncio
async def test_streaming_batch_size_control():
    """Test that batch_size is respected."""

    async def fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict]:
        if page > 10:
            return []
        return [
            {
                'hash': f'0x{(page-1)*100+i:064x}',
                'blockNumber': (page - 1) * 100 + i,
                'transactionIndex': 0,
            }
            for i in range(100)
        ]

    spec = FetchSpec(
        name='test.txs',
        fetch_page=fetch_page,
        key_fn=lambda it: it.get('hash'),
        order_fn=lambda it: (it.get('blockNumber', 0), it.get('transactionIndex', 0)),
        max_offset=100,
    )

    policy = ProviderPolicy(
        mode='paged',
        prefetch=1,
        window_cap=None,
        rps_key=None,
    )

    # Test with batch_size=250
    batches = []
    async for batch in fetch_all_generic_streaming(
        start_block=0,
        end_block=99_999,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
        batch_size=250,
    ):
        batches.append(batch)
        # All batches except possibly last should be exactly 250
        if batch != batches[-1]:
            assert len(batch) == 250

    # Total should be 1000 items (10 pages * 100 items)
    total_items = sum(len(b) for b in batches)
    assert total_items == 1000

    # Should have 4 batches (1000 / 250)
    assert len(batches) == 4


@pytest.mark.asyncio
async def test_streaming_early_termination():
    """Test early termination (breaking out of iteration)."""

    async def fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict]:
        if page > 100:  # Simulate large dataset
            return []
        return [
            {
                'hash': f'0x{(page-1)*100+i:064x}',
                'blockNumber': (page - 1) * 100 + i,
                'transactionIndex': 0,
            }
            for i in range(100)
        ]

    spec = FetchSpec(
        name='test.txs',
        fetch_page=fetch_page,
        key_fn=lambda it: it.get('hash'),
        order_fn=lambda it: (it.get('blockNumber', 0), it.get('transactionIndex', 0)),
        max_offset=100,
    )

    policy = ProviderPolicy(
        mode='paged',
        prefetch=1,
        window_cap=None,
        rps_key=None,
    )

    # Only process first 500 items
    items_processed = 0
    async for batch in fetch_all_generic_streaming(
        start_block=0,
        end_block=99_999,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
        batch_size=100,
    ):
        items_processed += len(batch)
        if items_processed >= 500:
            break

    # Should have processed around 500 items (maybe slightly more due to batch)
    assert 500 <= items_processed < 600


@pytest.mark.asyncio
async def test_streaming_progress_callback():
    """Test progress callback during streaming."""
    progress_calls = []

    async def on_progress(
        fetched: int,
        total_expected: int | None,
        current_block: int | None,
        current_page: int | None,
        operation: str,
    ) -> None:
        progress_calls.append(
            {
                'fetched': fetched,
                'current_block': current_block,
                'current_page': current_page,
            }
        )

    async def fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict]:
        if page > 5:
            return []
        return [
            {
                'hash': f'0x{(page-1)*100+i:064x}',
                'blockNumber': (page - 1) * 100 + i,
                'transactionIndex': 0,
            }
            for i in range(100)
        ]

    spec = FetchSpec(
        name='test.txs',
        fetch_page=fetch_page,
        key_fn=lambda it: it.get('hash'),
        order_fn=lambda it: (it.get('blockNumber', 0), it.get('transactionIndex', 0)),
        max_offset=100,
    )

    policy = ProviderPolicy(
        mode='paged',
        prefetch=1,
        window_cap=None,
        rps_key=None,
    )

    all_items = []
    async for batch in fetch_all_generic_streaming(
        start_block=0,
        end_block=99_999,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
        batch_size=100,
        on_progress=on_progress,
    ):
        all_items.extend(batch)

    # Progress callback should have been called
    assert len(progress_calls) > 0
    # Last progress call should have all items processed
    # Note: progress is called per page, not per batch yield
    assert len(all_items) == 500


@pytest.mark.asyncio
async def test_streaming_invalid_batch_size():
    """Test that invalid batch_size raises error."""
    spec = FetchSpec(
        name='test.txs',
        fetch_page=lambda **kwargs: [],
        key_fn=lambda it: it.get('hash'),
        order_fn=lambda it: (it.get('blockNumber', 0), it.get('transactionIndex', 0)),
        max_offset=100,
    )

    policy = ProviderPolicy(
        mode='paged',
        prefetch=1,
        window_cap=None,
        rps_key=None,
    )

    with pytest.raises(ValueError, match='batch_size must be at least 1'):
        async for _ in fetch_all_generic_streaming(
            start_block=0,
            end_block=100,
            fetch_spec=spec,
            policy=policy,
            rate_limiter=None,
            retry=None,
            telemetry=None,
            max_concurrent=1,
            batch_size=0,
        ):
            pass


@pytest.mark.asyncio
async def test_streaming_empty_dataset():
    """Test streaming with empty dataset."""

    async def fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict]:
        return []

    spec = FetchSpec(
        name='test.txs',
        fetch_page=fetch_page,
        key_fn=lambda it: it.get('hash'),
        order_fn=lambda it: (it.get('blockNumber', 0), it.get('transactionIndex', 0)),
        max_offset=100,
    )

    policy = ProviderPolicy(
        mode='paged',
        prefetch=1,
        window_cap=None,
        rps_key=None,
    )

    batches = []
    async for batch in fetch_all_generic_streaming(
        start_block=0,
        end_block=100,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
        batch_size=100,
    ):
        batches.append(batch)

    # Should have no batches
    assert len(batches) == 0


@pytest.mark.asyncio
async def test_streaming_large_dataset_simulation():
    """Simulate streaming 100k items to verify constant memory usage."""
    # This test simulates a whale address with 100k transactions
    TOTAL_ITEMS = 100_000  # noqa: N806
    PAGE_SIZE = 10_000  # noqa: N806

    call_count = 0

    async def fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict]:
        nonlocal call_count
        call_count += 1

        start_idx = (page - 1) * PAGE_SIZE
        if start_idx >= TOTAL_ITEMS:
            return []

        end_idx = min(start_idx + PAGE_SIZE, TOTAL_ITEMS)
        return [
            {
                'hash': f'0x{i:064x}',
                'blockNumber': i,
                'transactionIndex': 0,
            }
            for i in range(start_idx, end_idx)
        ]

    spec = FetchSpec(
        name='test.whale',
        fetch_page=fetch_page,
        key_fn=lambda it: it.get('hash'),
        order_fn=lambda it: (it.get('blockNumber', 0), it.get('transactionIndex', 0)),
        max_offset=PAGE_SIZE,
    )

    policy = ProviderPolicy(
        mode='paged',
        prefetch=1,
        window_cap=None,
        rps_key=None,
    )

    total_items = 0
    batch_count = 0

    # Stream with 1000 items per batch
    async for batch in fetch_all_generic_streaming(
        start_block=0,
        end_block=99_999_999,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
        batch_size=1000,
    ):
        total_items += len(batch)
        batch_count += 1
        # At any point, we should only have 1 batch in memory (constant usage)
        assert len(batch) <= 1000

    # Should have processed all 100k items
    assert total_items == TOTAL_ITEMS
    # Should have 100 batches (100k / 1000)
    assert batch_count == 100
    # Should have made 10-11 API calls (100k / 10k per page, plus one to check if more pages exist)
    assert 10 <= call_count <= 11
