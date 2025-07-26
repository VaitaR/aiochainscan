from unittest.mock import patch

from aiochainscan.decode import (
    decode_log_data,
    decode_transaction_input,
    decode_transaction_input_with_function_name,
    generate_function_abi,
    keccak_hash,
)


class TestKeccakHash:
    """Test keccak hash generation."""

    def test_keccak_hash_basic(self):
        """Test basic keccak hash generation."""
        text = "transfer(address,uint256)"
        result = keccak_hash(text)

        assert isinstance(result, str)
        assert len(result) == 64  # 32 bytes = 64 hex chars

    def test_keccak_hash_empty_string(self):
        """Test keccak hash with empty string."""
        result = keccak_hash("")
        assert len(result) == 64

    def test_keccak_hash_unicode(self):
        """Test keccak hash with unicode characters."""
        result = keccak_hash("тест")
        assert len(result) == 64

    def test_keccak_hash_consistency(self):
        """Test that same input always produces same hash."""
        text = "balanceOf(address)"
        hash1 = keccak_hash(text)
        hash2 = keccak_hash(text)
        assert hash1 == hash2


class TestGenerateFunctionAbi:
    """Test ABI generation from function signatures."""

    def test_generate_simple_function_abi(self):
        """Test generating ABI for simple function."""
        signature = "transfer(address to, uint256 amount)"
        result = generate_function_abi(signature)

        expected = [{
            'type': 'function',
            'name': 'transfer',
            'inputs': [
                {'type': 'address', 'name': 'to'},
                {'type': 'uint256', 'name': 'amount'}
            ],
            'outputs': [],
            'stateMutability': 'nonpayable'
        }]

        assert result == expected

    def test_generate_no_params_function_abi(self):
        """Test generating ABI for function with no parameters."""
        signature = "totalSupply()"
        result = generate_function_abi(signature)

        expected = [{
            'type': 'function',
            'name': 'totalSupply',
            'inputs': [],
            'outputs': [],
            'stateMutability': 'nonpayable'
        }]

        assert result == expected

    def test_generate_complex_function_abi(self):
        """Test generating ABI for function with complex types."""
        signature = "swapExactTokensForTokens(uint256 amountIn, uint256 amountOutMin, address[] path, address to)"
        result = generate_function_abi(signature)

        expected = [{
            'type': 'function',
            'name': 'swapExactTokensForTokens',
            'inputs': [
                {'type': 'uint256', 'name': 'amountIn'},
                {'type': 'uint256', 'name': 'amountOutMin'},
                {'type': 'address[]', 'name': 'path'},
                {'type': 'address', 'name': 'to'}
            ],
            'outputs': [],
            'stateMutability': 'nonpayable'
        }]

        assert result == expected


class TestDecodeTransactionInput:
    """Test transaction input decoding."""

    def setup_method(self):
        """Setup test data."""
        self.transfer_abi = [{
            'type': 'function',
            'name': 'transfer',
            'inputs': [
                {'type': 'address', 'name': 'to'},
                {'type': 'uint256', 'name': 'amount'}
            ]
        }]

        # Mock transaction with transfer function call - ensure even length hex string
        self.transfer_transaction = {
            'input': '0xa9059cbb000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0000000000000000000000000000000000000000000000000de0b6b3a76400000',
            'blockNumber': '12345'
        }

    @patch('aiochainscan.decode.decode')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_transaction_input_success(self, mock_keccak, mock_decode):
        """Test successful transaction input decoding."""
        # Setup mocks
        mock_keccak.return_value = 'a9059cbb00000000000000000000000000000000000000000000000000000000'
        mock_decode.return_value = [
            '0x742d35cc6270c0532c0749334b1c1d434f4e86c0',  # address
            1000000000000000000  # uint256
        ]

        transaction = self.transfer_transaction.copy()
        result = decode_transaction_input(transaction, self.transfer_abi)

        assert result['decoded_func'] == 'transfer'
        assert 'decoded_data' in result
        assert result['decoded_data']['to'] == '0x742d35cc6270c0532c0749334b1c1d434f4e86c0'
        assert result['decoded_data']['amount'] == 1000000000000000000

    def test_decode_transaction_input_no_match(self):
        """Test transaction input decoding when no function matches."""
        transaction = {
            'input': '0x12345678000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0',
            'blockNumber': '12345'
        }

        result = decode_transaction_input(transaction, self.transfer_abi)

        assert result['decoded_func'] == ''
        assert result['decoded_data'] == {}

    @patch('aiochainscan.decode.decode')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_transaction_input_with_bytes_conversion(self, mock_keccak, mock_decode):
        """Test transaction decoding with bytes conversion."""
        mock_keccak.return_value = 'a9059cbb00000000000000000000000000000000000000000000000000000000'
        mock_decode.return_value = [
            b'\x74\x2d\x35\xcc\x62\x70\xc0\x53\x2c\x07\x49\x33\x4b\x1c\x1d\x43\x4f\x4e\x86\xc0',
            [b'\x12\x34\x00\x00', b'\x56\x78\x00\x00']
        ]

        abi = [{
            'type': 'function',
            'name': 'testFunction',
            'inputs': [
                {'type': 'bytes', 'name': 'data'},
                {'type': 'bytes[]', 'name': 'dataArray'}
            ]
        }]

        transaction = self.transfer_transaction.copy()
        result = decode_transaction_input(transaction, abi)

        assert result['decoded_func'] == 'testFunction'
        # Check bytes conversion
        assert isinstance(result['decoded_data']['data'], str)
        assert isinstance(result['decoded_data']['dataArray'], list)

    def test_decode_transaction_input_empty_abi(self):
        """Test transaction decoding with empty ABI."""
        transaction = self.transfer_transaction.copy()
        result = decode_transaction_input(transaction, [])

        assert result['decoded_func'] == ''
        assert result['decoded_data'] == {}


class TestDecodeTransactionInputWithFunctionName:
    """Test transaction decoding using function name signature."""

    @patch('aiochainscan.decode.decode_transaction_input')
    @patch('aiochainscan.decode.generate_function_abi')
    def test_decode_with_function_name(self, mock_generate_abi, mock_decode_input):
        """Test decoding transaction using function name."""
        mock_abi = [{'type': 'function', 'name': 'transfer'}]
        mock_generate_abi.return_value = mock_abi
        mock_decode_input.return_value = {'decoded_func': 'transfer', 'decoded_data': {}}

        transaction = {
            'function_name': 'transfer(address to, uint256 amount)',
            'input': '0xa9059cbb...'
        }

        decode_transaction_input_with_function_name(transaction)

        mock_generate_abi.assert_called_once_with('transfer(address to, uint256 amount)')
        mock_decode_input.assert_called_once_with(transaction, mock_abi)

    @patch('aiochainscan.decode.decode_transaction_input')
    @patch('aiochainscan.decode.generate_function_abi')
    def test_decode_with_custom_signature_name(self, mock_generate_abi, mock_decode_input):
        """Test decoding with custom signature field name."""
        mock_abi = [{'type': 'function', 'name': 'approve'}]
        mock_generate_abi.return_value = mock_abi
        mock_decode_input.return_value = {'decoded_func': 'approve', 'decoded_data': {}}

        transaction = {
            'custom_signature': 'approve(address spender, uint256 amount)',
            'input': '0x095ea7b3...'
        }

        decode_transaction_input_with_function_name(
            transaction,
            signature_name='custom_signature'
        )

        mock_generate_abi.assert_called_once_with('approve(address spender, uint256 amount)')


class TestDecodeLogData:
    """Test event log data decoding."""

    def setup_method(self):
        """Setup test data."""
        self.transfer_event_abi = [{
            'type': 'event',
            'name': 'Transfer',
            'inputs': [
                {'type': 'address', 'name': 'from', 'indexed': True},
                {'type': 'address', 'name': 'to', 'indexed': True},
                {'type': 'uint256', 'name': 'value', 'indexed': False}
            ]
        }]

        self.transfer_log = {
            'topics': [
                '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',  # Transfer event signature
                '0x000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0',  # from (indexed)
                '0x000000000000000000000000abc123def456789012345678901234567890abcd'   # to (indexed)
            ],
            'data': '0x000000000000000000000000000000000000000000000000de0b6b3a76400000'  # value (non-indexed)
        }

    @patch('aiochainscan.decode.decode')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_log_data_success(self, mock_keccak, mock_decode):
        """Test successful log data decoding."""
        # Mock keccak hash for Transfer event
        mock_keccak.return_value = 'ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        # Mock decode calls for indexed and non-indexed data
        mock_decode.side_effect = [
            ['0x742d35cc6270c0532c0749334b1c1d434f4e86c0'],  # from address
            ['0xabc123def456789012345678901234567890abcd'],   # to address
            [1000000000000000000]                             # value
        ]

        log = self.transfer_log.copy()
        result = decode_log_data(log, self.transfer_event_abi)

        assert 'decoded_data' in result
        decoded = result['decoded_data']
        assert decoded['event'] == 'Transfer'
        assert decoded['from'] == '0x742d35cc6270c0532c0749334b1c1d434f4e86c0'
        assert decoded['to'] == '0xabc123def456789012345678901234567890abcd'
        assert decoded['value'] == 1000000000000000000

    def test_decode_log_data_no_match(self):
        """Test log decoding when no event matches."""
        log = {
            'topics': ['0x1234567890abcdef'],
            'data': '0x0000000000000000000000000000000000000000000000000000000000000001'
        }

        result = decode_log_data(log, self.transfer_event_abi)

        # Should not have decoded_data if no match
        assert 'decoded_data' not in result

    @patch('aiochainscan.decode.decode')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_log_data_with_bytes_conversion(self, mock_keccak, mock_decode):
        """Test log decoding with bytes data conversion."""
        mock_keccak.return_value = 'test_event_hash'
        mock_decode.side_effect = [
            [b'\x12\x34\x56\x78'],  # bytes data
            []
        ]

        bytes_event_abi = [{
            'type': 'event',
            'name': 'BytesEvent',
            'inputs': [
                {'type': 'bytes32', 'name': 'data', 'indexed': True}
            ]
        }]

        log = {
            'topics': ['0xtest_event_hash', '0x1234567800000000000000000000000000000000000000000000000000000000'],
            'data': '0x'
        }

        result = decode_log_data(log, bytes_event_abi)

        assert 'decoded_data' in result
        # Check that bytes are converted to hex string
        assert isinstance(result['decoded_data']['data'], str)

    def test_decode_log_data_empty_abi(self):
        """Test log decoding with empty ABI."""
        log = self.transfer_log.copy()
        result = decode_log_data(log, [])

        assert 'decoded_data' not in result

    @patch('aiochainscan.decode.decode')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_log_data_only_indexed_params(self, mock_keccak, mock_decode):
        """Test log decoding with only indexed parameters."""
        mock_keccak.return_value = 'approval_event_hash'
        mock_decode.side_effect = [
            ['0x742d35cc6270c0532c0749334b1c1d434f4e86c0'],  # owner
            ['0xabc123def456789012345678901234567890abcd'],   # spender
            []  # Empty list for non-indexed params (empty data)
        ]

        approval_abi = [{
            'type': 'event',
            'name': 'Approval',
            'inputs': [
                {'type': 'address', 'name': 'owner', 'indexed': True},
                {'type': 'address', 'name': 'spender', 'indexed': True}
            ]
        }]

        log = {
            'topics': [
                '0xapproval_event_hash',
                '0x000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0',
                '0x000000000000000000000000abc123def456789012345678901234567890abcd'
            ],
            'data': '0x'
        }

        result = decode_log_data(log, approval_abi)

        assert 'decoded_data' in result
        decoded = result['decoded_data']
        assert decoded['event'] == 'Approval'
        assert decoded['owner'] == '0x742d35cc6270c0532c0749334b1c1d434f4e86c0'
        assert decoded['spender'] == '0xabc123def456789012345678901234567890abcd'


class TestDecodeIntegration:
    """Integration tests for decode functionality."""

    def test_full_transaction_decode_workflow(self):
        """Test complete transaction decoding workflow."""
        # This would be an integration test with real ABI and transaction data
        pass

    def test_full_log_decode_workflow(self):
        """Test complete log decoding workflow."""
        # This would be an integration test with real ABI and log data
        pass

    def test_decode_error_handling(self):
        """Test error handling in decode functions."""
        # Test various error scenarios
        pass
