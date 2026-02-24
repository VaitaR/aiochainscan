"""Integration test to verify async decode_input_with_online_lookup works with real HTTP client."""

import pytest

from aiochainscan.adapters.httpx_client import HttpxClientAdapter
from aiochainscan.decode import decode_input_with_online_lookup


@pytest.mark.integration
@pytest.mark.asyncio
async def test_decode_with_online_lookup_real_api():
    """Test decode_input_with_online_lookup with real 4byte.directory API."""
    # Sample transaction with transfer(address,uint256) - selector 0xa9059cbb
    transaction = {
        'input': '0xa9059cbb00000000000000000000000095227777777777777777777777777777777777770000000000000000000000000000000000000000000000000000000000000001'
    }

    async with HttpxClientAdapter() as http_client:
        decoded_tx = await decode_input_with_online_lookup(transaction, http_client)

        # Verify the function was decoded (4byte.directory may return different matches)
        # The important thing is that it decoded SOMETHING and parsed correctly
        assert decoded_tx['decoded_func'] != ''
        assert 'decoded_data' in decoded_tx
        # Should have 2 parameters for any function with selector 0xa9059cbb
        assert len(decoded_tx['decoded_data']) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_decode_with_online_lookup_caching():
    """Test that signature database caching works correctly."""
    transaction = {
        'input': '0xa9059cbb00000000000000000000000095227777777777777777777777777777777777770000000000000000000000000000000000000000000000000000000000000001'
    }

    async with HttpxClientAdapter() as http_client:
        # First call - should fetch from API
        decoded_tx1 = await decode_input_with_online_lookup(transaction, http_client)

        # Second call with same selector - should use cache (no API call)
        decoded_tx2 = await decode_input_with_online_lookup(transaction, http_client)

        # Both should have the same result
        assert decoded_tx1['decoded_func'] == decoded_tx2['decoded_func']
        assert decoded_tx1['decoded_data'] == decoded_tx2['decoded_data']
