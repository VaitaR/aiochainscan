from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.decode import decode_input_with_online_lookup, sig_db


@pytest.fixture(autouse=True)
def clear_sig_cache():
    """Clear the signature database cache before each test."""
    sig_db.cache.clear()
    yield
    sig_db.cache.clear()


class TestDecodeOnline:
    @pytest.mark.asyncio
    async def test_decode_with_online_lookup_success(self):
        # Mock the HttpClient
        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(
            return_value={
                'count': 1,
                'next': None,
                'previous': None,
                'results': [
                    {
                        'id': 1,
                        'created_at': '2018-05-11T19:42:04.281044Z',
                        'text_signature': 'transfer(address,uint256)',
                        'hex_signature': '0xa9059cbb',
                        'bytes_signature': 'a(E..{',
                    }
                ],
            }
        )

        # Sample transaction
        transaction = {
            'input': '0xa9059cbb00000000000000000000000095227777777777777777777777777777777777770000000000000000000000000000000000000000000000000000000000000001'
        }

        decoded_tx = await decode_input_with_online_lookup(transaction, mock_http_client)

        assert decoded_tx['decoded_func'] == 'transfer'
        assert 'decoded_data' in decoded_tx
        assert len(decoded_tx['decoded_data']) == 2
        assert (
            decoded_tx['decoded_data']['param_0'] == '0x9522777777777777777777777777777777777777'
        )
        assert decoded_tx['decoded_data']['param_1'] == 1

    @pytest.mark.asyncio
    async def test_decode_with_online_lookup_not_found(self):
        # Mock the HttpClient with "not found" response
        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(
            return_value={
                'count': 0,
                'next': None,
                'previous': None,
                'results': [],
            }
        )

        # Sample transaction with an unknown selector
        transaction = {
            'input': '0xdeadbeef00000000000000000000000095227777777777777777777777777777777777770000000000000000000000000000000000000000000000000000000000000001'
        }

        decoded_tx = await decode_input_with_online_lookup(transaction, mock_http_client)
        assert decoded_tx['decoded_func'] == ''
        assert decoded_tx['decoded_data'] == {}

    @pytest.mark.asyncio
    async def test_decode_with_online_lookup_request_error(self):
        # Mock a network error
        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(side_effect=Exception('Network error'))

        # Sample transaction
        transaction = {
            'input': '0xa9059cbb00000000000000000000000095227777777777777777777777777777777777770000000000000000000000000000000000000000000000000000000000000001'
        }

        decoded_tx = await decode_input_with_online_lookup(transaction, mock_http_client)
        assert decoded_tx['decoded_func'] == ''
        assert decoded_tx['decoded_data'] == {}

    @pytest.mark.asyncio
    async def test_decode_with_online_lookup_no_input(self):
        transaction = {'input': ''}

        # Mock http client - won't be called
        mock_http_client = MagicMock()

        decoded_tx = await decode_input_with_online_lookup(transaction, mock_http_client)
        assert decoded_tx['decoded_func'] == ''
        assert decoded_tx['decoded_data'] == {}

    @pytest.mark.asyncio
    async def test_decode_with_online_lookup_short_input(self):
        transaction = {'input': '0xa9059c'}

        # Mock http client - won't be called
        mock_http_client = MagicMock()

        decoded_tx = await decode_input_with_online_lookup(transaction, mock_http_client)
        assert decoded_tx['decoded_func'] == ''
        assert decoded_tx['decoded_data'] == {}
