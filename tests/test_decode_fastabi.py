"""Tests for fastabi Rust backend with fallback to Python implementation."""

import json
from unittest.mock import patch

import pytest

# Test data
TRANSFER_ABI = [
    {
        'type': 'function',
        'name': 'transfer',
        'inputs': [
            {'type': 'address', 'name': 'to'},
            {'type': 'uint256', 'name': 'amount'},
        ],
        'outputs': [{'type': 'bool', 'name': ''}],
        'stateMutability': 'nonpayable',
    }
]

TRANSFER_INPUT = '0xa9059cbb000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0000000000000000000000000000000000000000000000000de0b6b3a76400000'

EXPECTED_DECODED = {
    'function_name': 'transfer',
    'decoded_data': {
        'to': '0x742d35cc6270c0532c0749334b1c1d434f4e86c0',
        'amount': '16000000000000000000',
    },
}


class TestFastAbiAvailability:
    """Test fastabi module availability and fallback behavior."""

    def test_fastabi_import_success(self):
        """Test that fastabi can be imported when available."""
        try:
            from aiochainscan_fastabi import decode_input as fast_decode_input

            assert callable(fast_decode_input)
        except ImportError:
            pytest.skip('fastabi not available - expected for initial TDD')

    def test_fastabi_availability_flag(self):
        """Test FASTABI_AVAILABLE flag is set correctly."""
        from aiochainscan.decode import FASTABI_AVAILABLE

        # This will initially be False and become True after we implement the integration
        assert isinstance(FASTABI_AVAILABLE, bool)


class TestFastAbiDecoding:
    """Test fast ABI decoding functionality."""

    def setup_method(self):
        """Setup test data."""
        try:
            from aiochainscan_fastabi import decode_input as fast_decode_input

            self.fast_decode_input = fast_decode_input
            self.fastabi_available = True
        except ImportError:
            self.fastabi_available = False
            pytest.skip('fastabi not available')

    def test_decode_transfer_function(self):
        """Test decoding a transfer function call."""
        if not self.fastabi_available:
            pytest.skip('fastabi not available')

        abi_json = json.dumps(TRANSFER_ABI)
        input_bytes = bytes.fromhex(TRANSFER_INPUT[2:])  # Remove '0x' prefix

        result_json = self.fast_decode_input(input_bytes, abi_json)
        result = json.loads(result_json)

        assert result['function_name'] == EXPECTED_DECODED['function_name']
        assert result['decoded_data']['to'] == EXPECTED_DECODED['decoded_data']['to']
        assert result['decoded_data']['amount'] == EXPECTED_DECODED['decoded_data']['amount']

    def test_decode_empty_input(self):
        """Test decoding empty input data."""
        if not self.fastabi_available:
            pytest.skip('fastabi not available')

        abi_json = json.dumps(TRANSFER_ABI)
        input_bytes = b''

        result_json = self.fast_decode_input(input_bytes, abi_json)
        result = json.loads(result_json)

        assert result['function_name'] == ''
        assert result['decoded_data'] == {}

    def test_decode_unknown_function(self):
        """Test decoding input with unknown function selector."""
        if not self.fastabi_available:
            pytest.skip('fastabi not available')

        abi_json = json.dumps(TRANSFER_ABI)
        # Create input with unknown selector (0x12345678)
        unknown_input = bytes.fromhex(
            '12345678000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0'
        )

        result_json = self.fast_decode_input(unknown_input, abi_json)
        result = json.loads(result_json)

        assert result['function_name'] == ''
        assert result['decoded_data'] == {}

    def test_decode_invalid_abi(self):
        """Test error handling with invalid ABI JSON."""
        if not self.fastabi_available:
            pytest.skip('fastabi not available')

        input_bytes = bytes.fromhex(TRANSFER_INPUT[2:])
        invalid_abi = 'invalid json'

        with pytest.raises(ValueError):
            self.fast_decode_input(input_bytes, invalid_abi)


class TestIntegratedDecoding:
    """Test the integrated decoding functions with fastabi backend."""

    def test_decode_transaction_input_uses_fastabi(self):
        """Test that decode_transaction_input uses fastabi when available."""
        from aiochainscan.decode import decode_transaction_input

        transaction = {
            'input': TRANSFER_INPUT,
            'blockNumber': '12345',
        }

        # This test will initially fail until we implement the integration
        result = decode_transaction_input(transaction, TRANSFER_ABI)

        # Verify the result regardless of backend
        assert result['decoded_func'] == 'transfer'
        assert 'decoded_data' in result
        assert 'to' in result['decoded_data']
        assert 'amount' in result['decoded_data']

    def test_python_fallback_works(self):
        """Test that Python fallback works when fastabi is not available."""
        with patch('aiochainscan.decode.FASTABI_AVAILABLE', False):
            from aiochainscan.decode import decode_transaction_input

            transaction = {
                'input': TRANSFER_INPUT,
                'blockNumber': '12345',
            }

            result = decode_transaction_input(transaction, TRANSFER_ABI)

            # Should still work with Python implementation
            assert 'decoded_func' in result
            assert 'decoded_data' in result


class TestPerformanceBenchmarks:
    """Performance benchmarks comparing fastabi vs Python implementation."""

    def setup_method(self):
        """Setup test data for benchmarks."""
        try:
            from aiochainscan_fastabi import decode_input as fast_decode_input

            self.fast_decode_input = fast_decode_input
            self.fastabi_available = True
        except ImportError:
            self.fastabi_available = False

        # Create test data
        self.abi_json = json.dumps(TRANSFER_ABI)
        self.input_bytes = bytes.fromhex(TRANSFER_INPUT[2:])

        # Python implementation for comparison
        # Import directly to avoid dependency issues
        try:
            import os
            import sys

            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from aiochainscan.decode import _decode_transaction_input_python

            self.python_decode = _decode_transaction_input_python
        except ImportError:
            self.python_decode = None

        self.transaction = {
            'input': TRANSFER_INPUT,
            'blockNumber': '12345',
        }

    @pytest.mark.benchmark(group='decode_single')
    def test_benchmark_fastabi_single(self, benchmark):
        """Benchmark single transaction decoding with fastabi."""
        if not self.fastabi_available:
            pytest.skip('fastabi not available')

        def decode_with_fastabi():
            return self.fast_decode_input(self.input_bytes, self.abi_json)

        result = benchmark(decode_with_fastabi)
        decoded = json.loads(result)
        assert decoded['function_name'] == 'transfer'

    @pytest.mark.benchmark(group='decode_single')
    def test_benchmark_python_single(self, benchmark):
        """Benchmark single transaction decoding with Python."""

        def decode_with_python():
            return self.python_decode(self.transaction.copy(), TRANSFER_ABI)

        result = benchmark(decode_with_python)
        assert result['decoded_func'] == 'transfer'

    @pytest.mark.benchmark(group='decode_batch')
    def test_benchmark_fastabi_batch(self, benchmark):
        """Benchmark batch transaction decoding with fastabi."""
        if not self.fastabi_available:
            pytest.skip('fastabi not available')

        def decode_batch_fastabi():
            results = []
            for _ in range(100):
                result = self.fast_decode_input(self.input_bytes, self.abi_json)
                results.append(json.loads(result))
            return results

        results = benchmark(decode_batch_fastabi)
        assert len(results) == 100
        assert all(r['function_name'] == 'transfer' for r in results)

    @pytest.mark.benchmark(group='decode_batch')
    def test_benchmark_python_batch(self, benchmark):
        """Benchmark batch transaction decoding with Python."""

        def decode_batch_python():
            results = []
            for _ in range(100):
                result = self.python_decode(self.transaction.copy(), TRANSFER_ABI)
                results.append(result)
            return results

        results = benchmark(decode_batch_python)
        assert len(results) == 100
        assert all(r['decoded_func'] == 'transfer' for r in results)

    def test_performance_improvement(self):
        """Test that fastabi provides significant performance improvement."""
        if not self.fastabi_available:
            pytest.skip('fastabi not available')

        import time

        # Time Python implementation
        start = time.perf_counter()
        for _ in range(100):
            self.python_decode(self.transaction.copy(), TRANSFER_ABI)
        python_time = time.perf_counter() - start

        # Time fastabi implementation
        start = time.perf_counter()
        for _ in range(100):
            self.fast_decode_input(self.input_bytes, self.abi_json)
        fastabi_time = time.perf_counter() - start

        # fastabi should be significantly faster (at least 10x)
        improvement_ratio = python_time / fastabi_time
        assert improvement_ratio >= 10.0, (
            f'Expected 10x+ improvement, got {improvement_ratio:.2f}x'
        )


class TestCompatibility:
    """Test compatibility between fastabi and Python implementations."""

    def test_identical_results(self):
        """Test that fastabi and Python produce identical results."""
        if not hasattr(self, 'fastabi_available'):
            try:
                from aiochainscan_fastabi import decode_input as fast_decode_input

                self.fast_decode_input = fast_decode_input
                self.fastabi_available = True
            except ImportError:
                pytest.skip('fastabi not available')

        from aiochainscan.decode import decode_transaction_input

        # Test data
        transaction = {
            'input': TRANSFER_INPUT,
            'blockNumber': '12345',
        }

        # Python result
        python_result = decode_transaction_input(transaction.copy(), TRANSFER_ABI)

        # Fastabi result
        abi_json = json.dumps(TRANSFER_ABI)
        input_bytes = bytes.fromhex(TRANSFER_INPUT[2:])
        fastabi_result_json = self.fast_decode_input(input_bytes, abi_json)
        fastabi_result = json.loads(fastabi_result_json)

        # Compare results
        assert python_result['decoded_func'] == fastabi_result['function_name']

        # Compare decoded data (accounting for potential type differences)
        for key, value in python_result['decoded_data'].items():
            assert key in fastabi_result['decoded_data']
            # Convert both to string for comparison (fastabi returns strings)
            assert str(value) == str(fastabi_result['decoded_data'][key])
