import subprocess
import sys
from unittest.mock import patch

import pytest

from aiochainscan.decode import (
    _MIN_FASTABI_VERSION,
    FASTABI_AVAILABLE,
    _decode_transaction_input_fast,
    _decode_transaction_input_python,
    _parse_extension_version,
    _preprocess_abi,
    _require_strict_fastabi,
    canonical_abi_type,
    decode_log_data,
    decode_transaction_input,
    decode_transaction_input_with_function_name,
    generate_function_abi,
    keccak_hash,
)
from aiochainscan.exceptions import PureAbiDecodeWarning

# Check if eth-hash backend is available
try:
    from eth_utils import keccak

    keccak(b'test')
    ETH_HASH_AVAILABLE = True
except (ImportError, Exception):
    ETH_HASH_AVAILABLE = False


@pytest.mark.skipif(not ETH_HASH_AVAILABLE, reason='eth-hash backend not installed')
class TestKeccakHash:
    """Test keccak hash generation."""

    def test_keccak_hash_basic(self):
        """Test basic keccak hash generation."""
        text = 'transfer(address,uint256)'
        result = keccak_hash(text)

        assert isinstance(result, str)
        assert len(result) == 64  # 32 bytes = 64 hex chars

    def test_keccak_hash_empty_string(self):
        """Test keccak hash with empty string."""
        result = keccak_hash('')
        assert len(result) == 64

    def test_keccak_hash_unicode(self):
        """Test keccak hash with unicode characters."""
        result = keccak_hash('тест')
        assert len(result) == 64

    def test_keccak_hash_consistency(self):
        """Test that same input always produces same hash."""
        text = 'balanceOf(address)'
        hash1 = keccak_hash(text)
        hash2 = keccak_hash(text)
        assert hash1 == hash2


@pytest.mark.skipif(not ETH_HASH_AVAILABLE, reason='eth-hash backend not installed')
class TestGenerateFunctionAbi:
    """Test ABI generation from function signatures."""

    def test_generate_simple_function_abi(self):
        """Test generating ABI for simple function."""
        signature = 'transfer(address to, uint256 amount)'
        result = generate_function_abi(signature)

        expected = [
            {
                'type': 'function',
                'name': 'transfer',
                'inputs': [
                    {'type': 'address', 'name': 'to'},
                    {'type': 'uint256', 'name': 'amount'},
                ],
                'outputs': [],
                'stateMutability': 'nonpayable',
            }
        ]

        assert result == expected

    def test_generate_no_params_function_abi(self):
        """Test generating ABI for function with no parameters."""
        signature = 'totalSupply()'
        result = generate_function_abi(signature)

        expected = [
            {
                'type': 'function',
                'name': 'totalSupply',
                'inputs': [],
                'outputs': [],
                'stateMutability': 'nonpayable',
            }
        ]

        assert result == expected

    def test_generate_complex_function_abi(self):
        """Test generating ABI for function with complex types."""
        signature = 'swapExactTokensForTokens(uint256 amountIn, uint256 amountOutMin, address[] path, address to)'
        result = generate_function_abi(signature)

        expected = [
            {
                'type': 'function',
                'name': 'swapExactTokensForTokens',
                'inputs': [
                    {'type': 'uint256', 'name': 'amountIn'},
                    {'type': 'uint256', 'name': 'amountOutMin'},
                    {'type': 'address[]', 'name': 'path'},
                    {'type': 'address', 'name': 'to'},
                ],
                'outputs': [],
                'stateMutability': 'nonpayable',
            }
        ]

        assert result == expected

    def test_generate_nested_tuple_signature(self):
        result = generate_function_abi(
            'route((uint256 amount,(address recipient,bool unwrap)) route, uint[] hops)'
        )

        inputs = result[0]['inputs']
        assert canonical_abi_type(inputs[0]) == '(uint256,(address,bool))'
        assert inputs[0]['components'][1]['components'][1]['name'] == 'unwrap'
        assert canonical_abi_type(inputs[1]) == 'uint256[]'


@pytest.mark.skipif(not ETH_HASH_AVAILABLE, reason='eth-hash backend not installed')
class TestCanonicalAbiSelectors:
    def test_uint_alias_has_same_selector_as_uint256(self):
        uint_abi = [
            {'type': 'function', 'name': 'f', 'inputs': [{'type': 'uint', 'name': 'value'}]}
        ]
        uint256_abi = [
            {'type': 'function', 'name': 'f', 'inputs': [{'type': 'uint256', 'name': 'value'}]}
        ]

        assert set(_preprocess_abi(uint_abi)[0]) == set(_preprocess_abi(uint256_abi)[0])

    def test_tuple_selector_uses_components_and_array_suffix(self):
        abi = [
            {
                'type': 'function',
                'name': 'f',
                'inputs': [
                    {
                        'type': 'tuple[]',
                        'name': 'items',
                        'components': [
                            {'type': 'uint', 'name': 'amount'},
                            {
                                'type': 'tuple',
                                'name': 'meta',
                                'components': [
                                    {'type': 'address', 'name': 'owner'},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]

        function_map, _ = _preprocess_abi(abi)
        expected = '0x' + keccak_hash('f((uint256,(address))[])')[:8]
        assert expected in function_map


@pytest.mark.skipif(not ETH_HASH_AVAILABLE, reason='eth-hash backend not installed')
class TestDecodeTransactionInput:
    """Test transaction input decoding."""

    def setup_method(self):
        """Setup test data."""
        self.transfer_abi = [
            {
                'type': 'function',
                'name': 'transfer',
                'inputs': [
                    {'type': 'address', 'name': 'to'},
                    {'type': 'uint256', 'name': 'amount'},
                ],
            }
        ]

        # Mock transaction with transfer function call - ensure even length hex string
        self.transfer_transaction = {
            'input': '0xa9059cbb000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0000000000000000000000000000000000000000000000000de0b6b3a76400000',
            'blockNumber': '12345',
        }

    @patch('aiochainscan.decode._abi_decode_params')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_transaction_input_success(self, mock_keccak, mock_decode):
        """Test successful transaction input decoding."""
        # Setup mocks
        mock_keccak.return_value = (
            'a9059cbb00000000000000000000000000000000000000000000000000000000'
        )
        mock_decode.return_value = [
            '0x742d35cc6270c0532c0749334b1c1d434f4e86c0',  # address
            1000000000000000000,  # uint256
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
            'blockNumber': '12345',
        }

        result = decode_transaction_input(transaction, self.transfer_abi)

        assert result['decoded_func'] == ''
        assert result['decoded_data'] == {}

    @patch('aiochainscan.decode._abi_decode_params')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_transaction_input_with_bytes_conversion(self, mock_keccak, mock_decode):
        """Test transaction decoding with bytes conversion."""
        mock_keccak.return_value = (
            'a9059cbb00000000000000000000000000000000000000000000000000000000'
        )
        mock_decode.return_value = [
            b'\x74\x2d\x35\xcc\x62\x70\xc0\x53\x2c\x07\x49\x33\x4b\x1c\x1d\x43\x4f\x4e\x86\xc0',
            [b'\x12\x34\x00\x00', b'\x56\x78\x00\x00'],
        ]

        abi = [
            {
                'type': 'function',
                'name': 'testFunction',
                'inputs': [
                    {'type': 'bytes', 'name': 'data'},
                    {'type': 'bytes[]', 'name': 'dataArray'},
                ],
            }
        ]

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


_MISSING_INPUT = object()


def _tx_with_input(raw_input):
    """Build one transaction dict; the sentinel means no ``input`` key at all."""
    if raw_input is _MISSING_INPUT:
        return {'blockNumber': '12345'}
    return {'input': raw_input, 'blockNumber': '12345'}


class TestDecodeTransactionInputGuardBeforeAbiIndex:
    """The input-length guard fires before any ABI-derived work.

    An input that is missing, empty or shorter than a function selector can
    select nothing on any tier against any ABI, so every entry point must
    return the empty-marked transaction WITHOUT building the ABI index -- a
    structurally malformed ABI must not raise for undecodable input. That was
    the pre-C6 order (the guard sat at the top of each entry point, ahead of
    every ABI touch); C6 moved index construction to the call sites and let it
    run first. This pins the restored order at all three entry points.
    """

    @pytest.mark.parametrize(
        'entry_point',
        [
            decode_transaction_input,
            _decode_transaction_input_fast,
            _decode_transaction_input_python,
        ],
        ids=['public', 'fast', 'pure'],
    )
    @pytest.mark.parametrize(
        'abi',
        [
            pytest.param([None], id='abi-null-entry'),
            pytest.param(
                [{'type': 'function', 'name': 'f', 'inputs': 'x', 'outputs': []}],
                id='abi-inputs-not-a-list',
            ),
        ],
    )
    @pytest.mark.parametrize(
        'raw_input',
        [
            pytest.param('', id='input-empty'),
            pytest.param('0x', id='input-bare-0x'),
            pytest.param('0x1234', id='input-short'),
            pytest.param(None, id='input-none'),
            pytest.param(_MISSING_INPUT, id='input-missing'),
        ],
    )
    def test_short_input_short_circuits_before_the_abi_index(self, entry_point, abi, raw_input):
        """Empty/too-short input returns the empty mark; the ABI is never read."""
        transaction = _tx_with_input(raw_input)

        result = entry_point(transaction, abi)

        assert result['decoded_func'] == ''
        assert result['decoded_data'] == {}


class TestCalldataPrefixNormalization:
    """The hex prefix is optional and case-insensitive, on every tier.

    The Rust tier reaches ``bytes.fromhex`` either way, so calldata that
    decodes there must decode on the pure floor too: the floor used to cut its
    selector from a ``0x``-prefixed string and matched neither a prefixless
    input nor an uppercase ``0X``.
    """

    ABI = [
        {
            'type': 'function',
            'name': 'transfer',
            'inputs': [
                {'type': 'address', 'name': 'to'},
                {'type': 'uint256', 'name': 'amount'},
            ],
            'outputs': [],
        }
    ]
    BODY = 'a9059cbb' + '0' * 24 + '11' * 20 + f'{1500:064x}'

    @pytest.mark.parametrize(
        'raw_input',
        [
            pytest.param('0x' + BODY, id='prefixed'),
            pytest.param(BODY, id='prefixless'),
            pytest.param('0X' + BODY, id='uppercase-prefix'),
            pytest.param('0x' + BODY.upper(), id='uppercase-body'),
        ],
    )
    @pytest.mark.parametrize(
        'entry_point',
        [decode_transaction_input, _decode_transaction_input_python],
        ids=['public', 'pure'],
    )
    def test_every_spelling_decodes_identically(self, entry_point, raw_input):
        result = entry_point({'input': raw_input}, self.ABI)

        assert result['decoded_func'] == 'transfer'
        assert result['decoded_data'] == {
            'to': '0x1111111111111111111111111111111111111111',
            'amount': 1500,
        }

    def test_prefixless_zero_argument_calldata_is_not_rejected_as_too_short(self):
        abi = [{'type': 'function', 'name': 'ping', 'inputs': [], 'outputs': []}]
        selector = keccak_hash('ping()')[:8]

        result = decode_transaction_input({'input': selector}, abi)

        assert result['decoded_func'] == 'ping'
        assert result['decoded_data'] == {}


@pytest.mark.skipif(not ETH_HASH_AVAILABLE, reason='eth-hash backend not installed')
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
            'input': '0xa9059cbb...',
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
            'input': '0x095ea7b3...',
        }

        decode_transaction_input_with_function_name(transaction, signature_name='custom_signature')

        mock_generate_abi.assert_called_once_with('approve(address spender, uint256 amount)')


@pytest.mark.skipif(not ETH_HASH_AVAILABLE, reason='eth-hash backend not installed')
class TestDecodeLogData:
    """Test event log data decoding."""

    def setup_method(self):
        """Setup test data."""
        self.transfer_event_abi = [
            {
                'type': 'event',
                'name': 'Transfer',
                'inputs': [
                    {'type': 'address', 'name': 'from', 'indexed': True},
                    {'type': 'address', 'name': 'to', 'indexed': True},
                    {'type': 'uint256', 'name': 'value', 'indexed': False},
                ],
            }
        ]

        self.transfer_log = {
            'topics': [
                '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',  # Transfer event signature
                '0x000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0',  # from (indexed)
                '0x000000000000000000000000abc123def456789012345678901234567890abcd',  # to (indexed)
            ],
            'data': '0x000000000000000000000000000000000000000000000000de0b6b3a76400000',  # value (non-indexed)
        }

    @patch('aiochainscan.decode._abi_decode_params')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_log_data_success(self, mock_keccak, mock_decode):
        """Test successful log data decoding."""
        # Mock keccak hash for Transfer event
        mock_keccak.return_value = (
            'ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        )

        # Mock decode calls for indexed and non-indexed data
        mock_decode.side_effect = [
            ['0x742d35cc6270c0532c0749334b1c1d434f4e86c0'],  # from address
            ['0xabc123def456789012345678901234567890abcd'],  # to address
            [1000000000000000000],  # value
        ]

        log = self.transfer_log.copy()
        result = decode_log_data(log, self.transfer_event_abi)

        assert 'decoded_data' in result
        decoded = result['decoded_data']
        assert decoded['event'] == 'Transfer'
        assert decoded['from'] == '0x742d35cc6270c0532c0749334b1c1d434f4e86c0'
        assert decoded['to'] == '0xabc123def456789012345678901234567890abcd'
        assert decoded['value'] == 1000000000000000000

    @patch('aiochainscan.decode._abi_decode_params')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_log_data_stringifies_uint_above_i64(self, mock_keccak, mock_decode):
        mock_keccak.return_value = (
            'ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        )
        large_value = 2**63
        mock_decode.side_effect = [
            ['0x742d35cc6270c0532c0749334b1c1d434f4e86c0'],
            ['0xabc123def456789012345678901234567890abcd'],
            [large_value],
        ]

        result = decode_log_data(self.transfer_log.copy(), self.transfer_event_abi)

        assert result['decoded_data']['value'] == str(large_value)

    def test_decode_log_data_no_match(self):
        """Test log decoding when no event matches."""
        log = {
            'topics': ['0x1234567890abcdef'],
            'data': '0x0000000000000000000000000000000000000000000000000000000000000001',
        }

        result = decode_log_data(log, self.transfer_event_abi)

        # Should not have decoded_data if no match
        assert 'decoded_data' not in result

    @patch('aiochainscan.decode._abi_decode_params')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_log_data_with_bytes_conversion(self, mock_keccak, mock_decode):
        """Test log decoding with bytes data conversion."""
        mock_keccak.return_value = 'test_event_hash'
        mock_decode.side_effect = [
            [b'\x12\x34\x56\x78'],  # bytes data
            [],
        ]

        bytes_event_abi = [
            {
                'type': 'event',
                'name': 'BytesEvent',
                'inputs': [{'type': 'bytes32', 'name': 'data', 'indexed': True}],
            }
        ]

        log = {
            'topics': [
                '0xtest_event_hash',
                '0x1234567800000000000000000000000000000000000000000000000000000000',
            ],
            'data': '0x',
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

    @patch('aiochainscan.decode._abi_decode_params')
    @patch('aiochainscan.decode.keccak_hash')
    def test_decode_log_data_only_indexed_params(self, mock_keccak, mock_decode):
        """Test log decoding with only indexed parameters."""
        mock_keccak.return_value = 'approval_event_hash'
        mock_decode.side_effect = [
            ['0x742d35cc6270c0532c0749334b1c1d434f4e86c0'],  # owner
            ['0xabc123def456789012345678901234567890abcd'],  # spender
            [],  # Empty list for non-indexed params (empty data)
        ]

        approval_abi = [
            {
                'type': 'event',
                'name': 'Approval',
                'inputs': [
                    {'type': 'address', 'name': 'owner', 'indexed': True},
                    {'type': 'address', 'name': 'spender', 'indexed': True},
                ],
            }
        ]

        log = {
            'topics': [
                '0xapproval_event_hash',
                '0x000000000000000000000000742d35cc6270c0532c0749334b1c1d434f4e86c0',
                '0x000000000000000000000000abc123def456789012345678901234567890abcd',
            ],
            'data': '0x',
        }

        result = decode_log_data(log, approval_abi)

        assert 'decoded_data' in result
        decoded = result['decoded_data']
        assert decoded['event'] == 'Approval'
        assert decoded['owner'] == '0x742d35cc6270c0532c0749334b1c1d434f4e86c0'
        assert decoded['spender'] == '0xabc123def456789012345678901234567890abcd'

    def test_indexed_dynamic_topic_is_exposed_as_lowercase_hash(self):
        event_abi = [
            {
                'type': 'event',
                'name': 'Message',
                'inputs': [{'type': 'string', 'name': 'message', 'indexed': True}],
            }
        ]
        topic0 = '0x' + keccak_hash('Message(string)')
        raw_topic = '0x' + 'AB' * 32

        result = decode_log_data({'topics': [topic0, raw_topic], 'data': '0x'}, event_abi)

        assert result['decoded_data']['message'] == raw_topic.lower()

    @pytest.mark.parametrize(
        'parameter',
        [
            {'type': 'uint256[2]', 'name': 'values', 'indexed': True},
            {
                'type': 'tuple',
                'name': 'value',
                'indexed': True,
                'components': [{'type': 'uint256', 'name': 'amount'}],
            },
        ],
    )
    def test_indexed_composite_topic_is_exposed_as_hash(self, parameter):
        event_abi = [{'type': 'event', 'name': 'Composite', 'inputs': [parameter]}]
        topic0 = '0x' + keccak_hash(f'Composite({canonical_abi_type(parameter)})')
        raw_topic = '0x' + 'CD' * 32

        result = decode_log_data({'topics': [topic0, raw_topic], 'data': '0x'}, event_abi)

        assert result['decoded_data'][parameter['name']] == raw_topic.lower()

    @patch('aiochainscan.decode._abi_decode_params', return_value=(7,))
    def test_unique_anonymous_event_is_decoded(self, mock_decode):
        event_abi = [
            {
                'type': 'event',
                'name': 'AnonymousValue',
                'anonymous': True,
                'inputs': [{'type': 'uint256', 'name': 'value', 'indexed': True}],
            }
        ]
        result = decode_log_data({'topics': ['0x' + '00' * 31 + '07'], 'data': '0x'}, event_abi)

        assert result['decoded_data'] == {'event': 'AnonymousValue', 'value': 7}
        mock_decode.assert_called_once()

    def test_ambiguous_anonymous_events_remain_undecoded(self):
        event_inputs = [{'type': 'uint256', 'name': 'value', 'indexed': True}]
        event_abi = [
            {'type': 'event', 'name': 'First', 'anonymous': True, 'inputs': event_inputs},
            {'type': 'event', 'name': 'Second', 'anonymous': True, 'inputs': event_inputs},
        ]

        result = decode_log_data({'topics': ['0x' + '00' * 31 + '07'], 'data': '0x'}, event_abi)

        assert 'decoded_data' not in result


@pytest.mark.skipif(not ETH_HASH_AVAILABLE, reason='eth-hash backend not installed')
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


class TestFastabiVersionGate:
    """The Rust tier is refused unless it carries the strict decode semantics."""

    class _Ext:
        __file__ = '/tmp/aiochainscan_fastabi.so'

        def __init__(self, version=None):
            if version is not None:
                self.__version__ = version

    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            ('0.2.0', (0, 2, 0)),
            ('0.2.1', (0, 2, 1)),
            ('1.0', (1, 0)),
            ('0.2.0rc1', (0, 2, 0)),
            ('0.2.0.dev3', (0, 2, 0)),
            ('', None),
            ('abc', None),
            (None, None),
            (0.2, None),
        ],
    )
    def test_version_parsing(self, raw, expected):
        assert _parse_extension_version(raw) == expected

    @pytest.mark.parametrize('version', ['0.2.0', '0.2.1', '0.3.0', '1.0.0'])
    def test_strict_extension_accepted(self, version):
        _require_strict_fastabi(self._Ext(version))

    @pytest.mark.parametrize('version', [None, '0.1.0', '0.1.9', '0.0.1', 'garbage'])
    def test_stale_extension_refused(self, version):
        with (
            pytest.warns(PureAbiDecodeWarning, match='strict ABI decode semantics'),
            pytest.raises(ImportError),
        ):
            _require_strict_fastabi(self._Ext(version))

    def test_live_extension_satisfies_the_gate_when_available(self):
        """Whatever the suite decodes with must be the strict tier, not a stale build."""
        if not FASTABI_AVAILABLE:
            pytest.skip('fastabi extension not built')
        import aiochainscan.decode as decode_module

        live = _parse_extension_version(decode_module._fastabi.__version__)
        assert live is not None and live >= _MIN_FASTABI_VERSION


def test_stale_extension_leaves_the_import_block_on_the_pure_floor(tmp_path):
    """The gate is wired into the import, not merely importable: a pre-0.2.0
    extension must leave FASTABI_AVAILABLE False in a fresh interpreter."""
    script = tmp_path / 'stale.py'
    script.write_text(
        'import sys, types, warnings\n'
        "fake = types.ModuleType('aiochainscan_fastabi')\n"
        "fake.__version__ = '0.1.0'\n"
        "fake.__file__ = '/fake/aiochainscan_fastabi.so'\n"
        "sys.modules['aiochainscan_fastabi'] = fake\n"
        'with warnings.catch_warnings(record=True) as caught:\n'
        "    warnings.simplefilter('always')\n"
        '    import aiochainscan.decode as d\n'
        "print(d.FASTABI_AVAILABLE, d.ARROW_AVAILABLE, 'PureAbiDecodeWarning' in "
        '[type(w.message).__name__ for w in caught])\n'
    )
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=True
    )
    assert result.stdout.split() == ['False', 'False', 'True']
