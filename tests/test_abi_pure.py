"""The pure-Python ABI decode floor: correctness, tier parity, speed.

Three oracles, in decreasing order of independence: hand-written calldata with
known values, ``eth_abi`` (cross-checked round-trips; a dev-only oracle, not a
decode tier), and the two decode tiers against each other. The parity tests are
the point of the exercise — a base install and an ``aiochainscan[fastabi]``
install must not disagree about what a transaction says.
"""

import signal
import warnings
from decimal import Context, Decimal
from typing import Any

import orjson
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
    (
        # 78 significant digits: more than Decimal's default context keeps.
        'fixed_point_full_width',
        [{'type': 'ufixed256x18'}, {'type': 'fixed256x80'}],
        [
            Decimal(2**256 - 1).scaleb(-18, Context(prec=256)),
            Decimal(-(2**255)).scaleb(-80, Context(prec=256)),
        ],
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


# (abi_type, payload) pairs no compliant encoder can produce. eth-abi rejects
# every one, so both remaining tiers must too -- a tier that accepts one reads
# the same transaction differently from the other.
NON_CANONICAL: list[tuple[str, str]] = [
    ('uint8', '100'.rjust(64, '0')),
    ('int8', 'ff'.rjust(64, '0')),
    ('bool', '2'.rjust(64, '0')),
    # An all-ones bool word: the tiers once disagreed here (Rust rejected it,
    # the floor read it as False), so parity on it is pinned, not assumed.
    ('bool', 'ff' * 32),
    ('address', 'ff' * 12 + '11' * 20),
    ('bytes4', 'aabbccdd' + 'ff' * 28),
    ('string', '0' * 64),
    ('uint256', '00' * 16),
    ('string', 'ffff'.rjust(64, '0')),
    ('uint8[]', '20'.rjust(64, '0') + 'ffffff'.rjust(64, '0')),
    # Dirty padding between a dynamic value and its 32-byte boundary.
    ('bytes', '20'.rjust(64, '0') + '1'.rjust(64, '0') + 'aa' + '00' * 30 + 'ff'),
    ('string', '20'.rjust(64, '0') + '1'.rjust(64, '0') + '61' + '00' * 30 + 'ff'),
    # Not UTF-8: ethabi converts lossily, so this needs an explicit check.
    ('string', '20'.rjust(64, '0') + '1'.rjust(64, '0') + 'ff' + '00' * 31),
]


@requires_eth_abi
@pytest.mark.parametrize(('abi_type', 'payload'), NON_CANONICAL)
def test_pure_floor_refuses_exactly_what_eth_abi_refuses(abi_type, payload):
    """Strictness parity: the floor rejects everything eth-abi rejected."""
    from eth_abi.abi import decode as eth_decode
    from eth_abi.exceptions import DecodingError

    data = bytes.fromhex(payload)
    # eth-abi signals invalid UTF-8 with UnicodeDecodeError, not DecodingError.
    with pytest.raises((DecodingError, UnicodeDecodeError)):
        eth_decode([abi_type], data)
    with pytest.raises(ValueError):
        decode_values(compile_params([{'type': abi_type}]), data)


@pytest.mark.skipif(not FASTABI_AVAILABLE, reason='fastabi extension not built')
def test_bulk_decoding_falls_back_wherever_a_single_decode_does():
    """A type the Rust backend cannot build a signature for must not decode in
    one call and come back empty in a batch of the same call."""
    inputs = [{'type': 'fixed128x18', 'name': 'x'}]
    abi = [{'type': 'function', 'name': 'f', 'inputs': inputs, 'outputs': []}]
    calldata = (
        '0x' + keccak_hash('f(fixed128x18)')[:8] + encode_arguments(inputs, [Decimal('1.5')]).hex()
    )

    single = decode_transaction_input({'input': calldata}, abi)
    batch = decode_transaction_inputs_batch([{'input': calldata}], abi)[0]

    assert single['decoded_data'] == {'x': '1.500000000000000000'}
    assert batch['decoded_data'] == single['decoded_data']
    assert batch['decoded_func'] == single['decoded_func'] == 'f'


@pytest.mark.skipif(not FASTABI_AVAILABLE, reason='fastabi extension not built')
@pytest.mark.parametrize(('abi_type', 'payload'), NON_CANONICAL)
def test_the_rust_tier_refuses_what_the_floor_refuses(abi_type, payload):
    """ethabi is lenient and has no strict mode, so lib.rs validates by hand.

    Undecodable calldata is non-fatal by contract, so a rejection shows up as
    an empty result rather than an exception.
    """
    abi = [
        {
            'type': 'function',
            'name': 'f',
            'inputs': [{'type': abi_type, 'name': 'x'}],
            'outputs': [],
        }
    ]
    calldata = '0x' + keccak_hash(f'f({abi_type})')[:8] + payload

    assert (
        decode_module._decode_transaction_input_fast({'input': calldata}, abi)['decoded_data']
        == {}
    )


class RawAbiEncoded(bytes):
    """Marker for pre-encoded ABI argument bytes."""


# Module-level table of declared Tier-convention cases:
# (solidity_type, abi_encoded_input_or_python_value, expected_tier_convention_value)
TIER_CONVENTION_CASES: list[tuple[str | dict[str, Any], Any, Any]] = [
    ('uint256', 9223372036854775807, 9223372036854775807),
    ('uint256', 9223372036854775808, '9223372036854775808'),
    ('int256', -9223372036854775808, -9223372036854775808),
    ('int256', -9223372036854775809, '-9223372036854775809'),
    ('bool', True, True),
    ('address', '0x' + '11' * 20, '0x' + '11' * 20),
    ('bytes32', b'\xaa' * 32, '0x' + 'aa' * 32),
    ('bytes', b'\x01\x02\x03', '0x010203'),
    ('string', 'hello world', 'hello world'),
    ('uint8[]', [1, 2, 3], [1, 2, 3]),
    (
        {
            'type': 'tuple',
            'name': 'named_tuple',
            'components': [{'type': 'uint256', 'name': 'a'}, {'type': 'bytes', 'name': 'b'}],
        },
        (42, b'\x01\x02'),
        [42, '0x0102'],
    ),
    (
        {
            'type': 'tuple',
            'components': [{'type': 'uint256'}, {'type': 'address'}],
        },
        (99, '0x' + '22' * 20),
        [99, '0x' + '22' * 20],
    ),
    ('ufixed128x18', Decimal('1.5'), '1.500000000000000000'),
]

TIER_CONVENTION_IDS: list[str] = [
    'uint256-int64-max',
    'uint256-above-int64-max',
    'int256-int64-min',
    'int256-below-int64-min',
    'bool',
    'address',
    'bytes32',
    'bytes',
    'string',
    'uint8-array',
    'named-tuple',
    'unnamed-tuple',
    'ufixed128x18',
]

PARAM_NAMING_CASES: list[tuple[list[dict[str, Any]], list[str]]] = [
    (
        [{'type': 'uint256', 'name': ''}, {'type': 'uint256', 'name': ''}],
        ['param_0', 'param_1'],
    ),
    (
        [{'type': 'uint256'}, {'type': 'uint256'}],
        ['param_0', 'param_1'],
    ),
    (
        [{'type': 'uint256', 'name': 'a'}, {'type': 'uint256', 'name': 'a'}],
        ['a', 'a_2'],
    ),
    (
        [
            {'type': 'uint256', 'name': 'a'},
            {'type': 'uint256', 'name': 'a'},
            {'type': 'uint256', 'name': 'a'},
        ],
        ['a', 'a_2', 'a_3'],
    ),
    (
        [
            {'type': 'uint256', 'name': ''},
            {'type': 'uint256', 'name': 'a'},
            {'type': 'uint256', 'name': ''},
            {'type': 'uint256', 'name': 'a'},
        ],
        ['param_0', 'a', 'param_2', 'a_2'],
    ),
]

PARAM_NAMING_IDS: list[str] = [
    'unnamed-empty-string',
    'unnamed-missing-key',
    'duplicate-names',
    'triple-duplicate-names',
    'mixed-named-unnamed-duplicate',
]


def _build_tier_case_calldata(
    solidity_type: str | dict[str, Any],
    val_or_encoded: Any,
) -> tuple[str, list[dict[str, Any]], str]:
    param = {'type': solidity_type} if isinstance(solidity_type, str) else dict(solidity_type)
    param_name = str(param.get('name') or '') or 'arg'
    param_with_name = {**param, 'name': param_name}
    sig = f'f({canonical_abi_type(param_with_name)})'
    abi = [{'type': 'function', 'name': 'f', 'inputs': [param_with_name], 'outputs': []}]
    if isinstance(val_or_encoded, RawAbiEncoded):
        raw_args = bytes(val_or_encoded)
    elif isinstance(val_or_encoded, bytes) and param.get('type') not in (
        'bytes',
        'fixed_bytes',
        'bytes32',
    ):
        raw_args = val_or_encoded
    else:
        raw_args = encode_arguments([param_with_name], [val_or_encoded])
    calldata = '0x' + keccak_hash(sig)[:8] + raw_args.hex()
    return param_name, abi, calldata


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

    @pytest.mark.skipif(not FASTABI_AVAILABLE, reason='fastabi extension not built')
    def test_the_pure_floor_agrees_with_the_rust_backend_on_unnamed_inputs(self):
        """Unnamed inputs must agree WITHOUT pre-filling names.

        The vector test above masks the convention with ``name or f'p{position}'``;
        these cases exercise the real one: unnamed inputs are keyed ``param_{i}``
        on both tiers, so adding or dropping ``[fastabi]`` cannot change the keys
        of a decoded payload.
        """
        abi = [
            {
                'type': 'function',
                'name': 'transfer',
                'inputs': [{'type': 'address', 'name': ''}, {'type': 'uint256', 'name': ''}],
                'outputs': [],
            }
        ]
        signature = 'transfer(address,uint256)'
        transaction = {
            'input': '0x'
            + keccak_hash(signature)[:8]
            + '00' * 12
            + 'ab' * 20
            + (5).to_bytes(32, 'big').hex()
        }

        with_fastabi = decode_module._decode_transaction_input_fast(dict(transaction), abi)
        pure = decode_module._decode_transaction_input_python(dict(transaction), abi)

        assert pure == with_fastabi
        assert pure['decoded_data'] == {'param_0': '0x' + 'ab' * 20, 'param_1': 5}

    @pytest.mark.skipif(not FASTABI_AVAILABLE, reason='fastabi extension not built')
    def test_the_pure_floor_agrees_with_the_rust_backend_on_duplicate_names(self):
        """Duplicate input names must agree on both tiers, and neither may drop
        a value: the first occurrence keeps the plain name, later ones are
        suffixed ``_2`` (the Rust tier folds them onto one key otherwise)."""
        abi = [
            {
                'type': 'function',
                'name': 'f',
                'inputs': [
                    {'type': 'uint256', 'name': 'a'},
                    {'type': 'uint256', 'name': 'a'},
                ],
                'outputs': [],
            }
        ]
        signature = 'f(uint256,uint256)'
        transaction = {
            'input': '0x'
            + keccak_hash(signature)[:8]
            + (1).to_bytes(32, 'big').hex()
            + (2).to_bytes(32, 'big').hex()
        }

        with_fastabi = decode_module._decode_transaction_input_fast(dict(transaction), abi)
        pure = decode_module._decode_transaction_input_python(dict(transaction), abi)

        assert pure == with_fastabi
        assert pure['decoded_data'] == {'a': 1, 'a_2': 2}

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

    @pytest.mark.parametrize(
        ('solidity_type', 'val_or_encoded', 'expected'),
        TIER_CONVENTION_CASES,
        ids=TIER_CONVENTION_IDS,
    )
    def test_pure_floor_tier_convention_table(
        self,
        solidity_type: str | dict[str, Any],
        val_or_encoded: Any,
        expected: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The pure-Python floor implements the Tier convention unconditionally."""
        monkeypatch.setattr(decode_module, 'FASTABI_AVAILABLE', False)
        param_name, abi, calldata = _build_tier_case_calldata(solidity_type, val_or_encoded)
        decoded = decode_transaction_input({'input': calldata}, abi)['decoded_data']
        assert decoded[param_name] == expected

    @pytest.mark.parametrize(
        ('solidity_type', 'val_or_encoded', 'expected'),
        TIER_CONVENTION_CASES,
        ids=TIER_CONVENTION_IDS,
    )
    @pytest.mark.skipif(not FASTABI_AVAILABLE, reason='fastabi extension not built')
    def test_rust_tier_tier_convention_table(
        self,
        solidity_type: str | dict[str, Any],
        val_or_encoded: Any,
        expected: Any,
    ) -> None:
        """The Rust tier implements the Tier convention and agrees with expected."""
        param_name, abi, calldata = _build_tier_case_calldata(solidity_type, val_or_encoded)
        fast_decoded = decode_module._decode_transaction_input_fast({'input': calldata}, abi)[
            'decoded_data'
        ]
        assert fast_decoded[param_name] == expected

    @pytest.mark.parametrize(
        ('params', 'expected_names'),
        PARAM_NAMING_CASES,
        ids=PARAM_NAMING_IDS,
    )
    def test_pure_floor_param_naming_table(
        self,
        params: list[dict[str, Any]],
        expected_names: list[str],
    ) -> None:
        """The pure floor resolves input names according to the naming convention."""
        assert decode_module._resolved_input_names(params) == expected_names

    @pytest.mark.parametrize(
        ('params', 'expected_names'),
        PARAM_NAMING_CASES,
        ids=PARAM_NAMING_IDS,
    )
    @pytest.mark.skipif(not FASTABI_AVAILABLE, reason='fastabi extension not built')
    def test_rust_tier_param_naming_table(
        self,
        params: list[dict[str, Any]],
        expected_names: list[str],
    ) -> None:
        """The Rust tier resolves input names identically to the pure floor."""
        sig = f'f({",".join(canonical_abi_type(p) for p in params)})'
        abi = [{'type': 'function', 'name': 'f', 'inputs': params, 'outputs': []}]
        values = [1] * len(params)
        calldata = '0x' + keccak_hash(sig)[:8] + encode_arguments(params, values).hex()
        fast_decoded = decode_module._decode_transaction_input_fast({'input': calldata}, abi)[
            'decoded_data'
        ]
        pure_decoded = decode_module._decode_transaction_input_python({'input': calldata}, abi)[
            'decoded_data'
        ]
        assert fast_decoded == pure_decoded
        assert set(fast_decoded.keys()) == set(expected_names)
        assert len(fast_decoded) == len(expected_names)


class TestUnnamedAndDuplicateInputNames:
    """One naming convention on both tiers for unnamed/colliding input names.

    ``dict(zip(names, values))`` used to fold every unnamed input onto the
    ``''`` key (all but the last silently lost) and a *missing* ``name`` key
    raised a KeyError that the malformed-calldata net swallowed, voiding the
    whole decode. The convention — mirrored in ``fastabi/src/lib.rs`` — is:
    unnamed inputs are keyed ``param_{i}`` by position; a name colliding with
    an earlier parameter keeps the plain spelling only for the first
    occurrence, later ones are suffixed ``_2``.
    """

    @pytest.fixture(autouse=True)
    def _pure_floor_only(self, monkeypatch):
        monkeypatch.setattr(decode_module, 'FASTABI_AVAILABLE', False)

    def _decode_data(self, inputs: list[dict[str, Any]], values: list[Any]) -> dict[str, Any]:
        abi = [{'type': 'function', 'name': 'f', 'inputs': inputs, 'outputs': []}]
        signature = f'f({",".join(canonical_abi_type(param) for param in inputs)})'
        calldata = '0x' + keccak_hash(signature)[:8] + encode_arguments(inputs, list(values)).hex()
        return decode_transaction_input({'input': calldata}, abi)['decoded_data']

    def test_empty_string_names_are_keyed_by_position(self):
        decoded = self._decode_data(
            [{'type': 'uint256', 'name': ''}, {'type': 'uint256', 'name': ''}], [1, 2]
        )

        assert decoded == {'param_0': 1, 'param_1': 2}

    def test_missing_name_keys_are_not_swallowed_as_malformed_calldata(self):
        decoded = self._decode_data([{'type': 'uint256'}, {'type': 'uint256'}], [1, 2])

        assert decoded == {'param_0': 1, 'param_1': 2}

    def test_duplicate_names_first_keeps_the_plain_name(self):
        decoded = self._decode_data(
            [{'type': 'uint256', 'name': 'a'}, {'type': 'uint256', 'name': 'a'}], [1, 2]
        )

        assert decoded == {'a': 1, 'a_2': 2}

    def test_triple_duplicates_number_consecutively(self):
        decoded = self._decode_data(
            [
                {'type': 'uint256', 'name': 'a'},
                {'type': 'uint256', 'name': 'a'},
                {'type': 'uint256', 'name': 'a'},
            ],
            [1, 2, 3],
        )

        assert decoded == {'a': 1, 'a_2': 2, 'a_3': 3}

    def test_mixed_named_unnamed_and_colliding(self):
        decoded = self._decode_data(
            [
                {'type': 'uint256', 'name': ''},
                {'type': 'uint256', 'name': 'a'},
                {'type': 'uint256', 'name': ''},
                {'type': 'uint256', 'name': 'a'},
            ],
            [1, 2, 3, 4],
        )

        assert decoded == {'param_0': 1, 'a': 2, 'param_2': 3, 'a_2': 4}

    def test_unnamed_event_inputs_are_keyed_by_position(self):
        abi = [
            {
                'type': 'event',
                'name': 'T',
                'inputs': [{'type': 'uint256', 'name': ''}, {'type': 'uint256', 'name': ''}],
            }
        ]
        log = {
            'topics': ['0x' + keccak_hash('T(uint256,uint256)')],
            'data': '0x' + (7).to_bytes(32, 'big').hex() + (8).to_bytes(32, 'big').hex(),
        }

        decoded = decode_log_data(dict(log), abi)['decoded_data']

        assert decoded == {'event': 'T', 'param_0': 7, 'param_1': 8}

    def test_duplicate_event_names_resolved_identically_to_functions(self):
        abi = [
            {
                'type': 'event',
                'name': 'T',
                'inputs': [
                    {'type': 'uint256', 'name': 'v', 'indexed': True},
                    {'type': 'uint256', 'name': 'v'},
                ],
            }
        ]
        log = {
            'topics': ['0x' + keccak_hash('T(uint256,uint256)'), (9).to_bytes(32, 'big').hex()],
            'data': '0x' + (8).to_bytes(32, 'big').hex(),
        }

        decoded = decode_log_data(dict(log), abi)['decoded_data']

        assert decoded == {'event': 'T', 'v': 9, 'v_2': 8}


class TestZeroSizeElementArrays:
    """An array of elements that encode to 0 bytes (an empty tuple) with a
    non-zero count is a corrupted length word: ``count * 0`` defeats the
    buffer bound and ``range(count)`` spun on a 2**63 length word (M3)."""

    def test_dynamic_array_with_huge_count_is_rejected(self):
        nodes = compile_params([{'type': 'tuple[]', 'components': []}, {'type': 'uint256'}])
        data = (64).to_bytes(32, 'big') + (1).to_bytes(32, 'big') + (2**63).to_bytes(32, 'big')

        if hasattr(signal, 'SIGALRM'):

            def hang_fail(signum: int, frame: Any) -> None:
                raise AssertionError('decoder spun past 20s on a zero-size element array')

            signal.signal(signal.SIGALRM, hang_fail)
            signal.alarm(20)
        try:
            with pytest.raises(ValueError, match='0 bytes'):
                decode_values(nodes, data)
        finally:
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)

    def test_static_array_of_zero_byte_elements_is_rejected_too(self):
        nodes = compile_params([{'type': 'tuple[3]', 'components': []}])

        with pytest.raises(ValueError, match='0 bytes'):
            decode_values(nodes, b'')

    def test_empty_array_of_zero_byte_elements_still_decodes(self):
        nodes = compile_params([{'type': 'tuple[]', 'components': []}, {'type': 'uint256'}])
        data = (64).to_bytes(32, 'big') + (1).to_bytes(32, 'big') + (0).to_bytes(32, 'big')

        assert decode_values(nodes, data) == [[], 1]


class TestExoticWidthsRejectedAtTheIndex:
    """ethabi accepts integer/bytes widths Solidity cannot produce (``int12``,
    ``uint0``, ``bytes0``) where the floor raises AbiTypeNotSupportedError —
    so the widths are validated at ABI-index build time and the whole ABI is
    refused before the Rust tier could answer differently."""

    @pytest.mark.parametrize('abi_type', ['int12', 'uint0', 'bytes0'])
    def test_building_the_index_rejects_non_spec_widths(self, abi_type):
        abi = [
            {
                'type': 'function',
                'name': 'f',
                'inputs': [{'type': abi_type, 'name': 'x'}],
                'outputs': [],
            }
        ]

        with pytest.raises(AbiTypeNotSupportedError):
            decode_module._preprocess_abi(abi)

    def test_rejection_covers_unrelated_functions_of_the_same_abi(self):
        """The index is built once per ABI: one exotic width anywhere refuses
        the ABI, on both tiers, instead of deciding per selected function."""
        abi = [
            {
                'type': 'function',
                'name': 'ok',
                'inputs': [{'type': 'uint256', 'name': 'x'}],
                'outputs': [],
            },
            {
                'type': 'function',
                'name': 'weird',
                'inputs': [{'type': 'int12', 'name': 'x'}],
                'outputs': [],
            },
        ]
        calldata = '0x' + keccak_hash('ok(uint256)')[:8] + (1).to_bytes(32, 'big').hex()

        with pytest.raises(AbiTypeNotSupportedError):
            decode_transaction_input({'input': calldata}, abi)


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

    @pytest.mark.parametrize(
        'type_name',
        [
            pytest.param('uint256[-1]', id='negative-array-length'),
            pytest.param('uint256[01]', id='non-canonical-array-length'),
            pytest.param('uint08', id='non-canonical-width'),
            pytest.param('bytes032', id='non-canonical-bytes-width'),
            pytest.param('uint\uff12\uff15\uff16', id='full-width-digits'),
        ],
    )
    def test_non_canonical_type_spelling_raises(self, type_name: str) -> None:
        """A type name is hashed verbatim, so a lenient spelling is a different
        function — and ``uint256[-1]`` used to decode to an empty list."""
        with pytest.raises(AbiTypeNotSupportedError):
            compile_params([{'type': type_name, 'name': 'x'}])

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


class TestFixedPointJsonSerialization:
    """``fixedMxN`` decodes to Decimal, which orjson refuses: the transaction
    decode path must render it as a fixed-point string (the same convention
    ``to_json_values`` uses), so an MCP tool serializing a decoded payload
    does not die on the first fixed-point argument (M2)."""

    @pytest.fixture(autouse=True)
    def _pure_floor_only(self, monkeypatch):
        monkeypatch.setattr(decode_module, 'FASTABI_AVAILABLE', False)

    def _decode_fixed(self, abi_type: str, value: Decimal) -> Any:
        inputs = [{'type': abi_type, 'name': 'x'}]
        abi = [{'type': 'function', 'name': 'f', 'inputs': inputs, 'outputs': []}]
        calldata = (
            '0x' + keccak_hash(f'f({abi_type})')[:8] + encode_arguments(inputs, [value]).hex()
        )
        return decode_transaction_input({'input': calldata}, abi)['decoded_data']['x']

    def test_fixed_point_survives_orjson_serialization(self):
        decoded = self._decode_fixed('fixed128x18', Decimal('1.5'))

        assert decoded == '1.500000000000000000'  # string, declared scale
        orjson.dumps({'x': decoded})  # must not raise TypeError

    def test_full_width_fixed_stays_fixed_point_not_scientific(self):
        decoded = self._decode_fixed(
            'ufixed256x80', Decimal(2**256 - 1).scaleb(-80, Context(prec=256))
        )

        assert decoded == format(Decimal(2**256 - 1).scaleb(-80, Context(prec=256)), 'f')
        assert 'E' not in decoded and 'e' not in decoded
        orjson.dumps({'x': decoded})


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

    def test_pure_floor_single(self, benchmark, monkeypatch):
        # Without this the benchmark dispatches to Rust wherever fastabi is
        # built, and stops measuring the floor it is named after.
        monkeypatch.setattr(decode_module, 'FASTABI_AVAILABLE', False)

        result = benchmark(lambda: decode_transaction_input(dict(self.transaction), self.ABI))

        assert result['decoded_func'] == 'swapExactTokensForTokens'
