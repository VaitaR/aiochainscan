"""Pure-Python Solidity ABI codec — the always-available decode floor.

Second and last tier of the decode backend chain in :mod:`aiochainscan.decode`
(``fastabi`` → this module). Unlike :mod:`aiochainscan._keccak` this is not
only a correctness floor: it is the decode path of every base install, so the
parse step is separated from the decode step and every per-value property is
precomputed at parse time.

Two output conventions, deliberately:

- :func:`decode_values` returns *native* Python values (``int``, ``bytes``,
  ``bool``, ``str``, ``list``). :mod:`aiochainscan.decode` normalises those to
  the fastabi JSON convention with its own converters, so the pure floor and
  the Rust accelerator agree value for value.
- :func:`decode_arguments` returns the fastabi JSON convention directly
  (uint/int as strings, bytes as ``0x`` hex, fully-named tuples as dicts) —
  what the MCP ``read_contract`` tool hands to an agent.

Supported types: ``uintN``/``intN``, ``address``, ``bool``, ``bytesN``,
``bytes``, ``string``, ``fixedMxN``/``ufixedMxN``, fixed/dynamic arrays and
(nested) tuples — everything the ABI spec defines. Anything else raises
:class:`~aiochainscan.exceptions.AbiTypeNotSupportedError` rather than decoding
to a wrong or empty value.

Decoding is *strict*, as the spec requires: a static value's padding must be
zero (sign extension for ``intN``) and a dynamic offset must point past the
head area. Accepting non-canonical padding would mean handing back a confident
number that no compliant encoder could have produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from aiochainscan.crypto import keccak_hex
from aiochainscan.exceptions import AbiTypeNotSupportedError

__all__ = [
    'TypeNode',
    'canonical_signature',
    'compile_params',
    'decode_arguments',
    'decode_values',
    'encode_arguments',
    'selector',
    'to_json_values',
]

_BASE_ALIASES = {
    'uint': 'uint256',
    'int': 'int256',
    'byte': 'bytes1',
    'fixed': 'fixed128x18',
    'ufixed': 'ufixed128x18',
    'function': 'bytes24',
}


@dataclass(slots=True)
class TypeNode:
    """Parsed ABI type: canonical form, structure, and precomputed layout.

    Layout fields (``is_dynamic``, ``static_size``, ``head_size``,
    ``tuple_keys``) are resolved once here so the decoder never recurses to
    answer a question about the *shape* while walking bytes.
    """

    canonical: str
    kind: str
    """uint | int | ufixed | fixed | address | bool | fixed_bytes | bytes |
    string | array | tuple"""

    bits: int = 0  # uint/int/fixed width, or bytesN width
    decimals: int = 0  # fixedMxN scale; the N
    length: int | None = None  # fixed-array length; None for dynamic
    elem: TypeNode | None = None
    components: tuple[TypeNode, ...] = ()
    component_names: tuple[str, ...] = ()
    is_dynamic: bool = False
    static_size: int = 32
    head_size: int = 32
    tuple_keys: tuple[str, ...] | None = None
    """Component names, set only when *every* component is named."""


def compile_params(params: list[dict[str, Any]]) -> tuple[TypeNode, ...]:
    """Parse a list of ABI parameters into reusable :class:`TypeNode` values.

    Callers that decode repeatedly against one ABI should keep the result:
    parsing is the expensive half, decoding the cheap one.
    """
    return tuple(_parse_param(param) for param in params)


def _parse_param(param: dict[str, Any]) -> TypeNode:
    """Parse one ABI parameter (``type`` + ``components``) into a TypeNode."""
    type_name = str(param.get('type', ''))
    components = param.get('components') or []

    if type_name.endswith(']'):
        bracket = type_name.rfind('[')
        inner = _parse_param({**param, 'type': type_name[:bracket]})
        suffix = type_name[bracket:]
        size_text = suffix[1:-1]
        length = int(size_text) if size_text else None
        is_dynamic = length is None or inner.is_dynamic
        static_size = 32 if length is None or is_dynamic else length * inner.static_size
        return TypeNode(
            canonical=inner.canonical + suffix,
            kind='array',
            length=length,
            elem=inner,
            is_dynamic=is_dynamic,
            static_size=static_size,
            head_size=32 if is_dynamic else static_size,
        )

    base = _BASE_ALIASES.get(type_name, type_name)
    if base == 'tuple':
        parsed = tuple(_parse_param(component) for component in components)
        names = tuple(str(component.get('name') or '') for component in components)
        is_dynamic = any(node.is_dynamic for node in parsed)
        static_size = 32 if is_dynamic else sum(node.static_size for node in parsed)
        return TypeNode(
            canonical=f"({','.join(node.canonical for node in parsed)})",
            kind='tuple',
            components=parsed,
            component_names=names,
            is_dynamic=is_dynamic,
            static_size=static_size,
            head_size=32 if is_dynamic else static_size,
            tuple_keys=names if all(names) else None,
        )
    if base.startswith('uint') and base[4:].isdigit():
        return TypeNode(canonical=base, kind='uint', bits=_integer_width(type_name, base[4:]))
    if base.startswith('int') and base[3:].isdigit():
        return TypeNode(canonical=base, kind='int', bits=_integer_width(type_name, base[3:]))
    if base == 'address':
        return TypeNode(canonical=base, kind='address')
    if base == 'bool':
        return TypeNode(canonical=base, kind='bool')
    if base == 'string':
        return TypeNode(canonical=base, kind='string', is_dynamic=True)
    if base == 'bytes':
        return TypeNode(canonical=base, kind='bytes', is_dynamic=True)
    if base.startswith('bytes') and base[5:].isdigit():
        width = int(base[5:])
        if not 0 < width <= 32:
            raise AbiTypeNotSupportedError(type_name)
        return TypeNode(canonical=base, kind='fixed_bytes', bits=width)
    for prefix, kind in (('ufixed', 'ufixed'), ('fixed', 'fixed')):
        if base.startswith(prefix):
            width_text, _, scale_text = base[len(prefix) :].partition('x')
            if width_text.isdigit() and scale_text.isdigit():
                scale = int(scale_text)
                if not 0 < scale <= 80:
                    raise AbiTypeNotSupportedError(type_name)
                return TypeNode(
                    canonical=base,
                    kind=kind,
                    bits=_integer_width(type_name, width_text),
                    decimals=scale,
                )
    raise AbiTypeNotSupportedError(type_name)


def _integer_width(type_name: str, digits: str) -> int:
    """Validate a spec integer width: a multiple of 8 in 8..256."""
    width = int(digits)
    if width % 8 or not 0 < width <= 256:
        raise AbiTypeNotSupportedError(type_name)
    return width


def canonical_signature(name: str, inputs: list[dict[str, Any]]) -> str:
    """Canonical Solidity signature, e.g. ``transfer(address,uint256)``."""
    types = ','.join(_parse_param(param).canonical for param in inputs)
    return f'{name}({types})'


def selector(name: str, inputs: list[dict[str, Any]]) -> str:
    """4-byte function selector (``0x``-prefixed) of the canonical signature."""
    return '0x' + keccak_hex(canonical_signature(name, inputs))[:8]


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def encode_arguments(inputs: list[dict[str, Any]], values: list[Any]) -> bytes:
    """ABI-encode ``values`` as the argument area of a call to ``inputs``.

    JSON-friendly coercion: numeric strings become ints, ``0x`` hex strings
    stay strings unless the type is ``bytes``/``bytesN``/``address``/``bool``.
    """
    if len(inputs) != len(values):
        signature = canonical_signature('f', inputs)
        raise ValueError(f'{signature} expects {len(inputs)} argument(s), got {len(values)}')
    nodes = compile_params(inputs)
    return _encode_sequence(
        nodes, [_coerce(node, value) for value, node in zip(values, nodes, strict=True)]
    )


def _encode_sequence(nodes: tuple[TypeNode, ...] | list[TypeNode], values: list[Any]) -> bytes:
    """Head/tail encoding of an argument sequence (ABI spec layout)."""
    heads: list[bytes | None] = []
    tails: list[bytes] = []
    for node, value in zip(nodes, values, strict=True):
        if node.is_dynamic:
            heads.append(None)
            tails.append(_encode_dynamic(node, value))
        else:
            heads.append(_encode_static(node, value))
            tails.append(b'')

    offset = sum(node.head_size for node in nodes)
    encoded = b''
    for head, tail in zip(heads, tails, strict=True):
        if head is None:
            encoded += offset.to_bytes(32, 'big')
            offset += len(tail)
        else:
            encoded += head
    for tail in tails:
        encoded += tail
    return encoded


def _encode_static(node: TypeNode, value: Any) -> bytes:
    """Encode a statically-sized value (exactly ``static_size`` bytes)."""
    if node.kind == 'uint':
        number = _coerce_int(value)
        if not 0 <= number < 2**node.bits:
            raise ValueError(f'{node.canonical} out of range: {value!r}')
        return number.to_bytes(32, 'big')
    if node.kind == 'int':
        number = _coerce_int(value)
        if not -(2 ** (node.bits - 1)) <= number < 2 ** (node.bits - 1):
            raise ValueError(f'{node.canonical} out of range: {value!r}')
        return (number % 2**256).to_bytes(32, 'big')
    if node.kind in ('ufixed', 'fixed'):
        scaled = Decimal(str(value)).scaleb(node.decimals)
        if scaled != scaled.to_integral_value():
            raise ValueError(f'{node.canonical} cannot represent {value!r} exactly')
        number = int(scaled)
        low, high = (
            (0, 2**node.bits)
            if node.kind == 'ufixed'
            else (-(2 ** (node.bits - 1)), 2 ** (node.bits - 1))
        )
        if not low <= number < high:
            raise ValueError(f'{node.canonical} out of range: {value!r}')
        return (number % 2**256).to_bytes(32, 'big')
    if node.kind == 'bool':
        return (1 if value else 0).to_bytes(32, 'big')
    if node.kind == 'address':
        return bytes(12) + _coerce_address(value)
    if node.kind == 'fixed_bytes':
        data = _coerce_hex_bytes(value)
        if len(data) > node.bits:
            raise ValueError(f'{node.canonical} expects at most {node.bits} bytes')
        return data.ljust(32, b'\x00')
    if node.kind == 'array':
        assert node.length is not None and node.elem is not None
        return _encode_sequence([node.elem] * node.length, list(value))
    if node.kind == 'tuple':
        return _encode_sequence(node.components, _tuple_values(node, value))
    raise AbiTypeNotSupportedError(node.canonical)


def _encode_dynamic(node: TypeNode, value: Any) -> bytes:
    """Encode the tail payload of a dynamically-sized value."""
    if node.kind == 'bytes':
        data = _coerce_hex_bytes(value)
        return len(data).to_bytes(32, 'big') + _pad_right(data)
    if node.kind == 'string':
        data = str(value).encode('utf-8')
        return len(data).to_bytes(32, 'big') + _pad_right(data)
    if node.kind == 'array':
        assert node.elem is not None
        items = list(value)
        length_prefix = b'' if node.length is not None else len(items).to_bytes(32, 'big')
        return length_prefix + _encode_sequence([node.elem] * len(items), items)
    if node.kind == 'tuple':
        return _encode_sequence(node.components, _tuple_values(node, value))
    raise AbiTypeNotSupportedError(node.canonical)


def _tuple_values(node: TypeNode, value: Any) -> list[Any]:
    """Align a tuple value (dict by component name, or sequence) with components."""
    if isinstance(value, dict):
        resolved: list[Any] = []
        for index, name in enumerate(node.component_names):
            if name and name in value:
                resolved.append(value[name])
            elif str(index) in value:
                resolved.append(value[str(index)])
            else:
                raise ValueError(f'tuple component {name or index!r} missing from argument')
        return resolved
    items = list(value)
    if len(items) != len(node.components):
        raise ValueError(f'tuple expects {len(node.components)} components, got {len(items)}')
    return items


def _pad_right(data: bytes) -> bytes:
    remainder = len(data) % 32
    return data if remainder == 0 else data + bytes(32 - remainder)


def _coerce_int(value: Any) -> int:
    # Idempotent: accepts pre-coerced ints alongside numeric strings/bools.
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 10)
    raise ValueError(f'cannot encode {value!r} as an integer')


def _coerce_address(value: Any) -> bytes:
    # Idempotent: a pre-coerced 20-byte value passes through unchanged.
    if isinstance(value, bytes | bytearray) and len(value) == 20:
        return bytes(value)
    if isinstance(value, int):
        return value.to_bytes(20, 'big')
    if isinstance(value, str):
        text = value[2:] if value.lower().startswith('0x') else value
        if len(text) != 40:
            raise ValueError(f'invalid address: {value!r}')
        return bytes.fromhex(text)
    raise ValueError(f'cannot encode {value!r} as an address')


def _coerce_hex_bytes(value: Any) -> bytes:
    if isinstance(value, bytes | bytearray):
        return bytes(value)
    if isinstance(value, str):
        text = value[2:] if value.lower().startswith('0x') else value
        return bytes.fromhex(text)
    raise ValueError(f'cannot encode {value!r} as bytes')


def _coerce(node: TypeNode, value: Any) -> Any:
    """Best-effort coercion of JSON-native values to encoder expectations."""
    if node.kind in ('uint', 'int'):
        return _coerce_int(value)
    if node.kind == 'address':
        return _coerce_address(value)
    if node.kind == 'bool':
        if isinstance(value, str):
            if value.lower() in ('true', '1'):
                return True
            if value.lower() in ('false', '0'):
                return False
        return bool(value)
    if node.kind in ('bytes', 'fixed_bytes'):
        return _coerce_hex_bytes(value)
    if node.kind == 'string':
        return value if isinstance(value, str) else str(value)
    if node.kind == 'array':
        return [_coerce(node.elem, item) for item in value] if node.elem else list(value)
    if node.kind == 'tuple':
        return _coerce_tuple(node, value)
    return value


def _coerce_tuple(node: TypeNode, value: Any) -> Any:
    if isinstance(value, dict):
        return value
    return [
        _coerce(component, item) for component, item in zip(node.components, value, strict=True)
    ]


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def decode_values(nodes: tuple[TypeNode, ...], data: bytes) -> list[Any]:
    """Decode ``data`` as the head/tail area of ``nodes``, as native values.

    uint/int stay ``int``, ``bytes``/``bytesN`` stay ``bytes``, arrays and
    tuples are ``list`` — the shape :mod:`aiochainscan.decode` normalises to
    the fastabi JSON convention. Trailing bytes are ignored, matching what
    real calldata carries.
    """
    return _decode_sequence(nodes, data, 0)


def decode_arguments(outputs: list[dict[str, Any]], data: bytes | str) -> dict[str, Any]:
    """Decode raw ``eth_call`` output bytes into a name-keyed dict.

    Unnamed outputs are keyed by their positional index (``'0'``, ``'1'`` …);
    uint/int values become strings (fastabi JSON convention), addresses are
    lowercased hex, bytes values are ``0x``-prefixed.
    """
    raw = _coerce_hex_bytes(data)
    nodes = compile_params(outputs)
    if not any(node.is_dynamic for node in nodes):
        expected = sum(node.head_size for node in nodes)
        if len(raw) != expected:
            raise ValueError(
                f'output data length {len(raw)} does not match ABI-encoded size {expected}'
            )
    values = to_json_values(nodes, _decode_sequence(nodes, raw, 0))
    names = [str(param.get('name') or '') or str(index) for index, param in enumerate(outputs)]
    return dict(zip(names, values, strict=True))


def to_json_values(nodes: tuple[TypeNode, ...], values: list[Any]) -> list[Any]:
    """Convert native decoded values to the fastabi JSON convention."""
    return [_to_json(node, value) for node, value in zip(nodes, values, strict=True)]


def _to_json(node: TypeNode, value: Any) -> Any:
    kind = node.kind
    if kind in ('uint', 'int'):
        return str(value)
    if kind in ('ufixed', 'fixed'):
        # Fixed-point keeps its declared scale rather than normalising, so the
        # rendered string says how many decimals the type carries.
        return format(value, 'f')
    if kind in ('bytes', 'fixed_bytes'):
        return '0x' + bytes(value).hex()
    if kind == 'array':
        assert node.elem is not None
        return [_to_json(node.elem, item) for item in value]
    if kind == 'tuple':
        converted = [
            _to_json(component, item)
            for component, item in zip(node.components, value, strict=True)
        ]
        if node.tuple_keys is not None:
            return dict(zip(node.tuple_keys, converted, strict=True))
        return converted
    return value


def _unsigned_word(node: TypeNode, buf: bytes, offset: int) -> int:
    """Read an unsigned value of ``node.bits`` and reject non-zero padding."""
    value = _read_uint(buf, offset)
    if node.bits != 256 and value >> node.bits:
        raise ValueError(f'{node.canonical}: value does not fit, padding is not zero')
    return value


def _signed_word(node: TypeNode, buf: bytes, offset: int) -> int:
    """Read a two's-complement value of ``node.bits`` and reject bad padding."""
    raw = _read_uint(buf, offset)
    bits = node.bits
    if bits == 256:
        return raw - 2**256 if raw >= 2**255 else raw
    value = raw & ((1 << bits) - 1)
    sign_bit = 1 << (bits - 1)
    negative = bool(value & sign_bit)
    if raw >> bits != ((1 << (256 - bits)) - 1 if negative else 0):
        raise ValueError(f'{node.canonical}: padding is not the sign extension')
    return value - (sign_bit << 1) if negative else value


def _decode_sequence(
    nodes: tuple[TypeNode, ...] | list[TypeNode], buf: bytes, base: int
) -> list[Any]:
    """Decode a head/tail sequence located at ``base`` (offsets are relative)."""
    values: list[Any] = []
    cursor = base
    head_size = sum(node.head_size for node in nodes)
    for node in nodes:
        if node.is_dynamic:
            # A pointer into the head area cannot be what an encoder produced:
            # the tail starts where the head ends.
            pointer = _read_uint(buf, cursor)
            if pointer < head_size:
                raise ValueError(
                    f'{node.canonical}: dynamic offset {pointer} points inside the '
                    f'{head_size}-byte head area'
                )
            values.append(_decode_node(node, buf, base + pointer))
            cursor += 32
        else:
            values.append(_decode_node(node, buf, cursor))
            cursor += node.static_size
    return values


def _decode_node(node: TypeNode, buf: bytes, offset: int) -> Any:
    """Decode a single value of ``node`` at absolute ``offset``."""
    kind = node.kind
    if kind == 'uint':
        return _unsigned_word(node, buf, offset)
    if kind == 'int':
        return _signed_word(node, buf, offset)
    if kind == 'bool':
        word = _read_uint(buf, offset)
        if word > 1:
            raise ValueError(f'bool: word is {word}, not 0 or 1')
        return word == 1
    if kind == 'address':
        if _read_uint(buf, offset) >> 160:
            raise ValueError('address: padding is not zero')
        return '0x' + _slice(buf, offset + 12, offset + 32).hex()
    if kind == 'fixed_bytes':
        width = node.bits
        if width != 32 and any(_slice(buf, offset + width, offset + 32)):
            raise ValueError(f'{node.canonical}: trailing padding is not zero')
        return _slice(buf, offset, offset + width)
    if kind == 'ufixed':
        return Decimal(_unsigned_word(node, buf, offset)).scaleb(-node.decimals)
    if kind == 'fixed':
        return Decimal(_signed_word(node, buf, offset)).scaleb(-node.decimals)
    if kind == 'bytes':
        length = _read_uint(buf, offset)
        return _slice(buf, offset + 32, offset + 32 + length)
    if kind == 'string':
        length = _read_uint(buf, offset)
        return _slice(buf, offset + 32, offset + 32 + length).decode('utf-8')
    if kind == 'array':
        assert node.elem is not None
        if node.length is None:
            count = _read_uint(buf, offset)
            # Bound the count against the buffer BEFORE materialising the node
            # list: a corrupted length word is a 32-byte input that would
            # otherwise ask for gigabytes. Every element occupies at least
            # ``head_size`` bytes of the head area, so this cannot reject a
            # well-formed payload.
            if offset + 32 + count * node.elem.head_size > len(buf):
                raise ValueError(
                    f'{node.canonical} declares {count} items, more than the '
                    f'remaining {len(buf) - offset - 32} bytes can hold'
                )
            return _decode_sequence([node.elem] * count, buf, offset + 32)
        return _decode_sequence([node.elem] * node.length, buf, offset)
    if kind == 'tuple':
        return _decode_sequence(node.components, buf, offset)
    raise AbiTypeNotSupportedError(node.canonical)


def _read_uint(buf: bytes, offset: int) -> int:
    end = offset + 32
    if offset < 0 or end > len(buf):
        raise ValueError(
            f'decoded data references bytes [{offset}:{end}] outside its length {len(buf)}'
        )
    return int.from_bytes(buf[offset:end], 'big')


def _slice(buf: bytes, start: int, end: int) -> bytes:
    if start < 0 or end > len(buf) or start > end:
        raise ValueError(
            f'decoded data references bytes [{start}:{end}] outside its length {len(buf)}'
        )
    return buf[start:end]
