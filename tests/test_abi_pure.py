"""The pure-Python ABI decode floor: correctness, tier parity, speed.

Three oracles, in decreasing order of independence: hand-written calldata with
known values, ``eth_abi`` (cross-checked round-trips; a dev-only oracle, not a
decode tier), and the two decode tiers against each other. The parity tests are
the point of the exercise — a base install and an ``aiochainscan[fastabi]``
install must not disagree about what a transaction says.
"""

import warnings
from decimal import Decimal
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
    FASTABI_AVAILABLE,
    canonical_abi_type,
    decode_log_data,
    decode_transaction_input,
    decode_transaction_inputs_batch,
    keccak_hash,
)
from aiochainscan.exceptions import AbiTypeNotSupportedError, PureAbiDecodeWarning

try:  # eth-abi is a test oracle only -- it is no longer a decode tier
    import eth_abi  # noqa: F401

    ETH_ABI_ORACLE = True
except ImportError:  # pragma: no cover - dev extra always installs it
    ETH_ABI_ORACLE = False

requires_eth_abi = pytest.mark.skipif(not ETH_ABI_ORACLE, reason='eth-abi oracle not installed')

# (id, params, values) — values in the encoder's native form.
VECTORS: list[tuple[str, list[dict[str, Any]], list[Any]]] = [
    ('scalars', [{'type': 'uint256'}, {'type': 'address'}], [2**255 - 1, '0x' + 'ab' * 20]),
    ('signed_extremes', [{'type': 'int8'}, {'type': 'int256'}], [-128, -(2**255)]),
    (
        'bool_bytes',
        [{'type': 'bool'}, {'type': 'bytes4'}, {'type': 'bytes'}],
        [True, b'\xde\xad\xbe\xef', b'\x00' * 70],
    ),
    (
        'fixed_point',
        [{'type': 'ufixed128x18'}, {'type': 'fixed128x18'}, {'type': 'fixed8x1'}],
        [Decimal('1.5'), Decimal('-2.25'), Decimal('-0.1')],
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


@requires_eth_abi
@pytest.mark.parametrize(
    ('abi_type', 'payload'),
    [
        ('uint8', '100'.rjust(64, '0')),
        ('int8', 'ff'.rjust(64, '0')),
        ('bool', '2'.rjust(64, '0')),
        ('address', 'ff' * 12 + '11' * 20),
        ('bytes4', 'aabbccdd' + 'ff' * 28),
        ('string', '0' * 64),
        ('uint256', '00' * 16),
        ('string', 'ffff'.rjust(64, '0')),
        ('uint8[]', '20'.rjust(64, '0') + 'ffffff'.rjust(64, '0')),
    ],
)
def test_pure_floor_refuses_exactly_what_eth_abi_refuses(abi_type, payload):
    """Strictness parity: the floor rejects everything eth-abi rejected."""
    from eth_abi.abi import decode as eth_decode
    from eth_abi.exceptions import DecodingError

    data = bytes.fromhex(payload)
    with pytest.raises(DecodingError):
        eth_decode([abi_type], data)
    with pytest.raises(ValueError):
        decode_values(compile_params([{'type': abi_type}]), data)


class TestTierParity:
    """A base install and an ``[fastabi]`` install decode identically."""

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

    @pytest.mark.parametrize(
        ('params', 'values'),
        [pytest.param(params, values, id=name) for name, params, values in VECTORS],
    )
    @pytest.mark.skipif(not FASTABI_AVAILABLE, reason='fastabi extension not built')
    def test_the_pure_floor_agrees_with_the_rust_backend(self, params, values):
        """fastabi is the reference convention; the pure floor follows it.

        Covers what the converters normalise: the pure floor hands back Python
        tuples for arrays and structs where fastabi emits JSON arrays.
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
        pure = decode_module._decode_transaction_input_python(dict(transaction), abi)

        assert pure == with_fastabi

    def test_pure_floor_output_convention(self, monkeypatch):
        # Without this the call dispatches to Rust wherever fastabi is built,
        # and the assertion below stops covering the floor it is named after.
        monkeypatch.setattr(decode_module, 'FASTABI_AVAILABLE', False)

        decoded = decode_transaction_input({'input': self._calldata()}, self.ABI)['decoded_data']

        assert decoded == {
            'deadline': str(2**200),  # large ints as strings, like the Rust backend
            'data': ['0x0102', '0x'],  # bytes as 0x hex
            'route': ['0x' + 'cd' * 20, [1, str(2**64)]],  # tuples as lists
        }


class TestBaseInstall:
    """No fastabi — what ``pip install aiochainscan`` gets."""

    @pytest.fixture(autouse=True)
    def _pure_floor_only(self, monkeypatch):
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
                'inputs': [{'type': 'uint257', 'name': 'rate'}],
            }
        ]
        selector = '0x' + keccak_hash('setRate(uint257)')[:8]

        with pytest.raises(AbiTypeNotSupportedError) as excinfo:
            decode_transaction_input({'input': selector + '00' * 32}, abi)

        assert excinfo.value.abi_type == 'uint257'

    def test_unsupported_type_in_event_raises(self):
        abi = [
            {
                'type': 'event',
                'name': 'RateSet',
                'inputs': [{'type': 'uint257', 'name': 'rate', 'indexed': False}],
            }
        ]
        log = {
            'topics': ['0x' + keccak_hash('RateSet(uint257)')],
            'data': '0x' + '00' * 32,
        }

        with pytest.raises(AbiTypeNotSupportedError):
            decode_log_data(log, abi)

    def test_corrupted_array_length_does_not_allocate(self):
        """A garbage length word must be rejected, not turned into a huge list."""
        abi = [
            {
                'type': 'function',
                'name': 'batch',
                'inputs': [{'type': 'uint256[]', 'name': 'items'}],
            }
        ]
        calldata = (
            '0x'
            + keccak_hash('batch(uint256[])')[:8]
            + (32).to_bytes(32, 'big').hex()  # offset to the array
            + (2**64).to_bytes(32, 'big').hex()  # claimed item count
        )

        result = decode_transaction_input({'input': calldata}, abi)

        assert result['decoded_data'] == {}

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

    def test_bulk_decode_warns_once_about_the_missing_rust_backend(self, monkeypatch):
        monkeypatch.setattr(decode_module, '_bulk_warning_emitted', False)
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
        batch = [{'input': calldata} for _ in range(decode_module._BULK_WARNING_THRESHOLD)]

        with pytest.warns(PureAbiDecodeWarning, match=r'aiochainscan\[fastabi\]'):
            first = decode_transaction_inputs_batch(batch, abi)

        assert all(tx['decoded_func'] == 'transfer' for tx in first)

        with warnings.catch_warnings():
            warnings.simplefilter('error', PureAbiDecodeWarning)
            decode_transaction_inputs_batch(batch, abi)

    @pytest.mark.parametrize(
        ('abi_type', 'word'),
        [
            ('uint8', '100'),  # does not fit in 8 bits
            ('int8', 'ff'),  # padding is not the sign extension
            ('bool', '2'),  # neither 0 nor 1
            ('address', 'ff' * 12 + '11' * 20),  # padding is not zero
            ('bytes4', 'aabbccdd' + 'ff' * 28),  # trailing padding is not zero
        ],
    )
    def test_non_canonical_padding_is_rejected(self, abi_type, word):
        """The spec requires zero padding; a value no encoder could produce is not data."""
        abi = [{'type': 'function', 'name': 'f', 'inputs': [{'type': abi_type, 'name': 'x'}]}]
        selector = '0x' + keccak_hash(f'f({abi_type})')[:8]
        calldata = selector + (word if len(word) == 64 else word.rjust(64, '0'))

        result = decode_transaction_input({'input': calldata}, abi)

        assert result['decoded_data'] == {}

    def test_canonical_padding_still_decodes(self):
        """The strict rules must not reject anything a compliant encoder emits."""
        abi = [
            {
                'type': 'function',
                'name': 'f',
                'inputs': [
                    {'type': 'int8', 'name': 'a'},
                    {'type': 'bool', 'name': 'b'},
                    {'type': 'bytes4', 'name': 'c'},
                ],
            }
        ]
        selector = '0x' + keccak_hash('f(int8,bool,bytes4)')[:8]
        calldata = selector + 'ff' * 32 + '1'.rjust(64, '0') + 'aabbccdd' + '0' * 56

        result = decode_transaction_input({'input': calldata}, abi)

        assert result['decoded_data'] == {'a': -1, 'b': True, 'c': '0xaabbccdd'}

    def test_dynamic_offset_into_the_head_area_is_rejected(self):
        abi = [{'type': 'function', 'name': 'f', 'inputs': [{'type': 'string', 'name': 'x'}]}]
        selector = '0x' + keccak_hash('f(string)')[:8]

        result = decode_transaction_input({'input': selector + '0' * 64}, abi)

        assert result['decoded_data'] == {}

    def test_small_bulk_decode_stays_silent(self, monkeypatch):
        """A batch below the threshold is not slow enough to be worth a message."""
        monkeypatch.setattr(decode_module, '_bulk_warning_emitted', False)
        abi = [{'type': 'function', 'name': 'ping', 'inputs': []}]

        with warnings.catch_warnings():
            warnings.simplefilter('error', PureAbiDecodeWarning)
            decode_transaction_inputs_batch([{'input': '0x' + keccak_hash('ping()')[:8]}], abi)


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

    def test_cached_plans_do_not_leak_between_selectors(self):
        """Two functions of one ABI must not reuse each other's decode plan."""
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

    def test_mutating_one_abi_never_changes_how_another_decodes(self):
        """Equal ABI lists share one cached index; it must share no state with them."""

        def make_abi() -> list[dict[str, Any]]:
            return [
                {
                    'type': 'function',
                    'name': 'transfer',
                    'inputs': [
                        {'type': 'address', 'name': 'to'},
                        {'type': 'uint256', 'name': 'value'},
                    ],
                }
            ]

        seeded, untouched = make_abi(), make_abi()
        assert seeded is not untouched and seeded == untouched
        calldata = (
            '0xa9059cbb'
            '000000000000000000000000d8da6bf26964af9d7eed9e03e53415d37aa96045'
            '00000000000000000000000000000000000000000000000000000002540be400'
        )

        decode_transaction_input({'input': calldata}, seeded)
        seeded[0]['name'] = 'POISONED'
        seeded[0]['inputs'][0]['name'] = 'poisoned_param'

        result = decode_transaction_input({'input': calldata}, untouched)

        assert result['decoded_func'] == 'transfer'
        assert set(result['decoded_data']) == {'to', 'value'}


@requires_eth_abi
def test_malformed_padding_is_non_fatal_on_the_eth_abi_tier(monkeypatch):
    """eth-abi raises DecodingError, which is not a ValueError, for bad padding."""
    monkeypatch.setattr(decode_module, 'FASTABI_AVAILABLE', False)
    abi = [{'type': 'function', 'name': 'flag', 'inputs': [{'type': 'bool', 'name': 'x'}]}]
    calldata = '0x' + keccak_hash('flag(bool)')[:8] + '2'.rjust(64, '0')

    result = decode_transaction_input({'input': calldata}, abi)

    assert result['decoded_func'] == ''
    assert result['decoded_data'] == {}


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

    @pytest.mark.parametrize(
        'abi_type',
        ['uint257', 'uint0', 'int12', 'bytes33', 'bytes0', 'fixed128x81', 'fixed127x18'],
    )
    def test_widths_outside_the_spec_are_rejected_at_parse_time(self, abi_type):
        """Same set eth-abi rejects; a bogus width must not decode to a number."""
        with pytest.raises(AbiTypeNotSupportedError):
            compile_params([{'type': abi_type}])


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

    def test_pure_floor_single(self, benchmark):
        result = benchmark(lambda: decode_transaction_input(dict(self.transaction), self.ABI))

        assert result['decoded_func'] == 'swapExactTokensForTokens'
