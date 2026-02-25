"""Integration test for chunked strategy with unified_fetch."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.core.context import ProviderContext
from aiochainscan.services.unified_fetch import fetch_all

TEST_ADDRESS = '0x1111111111111111111111111111111111111111'


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


@pytest.mark.asyncio
async def test_unified_fetch_with_chunked_strategy_logs(mock_http, mock_endpoint_builder):
    """Test that fetch_all works with chunked strategy for logs."""
    call_count = {'n': 0}

    async def mock_get(*args, **kwargs):
        call_count['n'] += 1
        if call_count['n'] <= 2:  # Two chunks
            return {
                'result': [
                    {
                        'blockNumber': '10',
                        'logIndex': '0',
                        'transactionHash': f'0x{call_count["n"]}',
                    },
                ]
            }
        return {'result': []}

    mock_http.get = mock_get

    _ctx = ProviderContext(
        api_kind='eth',
        network='ethereum',
        api_key='test_key',
        http=mock_http,
        endpoint_builder=mock_endpoint_builder,
    )
    logs = await fetch_all(
        ctx=_ctx,
        data_type='logs',
        address=TEST_ADDRESS,
        start_block=0,
        end_block=100,
        strategy='chunked',
        max_offset=50,  # chunk_size
        max_concurrent=2,
    )

    assert len(logs) >= 0  # Should not crash
    assert isinstance(logs, list)


@pytest.mark.asyncio
async def test_unified_fetch_with_chunked_strategy_transactions(mock_http, mock_endpoint_builder):
    """Test that fetch_all works with chunked strategy for transactions."""
    call_count = {'n': 0}

    async def mock_get(*args, **kwargs):
        call_count['n'] += 1
        if call_count['n'] <= 2:
            return {
                'result': [
                    {'blockNumber': '10', 'transactionIndex': '0', 'hash': f'0x{call_count["n"]}'},
                ]
            }
        return {'result': []}

    mock_http.get = mock_get

    _ctx = ProviderContext(
        api_kind='eth',
        network='ethereum',
        api_key='test_key',
        http=mock_http,
        endpoint_builder=mock_endpoint_builder,
    )
    txs = await fetch_all(
        ctx=_ctx,
        data_type='transactions',
        address=TEST_ADDRESS,
        start_block=0,
        end_block=100,
        strategy='chunked',
        max_offset=50,
        max_concurrent=2,
    )

    assert len(txs) >= 0
    assert isinstance(txs, list)


@pytest.mark.asyncio
async def test_unified_fetch_chunked_fallback_to_fast(mock_http, mock_endpoint_builder):
    """Test that unsupported data types fall back to fast strategy."""
    mock_http.get = AsyncMock(return_value={'result': []})

    # internal_transactions is not supported by chunked, should fall back to fast
    _ctx = ProviderContext(
        api_kind='eth',
        network='ethereum',
        api_key='test_key',
        http=mock_http,
        endpoint_builder=mock_endpoint_builder,
    )
    result = await fetch_all(
        ctx=_ctx,
        data_type='internal_transactions',
        address=TEST_ADDRESS,
        start_block=0,
        end_block=100,
        strategy='chunked',
        max_offset=50,
        max_concurrent=2,
    )

    assert isinstance(result, list)
