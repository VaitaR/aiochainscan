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
            from aiochainscan.aiochainscan_fastabi import decode_input as fast_decode_input

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
            from aiochainscan.aiochainscan_fastabi import decode_input as fast_decode_input

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

    def test_direct_cache_identity_includes_parameter_names(self):
        from aiochainscan.decode import keccak_hash

        try:
            from aiochainscan.aiochainscan_fastabi import decode_one_direct
        except ImportError:
            pytest.skip('fastabi not available')

        selector = bytes.fromhex(keccak_hash('named(uint256)')[:8])
        calldata = selector + (7).to_bytes(32, 'big')
        abi_one = [
            {
                'type': 'function',
                'name': 'named',
                'inputs': [{'type': 'uint256', 'name': 'one'}],
                'outputs': [],
            }
        ]
        abi_two = [
            {
                'type': 'function',
                'name': 'named',
                'inputs': [{'type': 'uint256', 'name': 'two'}],
                'outputs': [],
            }
        ]

        first = json.loads(decode_one_direct(calldata, abi_one))
        second = json.loads(decode_one_direct(calldata, abi_two))

        assert first['decoded_data'] == {'one': 7}
        assert second['decoded_data'] == {'two': 7}

    def test_signed_int_json_matches_python_sign(self):
        from aiochainscan.decode import keccak_hash

        try:
            from aiochainscan.aiochainscan_fastabi import decode_input
        except ImportError:
            pytest.skip('fastabi not available')

        abi = [
            {
                'type': 'function',
                'name': 'signed',
                'inputs': [{'type': 'int8', 'name': 'value'}],
                'outputs': [],
            }
        ]
        selector = bytes.fromhex(keccak_hash('signed(int8)')[:8])
        calldata = selector + (b'\xff' * 32)
        decoded = json.loads(decode_input(calldata, json.dumps(abi)))

        assert decoded['decoded_data']['value'] == -1

    def test_arrow_string_column_contains_plain_decoded_string(self):
        try:
            import polars as pl

            from aiochainscan.aiochainscan_fastabi import decode_many_to_arrow
        except ImportError:
            pytest.skip('fastabi and polars are required')

        from aiochainscan.decode import keccak_hash

        value = 'quoted "text"'
        encoded_value = value.encode()
        encoded = (
            bytes.fromhex(keccak_hash('message(string)')[:8])
            + (32).to_bytes(32, 'big')
            + len(encoded_value).to_bytes(32, 'big')
            + encoded_value.ljust((len(encoded_value) + 31) // 32 * 32, b'\0')
        )
        abi = [
            {
                'type': 'function',
                'name': 'message',
                'inputs': [{'type': 'string', 'name': 'value'}],
                'outputs': [],
            }
        ]

        frame = pl.from_arrow(decode_many_to_arrow([encoded], json.dumps(abi)))

        assert frame['value'][0] == value


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
            from aiochainscan.aiochainscan_fastabi import decode_input as fast_decode_input

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
        # Benchmarks can be unstable on macOS CI runners; skip to avoid flaky failures.
        import sys

        if sys.platform == 'darwin':
            pytest.skip('fastabi performance benchmark is unstable on macOS runners')

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
        assert (
            improvement_ratio >= 10.0
        ), f'Expected 10x+ improvement, got {improvement_ratio:.2f}x'


class TestCompatibility:
    """Test compatibility between fastabi and Python implementations."""

    def test_identical_results(self):
        """Test that fastabi and Python produce identical results."""
        if not hasattr(self, 'fastabi_available'):
            try:
                from aiochainscan.aiochainscan_fastabi import decode_input as fast_decode_input

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


class TestGilRelease:
    """Test that GIL is properly released during Rust computation."""

    def test_all_functions_return_json_strings(self):
        """Verify all fastabi functions return JSON strings (not Python objects)."""
        try:
            from aiochainscan.aiochainscan_fastabi import (
                decode_input,
                decode_many,
                decode_many_flat,
                decode_many_hex,
                decode_many_raw,
                decode_one,
            )
        except ImportError:
            pytest.skip('fastabi not available')

        abi_json = json.dumps(TRANSFER_ABI)
        input_bytes = bytes.fromhex(TRANSFER_INPUT[2:])

        # All functions should return str (JSON)
        result = decode_input(input_bytes, abi_json)
        assert isinstance(result, str), f'decode_input returned {type(result)}, expected str'
        json.loads(result)  # Should be valid JSON

        result = decode_one(input_bytes, abi_json)
        assert isinstance(result, str), f'decode_one returned {type(result)}, expected str'
        json.loads(result)  # Should be valid JSON

        result = decode_many([input_bytes], abi_json)
        assert isinstance(result, str), f'decode_many returned {type(result)}, expected str'
        json.loads(result)  # Should be valid JSON

        result = decode_many_hex([TRANSFER_INPUT], abi_json)
        assert isinstance(result, str), f'decode_many_hex returned {type(result)}, expected str'
        json.loads(result)  # Should be valid JSON

        result = decode_many_raw([input_bytes], abi_json)
        assert isinstance(result, str), f'decode_many_raw returned {type(result)}, expected str'
        json.loads(result)  # Should be valid JSON

        result = decode_many_flat([input_bytes], abi_json)
        assert isinstance(result, str), f'decode_many_flat returned {type(result)}, expected str'
        json.loads(result)  # Should be valid JSON

    def test_batch_decode_large_batch_no_gil_blocking(self):
        """Test that large batch decoding doesn't block by creating Python objects in Rust."""
        try:
            from aiochainscan.aiochainscan_fastabi import decode_many
        except ImportError:
            pytest.skip('fastabi not available')

        import time

        abi_json = json.dumps(TRANSFER_ABI)
        input_bytes = bytes.fromhex(TRANSFER_INPUT[2:])

        # Create a large batch
        batch_size = 10000
        batch = [input_bytes] * batch_size

        # Time the decode
        start = time.perf_counter()
        result = decode_many(batch, abi_json)
        elapsed = time.perf_counter() - start

        # Verify result
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert len(parsed) == batch_size

        # Should complete reasonably fast (< 5 seconds for 10k items)
        # This would timeout if GIL was held during Python object creation
        assert elapsed < 5.0, f'Batch decode took {elapsed:.2f}s, expected < 5s'


def _extension():
    """The extension object decode.py actually bound, in either install layout.

    The library resolves the top-level ``aiochainscan_fastabi`` distribution
    first and the legacy ``aiochainscan.aiochainscan_fastabi`` second; tests
    must exercise whichever one is live, and skip when none is.
    """
    from aiochainscan import decode as decode_module

    if not decode_module.FASTABI_AVAILABLE:
        pytest.skip('fastabi extension not built')
    return decode_module._fastabi


class TestPanicSafety:
    """C1: ABI JSON is external data and ethabi's type-string reader panics on
    malformed types (a type of ``"]"`` underflows). The extension must turn
    that into a catchable Python exception — extension 1.0.0 aborted the whole
    interpreter here (exit 134, SIGABRT)."""

    BAD_TYPE_ABI = [
        {'type': 'function', 'name': 'f', 'inputs': [{'type': ']', 'name': 'x'}], 'outputs': []}
    ]

    def test_bad_abi_type_raises_instead_of_aborting_on_decode_input(self):
        ext = _extension()

        with pytest.raises(ValueError):
            ext.decode_input(bytes.fromhex('00000000' + '00' * 32), json.dumps(self.BAD_TYPE_ABI))

    def test_bad_abi_type_raises_instead_of_aborting_on_decode_one(self):
        ext = _extension()

        with pytest.raises(ValueError):
            ext.decode_one(bytes.fromhex('00000000' + '00' * 32), json.dumps(self.BAD_TYPE_ABI))

    def test_bad_abi_type_raises_instead_of_aborting_on_decode_many(self):
        ext = _extension()

        with pytest.raises(ValueError):
            ext.decode_many([bytes.fromhex('00000000' + '00' * 32)], json.dumps(self.BAD_TYPE_ABI))

    def test_bad_abi_type_stays_catchable_through_the_library_seam(self):
        """decode.py's tier switch must absorb the failure and end on the pure
        floor, which rejects the type with AbiTypeNotSupportedError."""
        from aiochainscan.decode import decode_transaction_input

        calldata = '0x00000000' + '00' * 32

        with pytest.raises(ValueError):
            decode_transaction_input({'input': calldata}, self.BAD_TYPE_ABI)


class TestUnnamedAndDuplicateNameConvention:
    """H1 on the Rust tier: one convention with the pure floor — unnamed
    inputs keyed ``param_{i}``, name collisions resolved first-keeps-plain /
    ``_2`` suffix (1.0.0 folded duplicates onto the last value)."""

    UNNAMED_ABI = [
        {
            'type': 'function',
            'name': 'transfer',
            'inputs': [{'type': 'address', 'name': ''}, {'type': 'uint256', 'name': ''}],
            'outputs': [],
        }
    ]

    def test_unnamed_params_are_keyed_param_i(self):
        ext = _extension()

        calldata = bytes.fromhex(
            'a9059cbb' + '00' * 12 + 'ab' * 20 + (5).to_bytes(32, 'big').hex()
        )
        decoded = json.loads(ext.decode_input(calldata, json.dumps(self.UNNAMED_ABI)))

        assert decoded['decoded_data'] == {'param_0': '0x' + 'ab' * 20, 'param_1': 5}

    def test_duplicate_names_first_keeps_the_plain_name(self):
        ext = _extension()

        abi = [
            {
                'type': 'function',
                'name': 'f',
                'inputs': [{'type': 'uint256', 'name': 'a'}, {'type': 'uint256', 'name': 'a'}],
                'outputs': [],
            }
        ]
        calldata = bytes.fromhex(
            '13d1aa2e' + (1).to_bytes(32, 'big').hex() + (2).to_bytes(32, 'big').hex()
        )
        decoded = json.loads(ext.decode_input(calldata, json.dumps(abi)))

        assert decoded['decoded_data'] == {'a': 1, 'a_2': 2}

    def test_unnamed_parity_with_the_pure_floor(self):
        from aiochainscan import decode as decode_module

        ext = _extension()

        calldata = bytes.fromhex(
            'a9059cbb' + '00' * 12 + 'ab' * 20 + (5).to_bytes(32, 'big').hex()
        )
        fast = json.loads(ext.decode_input(calldata, json.dumps(self.UNNAMED_ABI)))
        pure = decode_module._decode_transaction_input_python(
            {'input': '0x' + calldata.hex()}, self.UNNAMED_ABI
        )

        assert fast['decoded_data'] == pure['decoded_data']
        assert fast['function_name'] == pure['decoded_func']


class TestDecodeOneContract:
    """decode_one answers the empty-result contract of its siblings
    (decode_input, decode_many): an unknown selector or truncated calldata is
    an empty decode, not an exception."""

    def test_unknown_selector_returns_empty_result(self):
        ext = _extension()

        unknown = bytes.fromhex(
            '12345678000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0'
        )

        result = json.loads(ext.decode_one(unknown, json.dumps(TRANSFER_ABI)))

        assert result == {'function_name': '', 'decoded_data': {}}

    def test_truncated_calldata_returns_empty_result(self):
        ext = _extension()

        result = json.loads(
            ext.decode_one(bytes.fromhex('a9059cbb' + 'ab' * 10), json.dumps(TRANSFER_ABI))
        )

        assert result == {'function_name': '', 'decoded_data': {}}

    def test_decode_one_direct_returns_empty_result_on_unknown_selector(self):
        ext = _extension()

        unknown = bytes.fromhex(
            '12345678000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0'
        )

        result = json.loads(ext.decode_one_direct(unknown, TRANSFER_ABI))

        assert result == {'function_name': '', 'decoded_data': {}}

    def test_decode_one_agrees_with_decode_input_byte_for_byte(self):
        """Both release the GIL and share one contract; their answers must not
        drift (a previous draft of decode_one raised where this pins empty)."""
        ext = _extension()

        calldata = bytes.fromhex(TRANSFER_INPUT[2:])
        abi_json = json.dumps(TRANSFER_ABI)

        assert ext.decode_one(calldata, abi_json) == ext.decode_input(calldata, abi_json)
