from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from hashlib import blake2b
from typing import Any, cast

import orjson

from aiochainscan.abi_pure import TypeNode, compile_params, decode_values
from aiochainscan.crypto import keccak_hex
from aiochainscan.exceptions import (
    AbiTypeNotSupportedError,
    ChainscanDependencyError,
    PureAbiDecodeWarning,
)

# Malformed calldata must stay non-fatal: a spam transaction whose selector
# happens to collide must not crash a decode loop.
_MALFORMED_CALLDATA_ERRORS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    IndexError,
    AttributeError,
)


def _abi_decode_params(
    params: list[dict[str, Any]],
    data: bytes,
    index: _AbiIndex | None = None,
    plan_key: str | None = None,
) -> Sequence[Any]:
    """Decode an ABI parameter sequence on the pure-Python floor.

    Second and last tier of the decode chain — fastabi decodes whole calldata
    upstream and never reaches here. Returns native Python values (``int``,
    ``bytes``, …), normalised to the fastabi JSON convention by
    :func:`_to_rust_convention`.

    ``index`` + ``plan_key`` memoise the compiled decode plan across every
    item decoded against the same ABI.
    """
    nodes = None if index is None or plan_key is None else index.nodes.get(plan_key)
    if nodes is None:
        nodes = compile_params(params)
        if index is not None and plan_key is not None:
            index.nodes[plan_key] = nodes
    return decode_values(nodes, data)


# orjson is a required dependency — always available
ORJSON_AVAILABLE = True


def _parse_json(json_str: str) -> Any:
    """Parse JSON string using orjson."""
    return orjson.loads(json_str)


# The Rust tier must agree with the pure-Python floor on decode semantics
# (UTF-8 string validity, dynamic-value padding, full-width fixed point). Those
# rules landed in the accelerator at 0.2.0, so an older locally built extension
# would silently decode by the pre-strict rules while this module decodes by the
# new ones. Refuse it and use the floor instead.
_MIN_FASTABI_VERSION = (0, 2, 0)


def _parse_extension_version(raw: object) -> tuple[int, ...] | None:
    """Return an extension version as a comparable tuple, or None if unreadable."""
    if not isinstance(raw, str):
        return None
    parts: list[int] = []
    for chunk in raw.split('.')[:3]:
        digits = ''
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            return None
        parts.append(int(digits))
    return tuple(parts) or None


def _require_strict_fastabi(module: Any) -> None:
    """Raise ImportError when the loaded extension predates the strict semantics."""
    version = _parse_extension_version(getattr(module, '__version__', None))
    if version is not None and version >= _MIN_FASTABI_VERSION:
        return
    reported = getattr(module, '__version__', None) or 'unknown (pre-0.2.0)'
    warnings.warn(
        f'Ignoring the aiochainscan-fastabi extension at {module.__file__}: it reports '
        f'version {reported}, but strict ABI decode semantics require '
        f'{".".join(str(part) for part in _MIN_FASTABI_VERSION)} or newer. '
        'Decoding falls back to the pure-Python backend. Rebuild with: '
        'cd aiochainscan/fastabi && maturin develop --release',
        PureAbiDecodeWarning,
        stacklevel=2,
    )
    raise ImportError('aiochainscan-fastabi is older than the strict decode semantics')


# Try to import fastabi Rust backend. The accelerator is now the top-level
# `aiochainscan_fastabi` distribution (separate from the pure-Python
# `aiochainscan` package — see docs/V1_PLAN.md Track A); an existing
# maturin/editable checkout may still build it as `aiochainscan.aiochainscan_fastabi`,
# so that name is tried second.
try:
    import importlib

    try:
        _fastabi = importlib.import_module('aiochainscan_fastabi')
    except ImportError:
        # Legacy location — resolved dynamically so import-linter's static
        # graph doesn't see decode.py depending on the whole `aiochainscan`
        # package (this branch never runs a real cross-layer import).
        _fastabi = importlib.import_module('aiochainscan.aiochainscan_fastabi')

    _require_strict_fastabi(_fastabi)

    _fast_decode_input_json = _fastabi.decode_input
    _fast_decode_many_json = _fastabi.decode_many

    FASTABI_AVAILABLE = True
    # decode_many_to_arrow only exists when fastabi was built with the
    # off-by-default `arrow` cargo feature (see fastabi/Cargo.toml).
    ARROW_AVAILABLE = hasattr(_fastabi, 'decode_many_to_arrow')

    def _fast_decode_to_arrow(calldatas: list[bytes], abi_json: str) -> Any:
        """Decode many transactions and return Arrow RecordBatch (zero-copy)."""
        if not ARROW_AVAILABLE:
            raise ChainscanDependencyError(
                'Arrow zero-copy requires fastabi built with the "arrow" cargo feature: '
                'cd aiochainscan/fastabi && maturin develop --release --features arrow'
            )
        return _fastabi.decode_many_to_arrow(calldatas, abi_json)

    # Wrapper functions that parse JSON returned from Rust
    # This avoids GIL blocking - orjson is optimized for fast object creation
    def _fast_decode_input(input_bytes: bytes, abi_json: str) -> dict[str, Any]:
        """Decode single transaction using Rust + orjson for Python object creation."""
        return cast(dict[str, Any], _parse_json(_fast_decode_input_json(input_bytes, abi_json)))

    def _fast_decode_many(calldatas: list[bytes], abi_json: str) -> list[dict[str, Any]]:
        """Decode many transactions using Rust + orjson for Python object creation."""
        return cast(list[dict[str, Any]], _parse_json(_fast_decode_many_json(calldatas, abi_json)))

except ImportError:
    FASTABI_AVAILABLE = False
    ARROW_AVAILABLE = False

FUNCTION_SELECTOR_LENGTH = 10  # '0x' + 4 bytes


def _split_array_suffix(type_name: str) -> tuple[str, str]:
    """Return an ABI type's base name and its complete array suffix."""
    end = len(type_name)
    while end and type_name[:end].endswith(']'):
        start = type_name.rfind('[', 0, end)
        if start < 0:
            break
        end = start
    return type_name[:end], type_name[end:]


def canonical_abi_type(param: dict[str, Any]) -> str:
    """Build an ABI canonical type, including recursively nested tuples."""
    type_name = cast(str, param.get('type', ''))
    base, suffix = _split_array_suffix(type_name)
    aliases = {
        'uint': 'uint256',
        'int': 'int256',
        'byte': 'bytes1',
        'fixed': 'fixed128x18',
        'ufixed': 'ufixed128x18',
    }
    base = aliases.get(base, base)
    if base == 'tuple':
        components = cast(list[dict[str, Any]], param.get('components', []))
        base = f"({','.join(canonical_abi_type(component) for component in components)})"
    return base + suffix


def _abi_type_is_dynamic(param: dict[str, Any]) -> bool:
    """Return whether an indexed value is represented by a topic hash."""
    type_name = cast(str, param.get('type', ''))
    base, suffix = _split_array_suffix(type_name)
    if suffix:
        return True
    if base == 'tuple':
        return True
    return base in {'bytes', 'string'}


@dataclass(slots=True)
class _AbiIndex:
    """Everything derived from one ABI list, derived once.

    Building the maps keccak-hashes every function and event signature (~120 µs
    for a 20-function ABI), which the batch and streaming paths would otherwise
    repeat per item. ``abi_json`` keeps the serialized ABI the Rust tier is
    handed, so the single and batch fast paths stop re-serializing per call.
    ``nodes`` then memoises each parameter list's compiled decode plan, keyed
    by selector / topic hash.
    """

    function_map: dict[str, dict[str, Any]]
    event_map: dict[str, dict[str, Any]]
    abi_json: str
    nodes: dict[str, tuple[TypeNode, ...]] = field(default_factory=dict)


_ABI_INDEX_BY_DIGEST: dict[bytes, _AbiIndex] = {}
_ABI_INDEX_BY_IDENTITY: dict[int, tuple[list[dict[str, Any]], _AbiIndex]] = {}
_ABI_MAPS_CACHE_MAX = 64


def _abi_index(abi: list[dict[str, Any]]) -> _AbiIndex:
    """Return the cached index for ``abi``, building it on first sight.

    Two levels, because hashing the ABI costs more than everything else on the
    decode path for a large ABI: an identity lookup first (callers hand the
    same list object to every item of a batch), then a content digest. The
    identity level retains the list, so ``is`` can never match a recycled
    address; it does go stale if a caller mutates an ABI list *in place*
    between decodes, which no caller in this library does.

    The index is built from a round-trip of the serialized ABI rather than
    from ``abi`` itself, so it shares no mutable state with the caller. A
    content digest means one index serves every equal ABI list, and without
    the copy an in-place mutation of one list would change how every other
    one decodes. The payload is retained on the index (``abi_json``): it is
    byte-for-byte what the fast tier is handed, so the JSON hand-off costs
    nothing per call.
    """
    by_identity = _ABI_INDEX_BY_IDENTITY.get(id(abi))
    if by_identity is not None and by_identity[0] is abi:
        return by_identity[1]

    payload = orjson.dumps(abi)
    digest = blake2b(payload, digest_size=16).digest()
    index = _ABI_INDEX_BY_DIGEST.get(digest)
    if index is None:
        parsed = cast('list[dict[str, Any]]', orjson.loads(payload))
        index = _build_abi_index(parsed, payload.decode())
        if len(_ABI_INDEX_BY_DIGEST) >= _ABI_MAPS_CACHE_MAX:
            _ABI_INDEX_BY_DIGEST.clear()
        _ABI_INDEX_BY_DIGEST[digest] = index
    if len(_ABI_INDEX_BY_IDENTITY) >= _ABI_MAPS_CACHE_MAX:
        _ABI_INDEX_BY_IDENTITY.clear()
    _ABI_INDEX_BY_IDENTITY[id(abi)] = (abi, index)
    return index


def _preprocess_abi(
    abi: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Pre-process an ABI list into lookup maps for functions and events."""
    index = _abi_index(abi)
    return index.function_map, index.event_map


def _build_abi_index(
    abi: list[dict[str, Any]],
    abi_json: str,
) -> _AbiIndex:
    """Build the lookup maps; ``abi_json`` rides along for the Rust hand-off."""
    function_map: dict[str, dict[str, Any]] = {}
    event_map: dict[str, dict[str, Any]] = {}

    for item in abi:
        item_type = cast(str | None, item.get('type'))
        if item_type == 'function':
            name = cast(str, item.get('name', ''))
            inputs_list = cast(list[dict[str, Any]], item.get('inputs', []))
            inputs = ','.join(canonical_abi_type(param) for param in inputs_list)
            signature_text = f'{name}({inputs})'
            # 4-byte selector
            selector = '0x' + keccak_hash(signature_text)[:8]
            function_map[selector] = item
        elif item_type == 'event':
            name = cast(str, item.get('name', ''))
            inputs_list = cast(list[dict[str, Any]], item.get('inputs', []))
            inputs = ','.join(canonical_abi_type(param) for param in inputs_list)
            signature_text = f'{name}({inputs})'
            # 32-byte topic hash
            topic_hash = '0x' + keccak_hash(signature_text)
            if item.get('anonymous') is not True:
                event_map[topic_hash.lower()] = item

    return _AbiIndex(function_map=function_map, event_map=event_map, abi_json=abi_json)


def _to_rust_convention(data: Any) -> Any:
    """Normalise decoded values to what the Rust backend serializes.

    ``bytes`` become ``0x`` hex, ints outside i64 become strings, and arrays
    and tuples both become ``list`` (the pure floor returns Python tuples) --
    so a decoded value does not change shape when a user adds or drops
    ``[fastabi]``. One traversal, not one per rule: this runs on every
    pure-floor decode.
    """
    if isinstance(data, bytes):
        return '0x' + data.hex()
    if isinstance(data, int):
        # bool is an int subclass and always falls inside the range, so it
        # survives as a bool.
        if data > 9223372036854775807 or data < -9223372036854775808:
            return str(data)
        return data
    if isinstance(data, dict):
        return {key: _to_rust_convention(value) for key, value in data.items()}
    if isinstance(data, list | tuple):
        return [_to_rust_convention(item) for item in data]
    return data


# Function to generate Keccak hash of the input text
def keccak_hash(text: str) -> str:
    return keccak_hex(text)


# The tier-switch tuple: errors that make the single fast path (and the whole
# fast batch) retry on the pure floor. AbiTypeNotSupportedError is a ValueError
# subclass and rides along, exactly as in the literal tuple this replaced —
# the floor re-raises it after its own attempt.
_FALLBACK_ERRORS: tuple[type[BaseException], ...] = (
    ValueError,
    KeyError,
    TypeError,
    RuntimeError,
)


def _declares_selector(index: _AbiIndex, raw_input: str) -> bool:
    """Whether the ABI behind ``index`` declares the function the calldata selects.

    Takes the index (not the ABI list) because every caller already holds it:
    the seam must not re-derive the index just to ask this.
    """
    return raw_input[:FUNCTION_SELECTOR_LENGTH] in index.function_map


def _mark_empty(transaction: dict[str, Any]) -> dict[str, Any]:
    """Mark one transaction as undecoded: no function name, no decoded data."""
    transaction['decoded_func'] = ''
    transaction['decoded_data'] = {}
    return transaction


def _rejects_input(transaction: dict[str, Any]) -> bool:
    """Whether ``transaction`` carries no decodable calldata.

    THE input-rejection predicate, written once and only here: an input that
    is missing, empty, or shorter than a function selector can select nothing
    on any tier against any ABI. ``_decode_one``'s guard and every entry
    point's pre-check ask this question — and the entry points must ask it
    BEFORE building the ABI index, so a structurally malformed ABI cannot
    raise for input that would never reach it (the pre-C6 order).
    """
    raw_input: str = transaction.get('input') or ''
    return not raw_input or len(raw_input) < FUNCTION_SELECTOR_LENGTH


def _decode_one(
    transaction: dict[str, Any],
    index: _AbiIndex,
    fast: Callable[[bytes, str], dict[str, Any]] | None = None,
    fast_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The one per-item decode seam every entry point shares.

    Owns the per-item plumbing exactly once: the input-length guard and the
    empty mark, the ``0x`` strip, the ABI→JSON hand-off (``index.abi_json``),
    the gated fast→pure fall-through, and the tier-switch exception tuple.

    ``fast`` is the single-item Rust callable (single fast path);
    ``fast_result`` is an answer already fetched for this item (batch path).
    On the single fast path everything from the fetch to the marking sits
    inside the tier-switch try, so any failure retries on the pure floor;
    the batch path enters with ``fast_result`` directly, so an unexpected
    answer shape propagates and the whole-batch fallback owns it.
    """
    # The shared input-rejection predicate: missing/empty/too-short input can
    # select nothing, on any tier, against any ABI.
    if _rejects_input(transaction):
        return _mark_empty(transaction)

    # typing.cast is a real call at runtime; annotated locals cost nothing.
    # ``or ''`` keeps the annotation honest: the guard above already rejected
    # missing and empty inputs, so this is a truthy string of selector length+.
    raw_input: str = transaction.get('input') or ''

    if fast_result is not None:
        # An empty function name means the fast tier did not recognise the
        # call -- including when it cannot build a signature for a type it does
        # not implement (fixed-point). The pure floor covers the whole
        # spec, so let it try, but only for a selector this ABI actually
        # declares: an unknown selector decodes to nothing on either tier.
        # THE fall-through rule — written here and only here.
        if not fast_result['function_name'] and _declares_selector(index, raw_input):
            fast_result = None
        else:
            transaction['decoded_func'] = fast_result['function_name']
            transaction['decoded_data'] = fast_result['decoded_data']
            return transaction

    elif fast is not None:
        try:
            hex_body = raw_input[2:] if raw_input.startswith('0x') else raw_input
            # Re-enter with the fetched answer: fall-through and marking live
            # in the fast_result branch above, so the rule is written once.
            return _decode_one(
                transaction, index, fast_result=fast(bytes.fromhex(hex_body), index.abi_json)
            )
        except _FALLBACK_ERRORS:
            pass

    # Pure floor: decode against the plan memoised in the index.
    func_selector = raw_input[:FUNCTION_SELECTOR_LENGTH]
    function = index.function_map.get(func_selector)

    if function:
        input_params: list[dict[str, Any]] = function['inputs']
        try:
            decoded_input = _abi_decode_params(
                input_params,
                bytes.fromhex(raw_input[FUNCTION_SELECTOR_LENGTH:]),
                index,
                func_selector,
            )

            # Assign the function name directly to transaction
            transaction['decoded_func'] = function['name']

            # Create a new dictionary for decoded transaction
            transaction['decoded_data'] = dict(
                zip(
                    [param['name'] for param in input_params],
                    decoded_input,
                    strict=False,
                )
            )
        except AbiTypeNotSupportedError:
            # A gap in this library, not malformed calldata — never silenced.
            raise
        except _MALFORMED_CALLDATA_ERRORS as e:
            _mark_empty(transaction)
            # Log at debug level to help with troubleshooting
            import logging

            logging.getLogger(__name__).debug(
                'Failed to decode transaction input: %s - %s', type(e).__name__, e
            )
    else:
        # No matching function found, assign empty values
        _mark_empty(transaction)

    if transaction.get('decoded_data'):
        transaction['decoded_data'] = _to_rust_convention(transaction['decoded_data'])

    return transaction


def _decode_transaction_input_fast(
    transaction: dict[str, Any], abi: list[dict[str, Any]]
) -> dict[str, Any]:
    """Fast Rust-based transaction input decoding."""
    # Guard before indexing: the ABI is never read for undecodable input.
    if _rejects_input(transaction):
        return _mark_empty(transaction)
    return _decode_one(transaction, _abi_index(abi), _fast_decode_input)


def _decode_transaction_input_python(
    transaction: dict[str, Any], abi: list[dict[str, Any]]
) -> dict[str, Any]:
    """Python-based transaction input decoding (fallback)."""
    # Guard before indexing: the ABI is never read for undecodable input.
    if _rejects_input(transaction):
        return _mark_empty(transaction)
    return _decode_one(transaction, _abi_index(abi))


# Main function that uses fast Rust backend or falls back to Python
def decode_transaction_input(
    transaction: dict[str, Any], abi: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Decode transaction input and return updated transaction with decoded data.
    Uses fast Rust backend when available, falls back to Python implementation.
    """
    # Guard before indexing: the ABI is never read for undecodable input.
    if _rejects_input(transaction):
        return _mark_empty(transaction)
    return _decode_one(
        transaction, _abi_index(abi), _fast_decode_input if FASTABI_AVAILABLE else None
    )


def _split_top_level(text: str) -> list[str]:
    """Split comma-separated text while retaining nested tuple expressions."""
    parts: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(text):
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == ',' and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def _matching_paren(text: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == '(':
            depth += 1
        elif text[index] == ')':
            depth -= 1
            if depth == 0:
                return index
    raise ValueError('Unbalanced parentheses in ABI signature')


def _parameter_name(tokens: list[str], index: int) -> str:
    ignored = {'memory', 'calldata', 'storage', 'indexed', 'payable'}
    names = [token for token in tokens if token not in ignored]
    return names[-1] if names else f'param_{index}'


def _parse_signature_parameter(text: str, index: int) -> dict[str, Any]:
    """Parse one human-readable ABI parameter, recursively expanding tuples."""
    text = text.strip()
    if text.startswith('(') or text.startswith('tuple('):
        opening = text.find('(')
        closing = _matching_paren(text, opening)
        components = [
            _parse_signature_parameter(component, component_index)
            for component_index, component in enumerate(
                _split_top_level(text[opening + 1 : closing])
            )
            if component
        ]
        position = closing + 1
        while position < len(text) and text[position] == '[':
            array_end = text.find(']', position)
            if array_end < 0:
                raise ValueError('Unbalanced array suffix in ABI signature')
            position = array_end + 1
        suffix = text[closing + 1 : position]
        name = _parameter_name(text[position:].strip().split(), index)
        return {'type': 'tuple' + suffix, 'name': name, 'components': components}

    tokens = text.split()
    if not tokens:
        raise ValueError('Empty parameter in ABI signature')
    return {'type': tokens[0], 'name': _parameter_name(tokens[1:], index)}


def generate_function_abi(signature: str) -> list[dict[str, Any]]:
    opening = signature.find('(')
    if opening < 0:
        raise ValueError('ABI function signature must contain parentheses')
    closing = _matching_paren(signature, opening)
    func_name = signature[:opening].strip()
    params = signature[opening + 1 : closing]
    inputs = [
        _parse_signature_parameter(param, index)
        for index, param in enumerate(_split_top_level(params))
        if param
    ]

    # Construct the ABI
    function_abi: list[dict[str, Any]] = [
        {
            'type': 'function',
            'name': func_name.strip(),
            'inputs': inputs,
            'outputs': [],  # Assuming the function does not return any values
            'stateMutability': 'nonpayable',  # Default state, may need to be adjusted based on function specifics
        }
    ]

    return function_abi


def decode_transaction_input_with_function_name(
    transaction: dict[str, Any], signature_name: str = 'function_name'
) -> dict[str, Any]:
    signature = transaction[signature_name]
    function_abi = generate_function_abi(signature)
    transaction = decode_transaction_input(transaction, function_abi)
    return transaction


def _decode_event_candidate(
    event: dict[str, Any],
    indexed_topics: list[str],
    data: str,
    index: _AbiIndex | None = None,
    plan_key: str | None = None,
) -> dict[str, Any] | None:
    """Decode one event candidate, returning None when its payload is invalid."""
    try:
        decoded_log: dict[str, Any] = {'event': event['name']}
        inputs = cast(list[dict[str, Any]], event.get('inputs', []))
        indexed_params = [param for param in inputs if param.get('indexed') is True]
        for position, (param, topic) in enumerate(
            zip(indexed_params, indexed_topics, strict=True)
        ):
            if _abi_type_is_dynamic(param):
                value: Any = topic.lower()
            else:
                topic_data = topic[2:] if topic[:2].lower() == '0x' else topic
                value = _abi_decode_params(
                    [param],
                    bytes.fromhex(topic_data),
                    index,
                    None if plan_key is None else f'{plan_key}#{position}',
                )[0]
            decoded_log[cast(str, param.get('name', ''))] = value

        non_indexed_params = [param for param in inputs if param.get('indexed') is not True]
        if non_indexed_params:
            data_bytes = data[2:] if data[:2].lower() == '0x' else data
            non_indexed_values = _abi_decode_params(
                non_indexed_params, bytes.fromhex(data_bytes), index, plan_key
            )
            for param, value in zip(non_indexed_params, non_indexed_values, strict=True):
                decoded_log[cast(str, param.get('name', ''))] = value
        return decoded_log
    except AbiTypeNotSupportedError:
        # Not "this candidate does not match" — the codec cannot express the
        # type at all, and every candidate would fail the same way.
        raise
    except Exception:
        return None


# Function to decode transaction input and return updated log with decoded data
def decode_log_data(log: dict[str, Any], abi: list[dict[str, Any]]) -> dict[str, Any]:
    index = _abi_index(abi)
    event_map = index.event_map

    topics = cast(list[str], log.get('topics', []))
    event: dict[str, Any] | None = None
    anonymous_candidates: list[dict[str, Any]] = []
    indexed_topics = topics[1:]
    if topics:
        event = event_map.get(topics[0].lower())
        if event is not None:
            indexed_topics = topics[1:]
        else:
            anonymous_candidates = [
                item
                for item in abi
                if item.get('type') == 'event' and item.get('anonymous') is True
            ]
    else:
        anonymous_candidates = [
            item for item in abi if item.get('type') == 'event' and item.get('anonymous') is True
        ]

    if event is None:
        matching = [
            item
            for item in anonymous_candidates
            if sum(
                1
                for param in cast(list[dict[str, Any]], item.get('inputs', []))
                if param.get('indexed') is True
            )
            == len(topics)
        ]
        data = cast(str, log.get('data', '0x'))
        decoded_candidates = [
            decoded
            for position, candidate in enumerate(matching)
            if (
                decoded := _decode_event_candidate(
                    candidate, topics, data, index, f'anon:{len(topics)}:{position}'
                )
            )
            is not None
        ]
        if len(decoded_candidates) == 1:
            log['decoded_data'] = decoded_candidates[0]
    elif (
        decoded := _decode_event_candidate(
            event, indexed_topics, cast(str, log.get('data', '0x')), index, topics[0].lower()
        )
    ) is not None:
        log['decoded_data'] = decoded
    # If no matching event was found, 'decoded_data' will not be in log
    # which is the desired behavior.

    if log.get('decoded_data'):
        log['decoded_data'] = _to_rust_convention(log['decoded_data'])

    return log


# Below this many items a bulk decode on the pure floor is not slow enough to be
# worth a message; above it the Rust backend is the difference between
# milliseconds and a visible pause.
_BULK_WARNING_THRESHOLD = 50
_bulk_warning_emitted = False


def _warn_bulk_on_pure_floor(count: int) -> None:
    """Warn once per process that a bulk decode is running without fastabi."""
    global _bulk_warning_emitted
    if _bulk_warning_emitted or FASTABI_AVAILABLE or count < _BULK_WARNING_THRESHOLD:
        return
    _bulk_warning_emitted = True
    warnings.warn(
        f'Decoding {count} inputs on the pure-Python backend. '
        "Install 'aiochainscan[fastabi]' for the Rust decoder "
        '(roughly an order of magnitude faster on bulk workloads).',
        PureAbiDecodeWarning,
        stacklevel=3,
    )


def decode_transaction_inputs_batch(
    transactions: list[dict[str, Any]], abi: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Decode multiple transaction inputs in batch for optimal performance.
    Uses fast Rust backend when available, falls back to Python implementation.

    Args:
        transactions: List of transaction dictionaries with 'input' field
        abi: ABI definition as list of dictionaries

    Returns:
        List of transaction dictionaries with decoded_func and decoded_data fields
    """
    if not FASTABI_AVAILABLE or not transactions:
        # Fallback to individual Python decoding
        _warn_bulk_on_pure_floor(len(transactions))
        return [decode_transaction_input(tx, abi) for tx in transactions]

    try:
        # Prepare data for batch processing
        calldatas: list[bytes] = []
        valid_indices: list[int] = []

        for i, tx in enumerate(transactions):
            if not _rejects_input(tx):
                input_hex = tx['input']
                if input_hex.startswith('0x'):
                    input_hex = input_hex[2:]
                calldatas.append(bytes.fromhex(input_hex))
                valid_indices.append(i)
            else:
                # Mark invalid transactions
                valid_indices.append(-1)

        if not calldatas:
            # No valid transactions, return with empty decoded fields
            for tx in transactions:
                _mark_empty(tx)
            return transactions

        index = _abi_index(abi)

        # Call optimized Rust batch decoder with GIL release
        decoded_results = _fast_decode_many(calldatas, index.abi_json)

        # Map results back to transactions (optimized)
        result_idx = 0
        for i, tx in enumerate(transactions):
            if valid_indices[i] != -1:
                # Valid transaction with result — the seam applies the gated
                # fall-through or the fast answer; an unexpected answer shape
                # raises into the whole-batch fallback below.
                _decode_one(tx, index, fast_result=decoded_results[result_idx])
                result_idx += 1
            else:
                # Invalid transaction
                _decode_one(tx, index)

        return transactions

    except _FALLBACK_ERRORS:
        # Fallback to Python implementation on any error
        return [decode_transaction_input(tx, abi) for tx in transactions]
