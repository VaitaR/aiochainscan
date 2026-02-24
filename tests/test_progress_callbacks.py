"""Tests for progress callback functionality."""

import asyncio

import pytest

from aiochainscan.services.paging_engine import (
    FetchSpec,
    ProviderPolicy,
    fetch_all_generic,
)
from aiochainscan.utils.progress_helpers import (
    callback_with_interval,
    logging_progress,
    silent_progress,
)


class TestProgressCallbackProtocol:
    """Test that progress callback protocol is correctly defined."""

    async def test_protocol_compliance(self):
        """Test that a callback adhering to the protocol works."""

        call_log = []

        async def my_callback(
            fetched: int,
            total_expected: int | None,
            current_block: int | None = None,
            current_page: int | None = None,
            operation: str = 'fetch',
        ) -> None:
            call_log.append(
                {
                    'fetched': fetched,
                    'total': total_expected,
                    'block': current_block,
                    'page': current_page,
                    'operation': operation,
                }
            )

        # Verify it's callable as ProgressCallback
        assert callable(my_callback)

        # Call it
        await my_callback(100, 1000, current_block=18000000, operation='test')

        assert len(call_log) == 1
        assert call_log[0]['fetched'] == 100
        assert call_log[0]['total'] == 1000
        assert call_log[0]['block'] == 18000000
        assert call_log[0]['operation'] == 'test'


class TestProgressHelpers:
    """Test progress helper functions."""

    async def test_silent_progress(self):
        """Test that silent progress callback does nothing."""

        callback = silent_progress()

        # Should not raise any errors
        await callback(100, 1000, current_block=18000000)
        await callback(200, None, current_page=5)

        # No assertions needed - just verify no exceptions

    async def test_logging_progress(self, caplog):
        """Test logging progress callback."""
        import logging

        with caplog.at_level(logging.INFO):
            callback = logging_progress('test.progress')

            await callback(500, 1000, current_block=18000000)

            # Check that log was created
            assert len(caplog.records) > 0
            assert '500' in caplog.text
            assert '50.0%' in caplog.text

    async def test_callback_with_interval(self):
        """Test rate-limited callback."""

        call_count = 0
        call_args = []

        async def counting_callback(fetched, total, **kwargs):
            nonlocal call_count
            call_count += 1
            call_args.append(fetched)

        # Rate limit to 0.5 seconds
        limited = callback_with_interval(counting_callback, min_interval_seconds=0.5)

        # Make several rapid calls
        await limited(100, 1000)
        await asyncio.sleep(0.1)
        await limited(200, 1000)  # Should be skipped (too soon)
        await asyncio.sleep(0.1)
        await limited(300, 1000)  # Should be skipped (too soon)
        await asyncio.sleep(0.4)  # Total 0.6s elapsed
        await limited(400, 1000)  # Should be called (>0.5s since last)

        # Only first and last should have been called
        assert call_count == 2
        assert call_args == [100, 400]


class TestPagingEngineProgressCallbacks:
    """Test progress callbacks integration with paging engine."""

    async def test_progress_callback_invoked_during_paging(self):
        """Test that progress callback is invoked during page fetching."""

        # Track callback invocations
        progress_calls = []

        async def track_progress(
            fetched: int,
            total_expected: int | None,
            current_block: int | None = None,
            current_page: int | None = None,
            operation: str = 'fetch',
        ) -> None:
            progress_calls.append(
                {
                    'fetched': fetched,
                    'total': total_expected,
                    'block': current_block,
                    'page': current_page,
                    'operation': operation,
                }
            )

        # Create mock fetch function that returns test data
        # We need at least max_offset items per page to keep fetching
        async def mock_fetch_page(*, page: int, start_block: int, end_block: int, offset: int):
            if page == 1:
                return [
                    {'hash': 'tx1', 'blockNumber': 1000, 'transactionIndex': 0},
                    {'hash': 'tx2', 'blockNumber': 1001, 'transactionIndex': 0},
                ]
            if page == 2:
                return [
                    {'hash': 'tx3', 'blockNumber': 1002, 'transactionIndex': 0},
                ]
            return []

        # Create fetch spec
        spec = FetchSpec(
            name='test.txs',
            fetch_page=mock_fetch_page,
            key_fn=lambda it: it.get('hash'),
            order_fn=lambda it: (
                int(it.get('blockNumber', 0)),
                int(it.get('transactionIndex', 0)),
            ),
            max_offset=2,  # Small offset to stop after 2 items per page
        )

        policy = ProviderPolicy(
            mode='paged',
            prefetch=1,
            window_cap=None,
            rps_key=None,
        )

        # Fetch with progress callback
        results = await fetch_all_generic(
            start_block=1000,
            end_block=2000,
            fetch_spec=spec,
            policy=policy,
            rate_limiter=None,
            retry=None,
            telemetry=None,
            max_concurrent=1,
            on_progress=track_progress,
        )

        # Verify results
        assert len(results) == 3  # All 3 transactions

        # Verify progress was called (at least once per page with data)
        assert len(progress_calls) >= 2

        # Verify progress increased
        assert progress_calls[0]['fetched'] == 2  # After first page
        if len(progress_calls) > 1:
            assert progress_calls[1]['fetched'] == 3  # After second page

    async def test_progress_callback_exception_handling(self):
        """Test that exceptions in progress callback don't crash the fetch."""

        call_count = 0

        async def failing_callback(fetched: int, total_expected: int | None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError('Simulated callback error')

        # Create simple mock data
        async def mock_fetch_page(*, page: int, start_block: int, end_block: int, offset: int):
            if page == 1:
                return [
                    {'hash': 'tx1', 'blockNumber': 1000, 'transactionIndex': 0},
                    {'hash': 'tx2', 'blockNumber': 1001, 'transactionIndex': 0},
                ]
            if page == 2:
                return [{'hash': 'tx3', 'blockNumber': 1002, 'transactionIndex': 0}]
            return []

        spec = FetchSpec(
            name='test.txs',
            fetch_page=mock_fetch_page,
            key_fn=lambda it: it.get('hash'),
            order_fn=lambda it: (
                int(it.get('blockNumber', 0)),
                int(it.get('transactionIndex', 0)),
            ),
            max_offset=2,
        )

        policy = ProviderPolicy(mode='paged', prefetch=1, window_cap=None, rps_key=None)

        # Fetch should complete despite callback error
        results = await fetch_all_generic(
            start_block=1000,
            end_block=2000,
            fetch_spec=spec,
            policy=policy,
            rate_limiter=None,
            retry=None,
            telemetry=None,
            max_concurrent=1,
            on_progress=failing_callback,
        )

        # Verify fetch completed successfully
        assert len(results) == 3

        # Verify callback was called multiple times (including the failed one)
        assert call_count >= 2


class TestProgressWithRealFetch:
    """Integration tests with real fetch scenarios."""

    @pytest.mark.asyncio
    async def test_sliding_mode_progress(self):
        """Test progress callbacks in sliding window mode."""

        progress_calls = []

        async def track_progress(
            fetched: int, total_expected: int | None, current_block: int | None = None, **kwargs
        ):
            progress_calls.append({'fetched': fetched, 'block': current_block})

        # Mock sliding window data - return less than max_offset to stop
        call_count = 0

        async def mock_fetch_sliding(*, page: int, start_block: int, end_block: int, offset: int):
            nonlocal call_count
            call_count += 1

            # Only return data for first call, then empty
            if call_count == 1:
                return [
                    {'hash': 'tx1', 'blockNumber': 1000, 'transactionIndex': 0},
                ]
            return []

        spec = FetchSpec(
            name='test.sliding',
            fetch_page=mock_fetch_sliding,
            key_fn=lambda it: it.get('hash'),
            order_fn=lambda it: (
                int(it.get('blockNumber', 0)),
                int(it.get('transactionIndex', 0)),
            ),
            max_offset=10,  # Return less than this to stop
        )

        policy = ProviderPolicy(mode='sliding', prefetch=1, window_cap=None, rps_key=None)

        results = await fetch_all_generic(
            start_block=1000,
            end_block=2000,
            fetch_spec=spec,
            policy=policy,
            rate_limiter=None,
            retry=None,
            telemetry=None,
            max_concurrent=1,
            on_progress=track_progress,
        )

        # Verify results
        assert len(results) == 1

        # Verify progress was tracked
        assert len(progress_calls) >= 1

        # Verify blocks progressed
        assert progress_calls[0]['block'] == 1000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
