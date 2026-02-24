"""Tests for whale block pagination data loss prevention.

This test suite verifies that the paging engine correctly detects and fails
when a single block contains more transactions than the API's pagination limit,
preventing silent data loss.
"""

from __future__ import annotations

import pytest

from aiochainscan.exceptions import PaginationDataLossError
from aiochainscan.services.paging_engine import (
    FetchSpec,
    ProviderPolicy,
    fetch_all_generic,
)


@pytest.mark.asyncio
async def test_whale_block_raises_pagination_error() -> None:
    """Test that whale blocks (single block with >= max_offset items) raise PaginationDataLossError."""

    # Mock fetch function that simulates a whale block
    # Block 100 has 10,000 transactions (hitting the API limit)
    call_count = 0

    async def mock_fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, str]]:
        nonlocal call_count
        call_count += 1

        # First call: return 10,000 items all from block 100
        if call_count == 1:
            return [
                {
                    'blockNumber': '100',
                    'transactionIndex': str(i),
                    'hash': f'0x{i:064x}',
                }
                for i in range(10_000)
            ]

        # Should never reach here - exception should be raised
        return []

    def key_fn(item: dict[str, str]) -> str:
        return item['hash']

    def order_fn(item: dict[str, str]) -> tuple[int, int]:
        return (int(item['blockNumber']), int(item['transactionIndex']))

    spec = FetchSpec(
        name='test_whale',
        fetch_page=mock_fetch_page,
        key_fn=key_fn,
        order_fn=order_fn,
        max_offset=10_000,
    )

    policy = ProviderPolicy(
        mode='sliding',
        prefetch=1,
        window_cap=10_000,
        rps_key=None,
    )

    # Should raise PaginationDataLossError instead of silently skipping
    with pytest.raises(PaginationDataLossError) as exc_info:
        await fetch_all_generic(
            start_block=0,
            end_block=1000,
            fetch_spec=spec,
            policy=policy,
            rate_limiter=None,
            retry=None,
            telemetry=None,
            max_concurrent=1,
        )

    # Verify exception details
    error = exc_info.value
    assert error.block_number == 100
    assert error.items_fetched == 10_000
    assert error.api_limit == 10_000
    assert 'GraphQL' in error.suggested_action or 'topic filter' in error.suggested_action
    assert call_count == 1  # Should fail on first page with whale block


@pytest.mark.asyncio
async def test_whale_block_not_triggered_when_below_limit() -> None:
    """Test that blocks with fewer items than the limit don't trigger whale detection."""

    async def mock_fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, str]]:
        # Return 9,999 items (below limit of 10,000)
        if start_block == 0:
            return [
                {
                    'blockNumber': '100',
                    'transactionIndex': str(i),
                    'hash': f'0x{i:064x}',
                }
                for i in range(9_999)
            ]
        return []

    def key_fn(item: dict[str, str]) -> str:
        return item['hash']

    def order_fn(item: dict[str, str]) -> tuple[int, int]:
        return (int(item['blockNumber']), int(item['transactionIndex']))

    spec = FetchSpec(
        name='test_normal',
        fetch_page=mock_fetch_page,
        key_fn=key_fn,
        order_fn=order_fn,
        max_offset=10_000,
    )

    policy = ProviderPolicy(
        mode='sliding',
        prefetch=1,
        window_cap=10_000,
        rps_key=None,
    )

    # Should NOT raise - 9,999 < 10,000
    result = await fetch_all_generic(
        start_block=0,
        end_block=1000,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
    )

    assert len(result) == 9_999


@pytest.mark.asyncio
async def test_whale_block_not_triggered_when_multiple_blocks() -> None:
    """Test that 10k items spanning multiple blocks don't trigger whale detection."""

    async def mock_fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, str]]:
        # Return 10,000 items across blocks 100-109
        if start_block == 0:
            return [
                {
                    'blockNumber': str(100 + (i // 1000)),  # Spread across 10 blocks
                    'transactionIndex': str(i % 1000),
                    'hash': f'0x{i:064x}',
                }
                for i in range(10_000)
            ]
        return []

    def key_fn(item: dict[str, str]) -> str:
        return item['hash']

    def order_fn(item: dict[str, str]) -> tuple[int, int]:
        return (int(item['blockNumber']), int(item['transactionIndex']))

    spec = FetchSpec(
        name='test_multi_block',
        fetch_page=mock_fetch_page,
        key_fn=key_fn,
        order_fn=order_fn,
        max_offset=10_000,
    )

    policy = ProviderPolicy(
        mode='sliding',
        prefetch=1,
        window_cap=10_000,
        rps_key=None,
    )

    # Should NOT raise - items span multiple blocks
    result = await fetch_all_generic(
        start_block=0,
        end_block=1000,
        fetch_spec=spec,
        policy=policy,
        rate_limiter=None,
        retry=None,
        telemetry=None,
        max_concurrent=1,
    )

    assert len(result) == 10_000


@pytest.mark.asyncio
async def test_whale_block_exception_message() -> None:
    """Test that the exception message contains helpful guidance."""

    async def mock_fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, str]]:
        return [
            {'blockNumber': '12345', 'transactionIndex': str(i), 'hash': f'0x{i:064x}'}
            for i in range(10_000)
        ]

    spec = FetchSpec(
        name='test',
        fetch_page=mock_fetch_page,
        key_fn=lambda x: x['hash'],
        order_fn=lambda x: (int(x['blockNumber']), int(x['transactionIndex'])),
        max_offset=10_000,
    )

    policy = ProviderPolicy(mode='sliding', prefetch=1, window_cap=10_000, rps_key=None)

    with pytest.raises(PaginationDataLossError) as exc_info:
        await fetch_all_generic(
            start_block=0,
            end_block=99999,
            fetch_spec=spec,
            policy=policy,
            rate_limiter=None,
            retry=None,
            telemetry=None,
            max_concurrent=1,
        )

    error_msg = str(exc_info.value)
    assert '12345' in error_msg  # Block number
    assert '10000' in error_msg or '10,000' in error_msg  # Item count
    assert 'GraphQL' in error_msg or 'topic' in error_msg or 'filter' in error_msg  # Suggestions


@pytest.mark.asyncio
async def test_whale_block_with_telemetry() -> None:
    """Test that whale block detection records telemetry event."""

    events: list[tuple[str, dict]] = []

    class MockTelemetry:
        async def record_event(self, name: str, data: dict) -> None:
            events.append((name, data))

        async def record_error(self, name: str, exc: Exception, data: dict) -> None:
            pass

    async def mock_fetch_page(
        *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[dict[str, str]]:
        return [
            {'blockNumber': '555', 'transactionIndex': str(i), 'hash': f'0x{i:064x}'}
            for i in range(10_000)
        ]

    spec = FetchSpec(
        name='test',
        fetch_page=mock_fetch_page,
        key_fn=lambda x: x['hash'],
        order_fn=lambda x: (int(x['blockNumber']), int(x['transactionIndex'])),
        max_offset=10_000,
    )

    policy = ProviderPolicy(mode='sliding', prefetch=1, window_cap=10_000, rps_key=None)

    with pytest.raises(PaginationDataLossError):
        await fetch_all_generic(
            start_block=0,
            end_block=99999,
            fetch_spec=spec,
            policy=policy,
            rate_limiter=None,
            retry=None,
            telemetry=MockTelemetry(),
            max_concurrent=1,
        )

    # Verify telemetry was recorded
    whale_events = [e for e in events if 'whale' in e[0]]
    assert len(whale_events) == 1
    event_name, event_data = whale_events[0]
    assert event_name == 'paging.whale_block_detected'
    assert event_data['block'] == 555
    assert event_data['items_fetched'] == 10_000
    assert event_data['limit'] == 10_000
