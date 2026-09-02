"""Minimal pure-Python Solidity ABI codec for ``read_contract``.

The fastabi Rust extension decodes transaction *inputs* (selector-addressed
calldata), but ``read_contract`` needs the mirror direction: encode a
function call from auto-fetched ABI + JSON arguments, and decode the raw
``eth_call`` output bytes. This module provides exactly that without new
dependencies (keccak comes from :mod:`aiochainscan.crypto`):

- :func:`canonical_signature` / :func:`selector` — 4-byte function selectors.
- :func:`encode_arguments` — head/tail ABI encoding with JSON-friendly
  argument coercion (numeric strings → ints, ``0x`` hex → bytes).
- :func:`decode_arguments` — decode raw output bytes into a name-keyed dict
  (uint/int values become strings, mirroring the fastabi i64 JSON convention).

Supported types: ``uintN``/``intN``, ``address``, ``bool``, ``bytesN``,
``bytes``, ``string``, fixed/dynamic arrays and (nested) tuples.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..crypto import keccak_hex

__all__ = [
    'canonical_signature',
    'decode_arguments',
    'encode_arguments',
    'selector',
]

_I64_MAX = 2**63 - 1
_I64_MIN = -(2**63)
_BASE_ALIASES = {
    'uint': 'uint256',
    'int': 'int256',
    'byte': 'bytes1',
    'fixed': 'fixed128x18',
    'ufixed': 'ufixed128x18',
    'function': 'bytes24',
}


@dataclass
class TypeNode:
    """Parsed ABI type with canonical form and structural children."""

    canonical: str
    kind: str  # uint | int | address | bool | fixed_bytes | bytes | string | array | tuple
    bits: int = 0  # uint/int width or bytesN width
    length: int | None = None  # fixed-array length; None for dynamic
    elem: TypeNode | None = None
    components: list[TypeNode] = field(default_factory=list)
    raw_components: list[dict[str, Any]] = field(default_factory=list)
    """Original ABI dicts of tuple components (names for dict alignment)."""

    @property
    def is_dynamic(self) -> bool:
        if self.kind in ('bytes', 'string'):
            return True
        if self.kind == 'array':
            return self.length is None or (self.elem is not None and self.elem.is_dynamic)
        if self.kind == 'tuple':
            return any(component.is_dynamic for component in self.components)
        return False

    @property
    def head_size(self) -> int:
        """Bytes occupied in the head area (32 for dynamic offsets)."""
        if self.is_dynamic:
            return 32
        return self.static_size

    @property
    def static_size(self) -> int:
        if self.kind in ('uint', 'int', 'bool', 'address', 'fixed_bytes'):
            return 32
        if self.kind == 'array':
            assert self.length is not None and self.elem is not None
            return self.length * self.elem.static_size
        if self.kind == 'tuple':
            return sum(component.static_size for component in self.components)
        return 32  # dynamic types never reach here (head_size intercepts)


def _parse_param(param: dict[str, Any]) -> TypeNode:
    """Parse one ABI parameter (``type`` + ``components``) into a TypeNode."""
    type_name = str(param.get('type', ''))
    components = param.get('components') or []

    if type_name.endswith(']'):
        bracket = type_name.rfind('[')
        inner = _parse_param({**param, 'type': type_name[:bracket]})
        suffix = type_name[bracket:]
        length: int | None = None
        size_text = suffix[1:-1]
        if size_text:
            length = int(size_text)
        return TypeNode(
            canonical=inner.canonical + suffix,
            kind='array',
            length=length,
            elem=inner,
        )

    base = _BASE_ALIASES.get(type_name, type_name)
    if base == 'tuple':
        parsed = [_parse_param(component) for component in components]
        canonical = f"({','.join(node.canonical for node in parsed)})"
        return TypeNode(
            canonical=canonical,
            kind='tuple',
            components=parsed,
            raw_components=components,
        )
    if base.startswith('uint') and base[4:].isdigit():
        return TypeNode(canonical=base, kind='uint', bits=int(base[4:]))
    if base.startswith('int') and base[3:].isdigit():
        return TypeNode(canonical=base, kind='int', bits=int(base[3:]))
    if base == 'address':
        return TypeNode(canonical=base, kind='address')
    if base == 'bool':
        return TypeNode(canonical=base, kind='bool')
    if base == 'string':
        return TypeNode(canonical=base, kind='string')
    if base == 'bytes':
        return TypeNode(canonical=base, kind='bytes')
    if base.startswith('bytes') and base[5:].isdigit():
        return TypeNode(canonical=base, kind='fixed_bytes', bits=int(base[5:]))
    raise ValueError(f'Unsupported ABI type: {type_name!r}')


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
    nodes = [_parse_param(param) for param in inputs]
    return _encode_sequence(
        nodes, [_coerce(node, value) for value, node in zip(values, nodes, strict=True)]
    )


def _encode_sequence(nodes: list[TypeNode], values: list[Any]) -> bytes:
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
    raise ValueError(f'Unsupported static type: {node.canonical}')


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
        nodes = [node.elem] * len(items)
        return length_prefix + _encode_sequence(nodes, items)
    if node.kind == 'tuple':
        return _encode_sequence(node.components, _tuple_values(node, value))
    raise ValueError(f'Unsupported dynamic type: {node.canonical}')


def _tuple_values(node: TypeNode, value: Any) -> list[Any]:
    """Align a tuple value (dict by component name, or sequence) with components."""
    if isinstance(value, dict):
        names = [str(component.get('name') or '') for component in node.raw_components]
        resolved: list[Any] = []
        for index, name in enumerate(names):
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


def decode_arguments(outputs: list[dict[str, Any]], data: bytes | str) -> dict[str, Any]:
    """Decode raw ``eth_call`` output bytes into a name-keyed dict.

    Unnamed outputs are keyed by their positional index (``'0'``, ``'1'`` …);
    uint/int values become strings (fastabi JSON convention), addresses are
    lowercased hex, bytes values are ``0x``-prefixed.
    """
    raw = _coerce_hex_bytes(data)
    nodes = [_parse_param(param) for param in outputs]
    if not any(node.is_dynamic for node in nodes):
        expected = sum(node.head_size for node in nodes)
        if len(raw) != expected:
            raise ValueError(
                f'output data length {len(raw)} does not match ABI-encoded size {expected}'
            )
    values = _decode_sequence(nodes, raw, 0)
    names: list[str] = []
    for index, param in enumerate(outputs):
        name = str(param.get('name') or '')
        names.append(name if name else str(index))
    return dict(zip(names, values, strict=True))


def _decode_sequence(nodes: list[TypeNode], buf: bytes, base: int) -> list[Any]:
    """Decode a head/tail sequence located at ``base`` (offsets are relative)."""
    values: list[Any] = []
    cursor = base
    for node in nodes:
        if node.is_dynamic:
            offset = _read_uint(buf, cursor)
            values.append(_decode_node(node, buf, base + offset))
            cursor += 32
        else:
            values.append(_decode_node(node, buf, cursor))
            cursor += node.static_size
    return values


def _decode_node(node: TypeNode, buf: bytes, offset: int) -> Any:
    """Decode a single value of ``node`` at absolute ``offset``."""
    if node.kind == 'uint':
        return str(_read_uint(buf, offset))
    if node.kind == 'int':
        return str(_read_int(buf, offset))
    if node.kind == 'bool':
        return _read_uint(buf, offset) != 0
    if node.kind == 'address':
        return '0x' + _slice(buf, offset + 12, offset + 32).hex()
    if node.kind == 'fixed_bytes':
        return '0x' + _slice(buf, offset, offset + node.bits).hex()
    if node.kind == 'bytes':
        length = _read_uint(buf, offset)
        data = _slice(buf, offset + 32, offset + 32 + length)
        return '0x' + data.hex()
    if node.kind == 'string':
        length = _read_uint(buf, offset)
        return _slice(buf, offset + 32, offset + 32 + length).decode('utf-8')
    if node.kind == 'array':
        assert node.elem is not None
        if node.length is None:
            count = _read_uint(buf, offset)
            nodes = [node.elem] * count
            return _decode_sequence(nodes, buf, offset + 32)
        nodes = [node.elem] * node.length
        return _decode_sequence(nodes, buf, offset)
    if node.kind == 'tuple':
        names = node.raw_components
        values = _decode_sequence(node.components, buf, offset)
        if all(str(item.get('name') or '') for item in names):
            keys = [str(item['name']) for item in names]
            return dict(zip(keys, values, strict=True))
        return values
    raise ValueError(f'Unsupported type in decode: {node.canonical}')


def _read_uint(buf: bytes, offset: int) -> int:
    return int.from_bytes(_slice(buf, offset, offset + 32), 'big')


def _read_int(buf: bytes, offset: int) -> int:
    value = _read_uint(buf, offset)
    return value - 2**256 if value >= 2**255 else value


def _slice(buf: bytes, start: int, end: int) -> bytes:
    if start < 0 or end > len(buf) or start > end:
        raise ValueError(
            f'decoded data references bytes [{start}:{end}] outside its length {len(buf)}'
        )
    return buf[start:end]
