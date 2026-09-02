"""The pure-Python ABI decode floor: correctness, tier parity, speed.

Three oracles, in decreasing order of independence: hand-written calldata with
known values, ``eth_abi`` (cross-checked round-trips), and the decode tiers
against each other. The tier-parity tests are the point of the exercise — a
base install and an ``aiochainscan[fallback]`` install must not disagree about
what a transaction says.
"""

from typing import Any

import pytest

from aiochainscan import decode as decode_module
from aiochainscan.abi_pure import (
    TypeNode,
    compile_params,
    decode_arguments,
    decode_values,
    encode_arguments,
)
from aiochainscan.decode import (
    ETH_ABI_AVAILABLE,
    FASTABI_AVAILABLE,
    canonical_abi_type,
    decode_log_data,
    decode_transaction_input,
    keccak_hash,
)
from aiochainscan.exceptions import AbiTypeNotSupportedError

requires_eth_abi = pytest.mark.skipif(not ETH_ABI_AVAILABLE, reason='eth-abi not installed')

# (id, params, values) — values in the encoder's native form.
VECTORS: list[tuple[str, list[dict[str, Any]], list[Any]]] = [
    ('scalars', [{'type': 'uint256'}, {'type': 'address'}], [2**255 - 1, '0x' + 'ab' * 20]),
    ('signed_extremes', [{'type': 'int8'}, {'type': 'int256'}], [-128, -(2**255)]),
    (
        'bool_bytes',
        [{'type': 'bool'}, {'type': 'bytes4'}, {'type': 'bytes'}],
        [True, b'\xde\xad\xbe\xef', b'\x00' * 70],
    ),
    ('unicode_string', [{'type': 'string'}], ['ключ ' * 20]),
    ('empty_string', [{'type': 'string'}], ['']),
    ('dynamic_array', [{'type': 'uint256[]'}], [[1, 2, 3, 2**200]]),
    ('empty_array', [{'type': 'uint256[]'}], [[]]),
    ('fixed_array', [{'type': 'uint256[3]'}], [[7, 8, 9]]),
    ('dynamic_elem_array', [{'type': 'bytes[]'}], [[b'a', b'bb' * 40, b'']]),
    ('fixed_array_of_dynamic', [{'type': 'string[2]'}], [['x', 'y' * 100]]),
    ('nested_array', [{'type': 'uint256[][2]'}], [[[1, 2], [3]]]),
    (
        'named_tuple',
        [
            {
                'type': 'tuple',
                'components': [{'type': 'uint256', 'name': 'a'}, {'type': 'bytes', 'name': 'b'}],
            }
        ],
        [(5, b'\x01\x02')],
    ),
    (
        'tuple_array',
        [
            {
                'type': 'tuple[]',
                'components': [{'type': 'address', 'name': 'a'}, {'type': 'uint8', 'name': 'b'}],
            }
        ],
        [[('0x' + '11' * 20, 3), ('0x' + '22' * 20, 4)]],
    ),
    (
        'nested_tuple',
        [
            {
                'type': 'tuple',
                'components': [
                    {
                        'type': 'tuple',
                        'name': 'inner',
                        'components': [
                            {'type': 'uint256', 'name': 'x'},
                            {'type': 'string', 'name': 's'},
                        ],
                    },
                    {'type': 'bool', 'name': 'flag'},
                ],
            }
        ],
        [((1, 'deep'), False)],
    ),
    (
        'mixed_static_dynamic',
        [
            {'type': 'uint256'},
            {'type': 'string'},
            {'type': 'uint256[]'},
            {'type': 'bytes3'},
        ],
        [1, 'mixed', [4, 5], b'\x01\x02\x03'],
    ),
]


def _as_lists(value: Any) -> Any:
    """Normalise container flavour (eth-abi yields tuples) for comparison."""
    if isinstance(value, list | tuple):
        return [_as_lists(item) for item in value]
    return value


class TestCrossOracle:
    """The pure codec against eth-abi on the same encoded bytes."""

    @pytest.mark.parametrize(
        ('params', 'values'),
        [pytest.param(params, values, id=name) for name, params, values in VECTORS],
    )
    @requires_eth_abi
    def test_pure_decode_matches_eth_abi(self, params, values):
        from eth_abi.abi import decode as eth_decode
        from eth_abi.abi import encode as eth_encode

        types = [canonical_abi_type(param) for param in params]
        data = eth_encode(types, values)

        assert _as_lists(decode_values(compile_params(params), data)) == _as_lists(
            eth_decode(types, data)
        )

    @pytest.mark.parametrize(
        ('params', 'values'),
        [pytest.param(params, values, id=name) for name, params, values in VECTORS],
    )
    @requires_eth_abi
    def test_pure_encode_matches_eth_abi(self, params, values):
        from eth_abi.abi import encode as eth_encode

        types = [canonical_abi_type(param) for param in params]

        assert encode_arguments(params, list(values)) == eth_encode(types, values)


class TestTierParity:
    """A base install and an ``[fallback]`` install decode identically."""

    ABI = [
        {
            'type': 'function',
            'name': 'multicall',
            'inputs': [
                {'type': 'uint256', 'name': 'deadline'},
                {'type': 'bytes[]', 'name': 'data'},
                {
                    'type': 'tuple',
                    'name': 'route',
                    'components': [
                        {'type': 'address', 'name': 'target'},
                        {'type': 'uint256[]', 'name': 'fees'},
                    ],
                },
            ],
        }
    ]

    def _calldata(self) -> str:
        signature = 'multicall(uint256,bytes[],(address,uint256[]))'
        args = encode_arguments(
            self.ABI[0]['inputs'],
            [
                2**200,  # above i64::MAX — must come back as a string
                [b'\x01\x02', b''],
                {'target': '0x' + 'cd' * 20, 'fees': [1, 2**64]},
            ],
        )
        return '0x' + keccak_hash(signature)[:8] + args.hex()

    @requires_eth_abi
    def test_eth_abi_and_pure_tiers_agree(self, monkeypatch):
        transaction = {'input': self._calldata()}
        with_eth_abi = decode_transaction_input(dict(transaction), self.ABI)

        monkeypatch.setattr(decode_module, '_eth_abi_decode', None)
        pure = decode_transaction_input(dict(transaction), self.ABI)

        assert pure == with_eth_abi

    @pytest.mark.parametrize(
        ('params', 'values'),
        [pytest.param(params, values, id=name) for name, params, values in VECTORS],
    )
    @pytest.mark.skipif(not FASTABI_AVAILABLE, reason='fastabi extension not built')
    def test_every_tier_agrees_with_the_rust_backend(self, params, values, monkeypatch):
        """fastabi is the reference convention; the other two tiers follow it.

        Covers what the converters normalise: eth-abi hands back Python tuples
        for arrays and structs where fastabi emits JSON arrays.
        """
        named = [
            {**param, 'name': param.get('name') or f'p{position}'}
            for position, param in enumerate(params)
        ]
        signature = f'f({",".join(canonical_abi_type(param) for param in named)})'
        abi = [{'type': 'function', 'name': 'f', 'inputs': named, 'outputs': []}]
        transaction = {
            'input': '0x' + keccak_hash(signature)[:8] + encode_arguments(named, values).hex()
        }

        with_fastabi = decode_module._decode_transaction_input_fast(dict(transaction), abi)
        with_eth_abi = decode_module._decode_transaction_input_python(dict(transaction), abi)
        monkeypatch.setattr(decode_module, '_eth_abi_decode', None)
        pure = decode_module._decode_transaction_input_python(dict(transaction), abi)

        assert with_eth_abi == with_fastabi
        assert pure == with_fastabi

    def test_pure_floor_output_convention(self, monkeypatch):
        monkeypatch.setattr(decode_module, '_eth_abi_decode', None)

        decoded = decode_transaction_input({'input': self._calldata()}, self.ABI)['decoded_data']

        assert decoded == {
            'deadline': str(2**200),  # large ints as strings, like the Rust backend
            'data': ['0x0102', '0x'],  # bytes as 0x hex
            'route': ['0x' + 'cd' * 20, [1, str(2**64)]],  # tuples as lists
        }


class TestBaseInstall:
    """No fastabi, no eth-abi — what ``pip install aiochainscan`` gets."""

    @pytest.fixture(autouse=True)
    def _pure_floor_only(self, monkeypatch):
        monkeypatch.setattr(decode_module, '_eth_abi_decode', None)
        monkeypatch.setattr(decode_module, 'FASTABI_AVAILABLE', False)

    def test_real_transfer_calldata(self):
        """Hand-written USDC ``transfer`` calldata — an oracle-free anchor."""
        abi = [
            {
                'type': 'function',
                'name': 'transfer',
                'inputs': [
                    {'type': 'address', 'name': 'to'},
                    {'type': 'uint256', 'name': 'value'},
                ],
            }
        ]
        calldata = (
            '0xa9059cbb'
            '000000000000000000000000d8da6bf26964af9d7eed9e03e53415d37aa96045'
            '00000000000000000000000000000000000000000000000000000002540be400'
        )

        result = decode_transaction_input({'input': calldata}, abi)

        assert result['decoded_func'] == 'transfer'
        assert result['decoded_data'] == {
            'to': '0xd8da6bf26964af9d7eed9e03e53415d37aa96045',
            'value': 10_000_000_000,
        }

    def test_event_log_with_indexed_and_data_params(self):
        abi = [
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
        log = {
            'topics': [
                '0x' + keccak_hash('Transfer(address,address,uint256)'),
                '0x' + '00' * 12 + '11' * 20,
                '0x' + '00' * 12 + '22' * 20,
            ],
            'data': '0x' + (2**100).to_bytes(32, 'big').hex(),
        }

        result = decode_log_data(log, abi)

        assert result['decoded_data'] == {
            'event': 'Transfer',
            'from': '0x' + '11' * 20,
            'to': '0x' + '22' * 20,
            'value': str(2**100),
        }

    def test_unsupported_type_raises_instead_of_empty_data(self):
        """A gap in the codec must not look like undecodable calldata."""
        abi = [
            {
                'type': 'function',
                'name': 'setRate',
                'inputs': [{'type': 'fixed128x18', 'name': 'rate'}],
            }
        ]
        selector = '0x' + keccak_hash('setRate(fixed128x18)')[:8]

        with pytest.raises(AbiTypeNotSupportedError) as excinfo:
            decode_transaction_input({'input': selector + '00' * 32}, abi)

        assert excinfo.value.abi_type == 'fixed128x18'

    def test_unsupported_type_in_event_raises(self):
        abi = [
            {
                'type': 'event',
                'name': 'RateSet',
                'inputs': [{'type': 'fixed128x18', 'name': 'rate', 'indexed': False}],
            }
        ]
        log = {
            'topics': ['0x' + keccak_hash('RateSet(fixed128x18)')],
            'data': '0x' + '00' * 32,
        }

        with pytest.raises(AbiTypeNotSupportedError):
            decode_log_data(log, abi)

    def test_malformed_calldata_still_decodes_to_empty(self):
        """Truncated data is bad input, not a codec gap — stays non-fatal."""
        abi = [
            {
                'type': 'function',
                'name': 'transfer',
                'inputs': [
                    {'type': 'address', 'name': 'to'},
                    {'type': 'uint256', 'name': 'value'},
                ],
            }
        ]

        result = decode_transaction_input({'input': '0xa9059cbb' + '11' * 8}, abi)

        assert result['decoded_func'] == ''
        assert result['decoded_data'] == {}


class TestAbiIndexCache:
    ABI_A = [
        {'type': 'function', 'name': 'a', 'inputs': [{'type': 'uint256', 'name': 'x'}]},
    ]
    ABI_B = [
        {'type': 'function', 'name': 'b', 'inputs': [{'type': 'uint256', 'name': 'x'}]},
    ]

    def test_same_object_hits_the_identity_fast_path(self):
        abi = list(self.ABI_A)

        assert decode_module._abi_index(abi) is decode_module._abi_index(abi)

    def test_equal_content_shares_one_index(self):
        first = decode_module._abi_index([dict(item) for item in self.ABI_A])
        second = decode_module._abi_index([dict(item) for item in self.ABI_A])

        assert first is second

    def test_distinct_abis_do_not_share_an_index(self):
        index_a = decode_module._abi_index(list(self.ABI_A))
        index_b = decode_module._abi_index(list(self.ABI_B))

        assert index_a is not index_b
        assert set(index_a.function_map) != set(index_b.function_map)

    def test_cached_plans_do_not_leak_between_selectors(self, monkeypatch):
        """Two functions of one ABI must not reuse each other's decode plan."""
        monkeypatch.setattr(decode_module, '_eth_abi_decode', None)
        abi = [
            {'type': 'function', 'name': 'one', 'inputs': [{'type': 'uint256', 'name': 'x'}]},
            {'type': 'function', 'name': 'two', 'inputs': [{'type': 'address', 'name': 'y'}]},
        ]
        word = '00' * 12 + '33' * 20

        one = decode_transaction_input(
            {'input': '0x' + keccak_hash('one(uint256)')[:8] + word}, abi
        )
        two = decode_transaction_input(
            {'input': '0x' + keccak_hash('two(address)')[:8] + word}, abi
        )

        assert one['decoded_data'] == {'x': str(int(word, 16))}
        assert two['decoded_data'] == {'y': '0x' + '33' * 20}


class TestMcpConvention:
    """``decode_arguments`` keeps the agent-facing JSON shape."""

    def test_named_tuple_becomes_a_dict_and_ints_become_strings(self):
        outputs = [
            {
                'type': 'tuple',
                'name': 'slot',
                'components': [
                    {'type': 'uint256', 'name': 'amount'},
                    {'type': 'bytes2', 'name': 'tag'},
                ],
            }
        ]
        data = encode_arguments(outputs, [{'amount': 7, 'tag': '0xbeef'}])

        assert decode_arguments(outputs, data) == {'slot': {'amount': '7', 'tag': '0xbeef'}}

    def test_unnamed_tuple_components_stay_positional(self):
        outputs = [
            {
                'type': 'tuple',
                'components': [{'type': 'uint8'}, {'type': 'uint8', 'name': 'second'}],
            }
        ]
        data = encode_arguments(outputs, [[1, 2]])

        assert decode_arguments(outputs, data) == {'0': ['1', '2']}


class TestTypeNodeLayout:
    """Layout is resolved at parse time, so the decoder never re-derives it."""

    @pytest.mark.parametrize(
        ('abi_type', 'is_dynamic', 'static_size'),
        [
            ('uint256', False, 32),
            ('bytes', True, 32),
            ('uint256[2]', False, 64),
            ('uint256[]', True, 32),
            ('string[2]', True, 32),
        ],
    )
    def test_precomputed_layout(self, abi_type, is_dynamic, static_size):
        (node,) = compile_params([{'type': abi_type}])

        assert isinstance(node, TypeNode)
        assert node.is_dynamic is is_dynamic
        assert node.static_size == static_size

    def test_unsupported_type_is_rejected_at_parse_time(self):
        with pytest.raises(AbiTypeNotSupportedError):
            compile_params([{'type': 'ufixed64x8'}])


@pytest.mark.benchmark(group='abi_decode_tiers')
class TestPureFloorBenchmarks:
    """The pure floor is the default path of every base install — measure it."""

    ABI = [
        {
            'type': 'function',
            'name': 'swapExactTokensForTokens',
            'inputs': [
                {'type': 'uint256', 'name': 'amountIn'},
                {'type': 'uint256', 'name': 'amountOutMin'},
                {'type': 'address[]', 'name': 'path'},
                {'type': 'address', 'name': 'to'},
                {'type': 'uint256', 'name': 'deadline'},
            ],
        }
    ] + [
        {'type': 'function', 'name': f'filler{i}', 'inputs': [{'type': 'uint256', 'name': 'x'}]}
        for i in range(20)
    ]

    def setup_method(self):
        signature = 'swapExactTokensForTokens(uint256,uint256,address[],address,uint256)'
        args = encode_arguments(
            self.ABI[0]['inputs'],
            [
                10**18,
                5 * 10**17,
                ['0x' + '11' * 20, '0x' + '22' * 20],
                '0x' + '33' * 20,
                1_700_000_000,
            ],
        )
        self.transaction = {'input': '0x' + keccak_hash(signature)[:8] + args.hex()}

    def test_pure_floor_single(self, benchmark, monkeypatch):
        monkeypatch.setattr(decode_module, '_eth_abi_decode', None)

        result = benchmark(lambda: decode_transaction_input(dict(self.transaction), self.ABI))

        assert result['decoded_func'] == 'swapExactTokensForTokens'

    @requires_eth_abi
    def test_eth_abi_tier_single(self, benchmark):
        result = benchmark(lambda: decode_transaction_input(dict(self.transaction), self.ABI))

        assert result['decoded_func'] == 'swapExactTokensForTokens'
