"""Test adaptive offset persistence across page fetches.

This test verifies that the fix for the yo-yo effect bug is working correctly.
When timeouts occur, the offset should be reduced and STAY reduced for subsequent
page fetches, not reset to the original high value.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from aiochainscan.core.context import ProviderContext
from aiochainscan.services.fetch_all import fetch_all_internal_basic
from aiochainscan.services.unified_fetch import fetch_all


@pytest.mark.asyncio
async def test_adaptive_offset_multiple_page_scenario():
    """Test the yo-yo bug fix in a true multi-page scenario.

    This simulates what happens with the OLD buggy code vs NEW fixed code:

    OLD (buggy): Page 1: try 10k (fail) -> retry 5k (ok)
                 Page 2: try 10k (fail) -> retry 5k (ok)  <- BUG: resets to 10k!
                 = 4 API calls, 2 unnecessary failures

    NEW (fixed): Page 1: try 10k (fail) -> retry 5k (ok)
                 Page 2: try 5k (ok)  <- FIX: remembers reduction!
                 = 3 API calls, 1 failure
    """

    offset_values_used = []
    call_count = [0]

    # We'll manually control when pages are requested by creating a custom scenario
    # where the paging engine's offset parameter changes between pages
    with patch('aiochainscan.services.fetch_all.get_internal_transactions') as mock_get:

        async def mock_implementation(**kwargs):
            call_count[0] += 1
            offset = kwargs.get('offset')
            page = kwargs.get('page', 1)
            offset_values_used.append((page, offset))

            # Page 1, first attempt: fail
            if page == 1 and offset == 10000:
                response = MagicMock()
                response.status_code = 502
                raise httpx.HTTPStatusError('Bad Gateway', request=MagicMock(), response=response)

            # Page 1, retry: succeed with reduced offset
            # Return exactly the expected offset (from paging engine's perspective: 10000)
            # to trigger page 2
            if page == 1 and offset == 5000:
                # Return 10000 items to make paging engine think there's more
                # (paging engine checks len(items) < effective_offset_for_provider where effective is 10000)
                return [
                    {
                        'hash': f'0xpage1_{i:060x}',
                        'blockNumber': str(1000 + i // 100),
                        'transactionIndex': str(i % 100),
                    }
                    for i in range(10000)  # Return MORE than reduced offset to trigger next page
                ]

            # Page 2: THIS IS THE KEY TEST
            # With bug: offset would reset to 10000, fail, retry at 5000
            # With fix: offset stays at 5000
            if page == 2:
                if offset == 10000:
                    # This means the bug is present!
                    pytest.fail(
                        f'YO-YO BUG DETECTED: Page 2 reset offset to {offset} instead of staying at 5000!'
                    )

                # With fix, we should get offset=5000 directly
                assert offset == 5000, f'Page 2 should use reduced offset=5000, got {offset}'
                return [
                    {
                        'hash': f'0xpage2_{i:060x}',
                        'blockNumber': str(2000),
                        'transactionIndex': str(i),
                    }
                    for i in range(100)
                ]

            return []

        mock_get.side_effect = mock_implementation

        mock_http = AsyncMock()
        mock_endpoint_builder = MagicMock()
        ctx = ProviderContext(
            api_kind='blockscout_base',
            network='base',
            api_key='',
            http=mock_http,
            endpoint_builder=mock_endpoint_builder,
        )

        result = await fetch_all_internal_basic(  # noqa: F841
            ctx=ctx,
            address='0x1234567890123456789012345678901234567890',
            start_block=None,
            end_block=None,
            max_offset=10000,
        )

        # With the fix, we should see:
        # (1, 10000) - page 1 initial attempt, fails
        # (1, 5000) - page 1 retry with reduced offset, succeeds
        # (2, 5000) - page 2 with PERSISTENT reduced offset (the fix!)

        assert (
            len(offset_values_used) == 3
        ), f'Expected 3 calls, got {len(offset_values_used)}: {offset_values_used}'
        assert offset_values_used[0] == (
            1,
            10000,
        ), 'First attempt should be page 1 with offset 10000'
        assert offset_values_used[1] == (
            1,
            5000,
        ), 'Retry should be page 1 with reduced offset 5000'
        assert offset_values_used[2] == (
            2,
            5000,
        ), f'BUG: Page 2 should use persistent offset 5000, got {offset_values_used[2]}'


@pytest.mark.asyncio
async def test_adaptive_offset_unified_fetch_multi_page():
    """Test yo-yo bug fix in unified_fetch with multiple pages."""

    offset_values_used = []

    with patch('aiochainscan.services.unified_fetch.get_internal_transactions') as mock_get:

        async def mock_implementation(**kwargs):
            offset = kwargs.get('offset')
            page = kwargs.get('page', 1)
            offset_values_used.append((page, offset))

            # Page 1: fail on first attempt
            if page == 1 and offset == 10000:
                response = MagicMock()
                response.status_code = 504
                raise httpx.HTTPStatusError(
                    'Gateway Timeout', request=MagicMock(), response=response
                )

            # Page 1 retry: succeed
            if page == 1 and offset == 5000:
                return [
                    {
                        'hash': f'0xp1_{i:062x}',
                        'blockNumber': str(1000 + i // 100),
                        'transactionIndex': str(i % 100),
                    }
                    for i in range(10000)
                ]

            # Page 2: should use persistent 5000, not reset to 10000
            if page == 2:
                if offset == 10000:
                    pytest.fail(f'YO-YO BUG in unified_fetch: Page 2 reset to {offset}!')
                assert offset == 5000
                return [
                    {
                        'hash': f'0xp2_{i:062x}',
                        'blockNumber': str(2000),
                        'transactionIndex': str(i),
                    }
                    for i in range(100)
                ]

            return []

        mock_get.side_effect = mock_implementation

        mock_http = AsyncMock()
        mock_endpoint_builder = MagicMock()
        ctx = ProviderContext(
            api_kind='blockscout_base',
            network='base',
            api_key='',
            http=mock_http,
            endpoint_builder=mock_endpoint_builder,
        )

        result = await fetch_all(  # noqa: F841
            ctx=ctx,
            data_type='internal_transactions',
            address='0x1234567890123456789012345678901234567890',
            start_block=None,
            end_block=None,
            strategy='basic',
            max_offset=10000,
        )

        assert len(offset_values_used) == 3
        assert offset_values_used[0] == (1, 10000)
        assert offset_values_used[1] == (1, 5000)
        assert offset_values_used[2] == (
            2,
            5000,
        ), f'Page 2 should persist offset 5000, got {offset_values_used[2]}'


@pytest.mark.asyncio
async def test_adaptive_offset_reduction_multiple_levels():
    """Verify offset can be reduced multiple times and stays at the final reduced value."""

    offset_values_used = []

    with patch('aiochainscan.services.fetch_all.get_internal_transactions') as mock_get:

        async def mock_implementation(**kwargs):
            offset = kwargs.get('offset')
            offset_values_used.append(offset)

            # Fail multiple times to trigger multiple reductions:
            # 10000 -> 5000 -> 2500 -> 1250 -> 1000 (minimum)
            if offset > 1250:
                response = MagicMock()
                response.status_code = 503
                raise httpx.HTTPStatusError(
                    'Service Unavailable', request=MagicMock(), response=response
                )

            # Once we're at 1250 or below, succeed
            if len(offset_values_used) <= 8:
                return [{'hash': f'0x{i:064x}', 'blockNumber': '1000'} for i in range(50)]

            return []

        mock_get.side_effect = mock_implementation

        mock_http = AsyncMock()
        mock_endpoint_builder = MagicMock()
        ctx = ProviderContext(
            api_kind='blockscout_base',
            network='base',
            api_key='',
            http=mock_http,
            endpoint_builder=mock_endpoint_builder,
        )

        result = await fetch_all_internal_basic(  # noqa: F841
            ctx=ctx,
            address='0x1234567890123456789012345678901234567890',
            start_block=None,
            end_block=None,
            max_offset=10000,
        )

        # Should see progression: 10000 -> 5000 -> 2500 -> 1250 (all fail), then 1250 succeeds
        # and all subsequent calls should use 1250
        assert 10000 in offset_values_used, 'Should start with 10000'
        assert 5000 in offset_values_used, 'Should reduce to 5000'
        assert 2500 in offset_values_used, 'Should reduce to 2500'
        assert 1250 in offset_values_used, 'Should reduce to 1250'

        # Find the first successful call (after reductions)
        # All subsequent calls should use the same reduced offset
        first_success_idx = None
        for i, offset in enumerate(offset_values_used):
            if offset == 1250:
                first_success_idx = i
                break

        assert first_success_idx is not None, 'Should find the first successful call at 1250'

        # Verify all subsequent calls use the final reduced offset
        subsequent_offsets = offset_values_used[first_success_idx + 1 :]
        if subsequent_offsets:  # If there were more calls after first success
            assert all(
                o == 1250 for o in subsequent_offsets
            ), f'All subsequent offsets should be 1250, but got {subsequent_offsets}'


@pytest.mark.asyncio
async def test_adaptive_offset_telemetry_logging(caplog):
    """Verify that offset reductions are logged via Python logging."""

    import logging

    # Set up logging capture at DEBUG level
    caplog.set_level(logging.DEBUG)

    with patch('aiochainscan.services.fetch_all.get_internal_transactions') as mock_get:

        async def mock_implementation(**kwargs):
            offset = kwargs.get('offset')
            page = kwargs.get('page', 1)  # noqa: F841

            # First call fails
            if offset == 10000:
                response = MagicMock()
                response.status_code = 502
                raise httpx.HTTPStatusError('Bad Gateway', request=MagicMock(), response=response)

            # Second call succeeds with partial data to end
            return [
                {'hash': f'0x{i:064x}', 'blockNumber': str(1000), 'transactionIndex': str(i)}
                for i in range(100)
            ]

        mock_get.side_effect = mock_implementation

        mock_http = AsyncMock()
        mock_endpoint_builder = MagicMock()
        ctx = ProviderContext(
            api_kind='blockscout_base',
            network='base',
            api_key='',
            http=mock_http,
            endpoint_builder=mock_endpoint_builder,
        )

        result = await fetch_all_internal_basic(  # noqa: F841
            ctx=ctx,
            address='0x1234567890123456789012345678901234567890',
            start_block=None,
            end_block=None,
            max_offset=10000,
        )

        # Verify logging was done (now via Python logging instead of telemetry)
        log_messages = [record.message for record in caplog.records]
        assert any(
            'adaptive_offset_reduction' in msg for msg in log_messages
        ), f'Should log adaptive offset reduction via Python logging, got: {log_messages}'
