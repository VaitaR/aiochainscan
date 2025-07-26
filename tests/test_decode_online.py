import unittest
from unittest.mock import Mock, patch

import requests

from aiochainscan.decode import decode_input_with_online_lookup


class TestDecodeOnline(unittest.TestCase):
    @patch('aiochainscan.decode.requests.get')
    def test_decode_with_online_lookup_success(self, mock_get):
        # Mock the API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
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
        mock_get.return_value = mock_response

        # Sample transaction
        transaction = {
            'input': '0xa9059cbb00000000000000000000000095227777777777777777777777777777777777770000000000000000000000000000000000000000000000000000000000000001'
        }

        decoded_tx = decode_input_with_online_lookup(transaction)

        self.assertEqual(decoded_tx['decoded_func'], 'transfer')
        self.assertIn('decoded_data', decoded_tx)
        self.assertEqual(len(decoded_tx['decoded_data']), 2)
        self.assertEqual(
            decoded_tx['decoded_data']['param_0'], '0x9522777777777777777777777777777777777777'
        )
        self.assertEqual(decoded_tx['decoded_data']['param_1'], 1)

    @patch('aiochainscan.decode.requests.get')
    def test_decode_with_online_lookup_not_found(self, mock_get):
        # Mock the API response for "not found"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'count': 0,
            'next': None,
            'previous': None,
            'results': [],
        }
        mock_get.return_value = mock_response

        # Sample transaction with an unknown selector
        transaction = {
            'input': '0xdeadbeef00000000000000000000000095227777777777777777777777777777777777770000000000000000000000000000000000000000000000000000000000000001'
        }

        decoded_tx = decode_input_with_online_lookup(transaction)
        self.assertEqual(decoded_tx['decoded_func'], '')
        self.assertEqual(decoded_tx['decoded_data'], {})

    @patch('aiochainscan.decode.requests.get')
    def test_decode_with_online_lookup_request_error(self, mock_get):
        # Mock a network error
        mock_get.side_effect = requests.exceptions.RequestException

        # Sample transaction
        transaction = {
            'input': '0xa9059cbb00000000000000000000000095227777777777777777777777777777777777770000000000000000000000000000000000000000000000000000000000000001'
        }

        decoded_tx = decode_input_with_online_lookup(transaction)
        self.assertEqual(decoded_tx['decoded_func'], '')
        self.assertEqual(decoded_tx['decoded_data'], {})

    def test_decode_with_online_lookup_no_input(self):
        transaction = {'input': ''}
        decoded_tx = decode_input_with_online_lookup(transaction)
        self.assertEqual(decoded_tx['decoded_func'], '')
        self.assertEqual(decoded_tx['decoded_data'], {})

    def test_decode_with_online_lookup_short_input(self):
        transaction = {'input': '0xa9059c'}
        decoded_tx = decode_input_with_online_lookup(transaction)
        self.assertEqual(decoded_tx['decoded_func'], '')
        self.assertEqual(decoded_tx['decoded_data'], {})


if __name__ == '__main__':
    unittest.main()
