from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import orjson

from aiochainscan.crypto import keccak_hex
from aiochainscan.exceptions import ChainscanDependencyError

_eth_abi_decode: Any
try:
    from eth_abi.abi import decode as _eth_abi_decode

    ETH_ABI_AVAILABLE = True
except ImportError:
    _eth_abi_decode = None
    ETH_ABI_AVAILABLE = False


def _abi_decode(types: list[str], data: bytes) -> tuple[Any, ...]:
    """Pure-Python ABI decode fallback for environments without fastabi."""
    if _eth_abi_decode is None:
        raise ChainscanDependencyError(
            'Pure-Python ABI decoding requires eth-abi. The fastabi Rust extension '
            'covers decoding in all wheel installs; otherwise run: '
            'pip install "aiochainscan[fallback]"'
        )
    return cast('tuple[Any, ...]', _eth_abi_decode(types, data))


# orjson is a required dependency — always available
ORJSON_AVAILABLE = True


def _parse_json(json_str: str) -> Any:
    """Parse JSON string using orjson."""
    return orjson.loads(json_str)


# Try to import fastabi Rust backend
try:
    from aiochainscan.aiochainscan_fastabi import decode_input as _fast_decode_input_json
    from aiochainscan.aiochainscan_fastabi import decode_many as _fast_decode_many_json
    from aiochainscan.aiochainscan_fastabi import (
        decode_many_direct as _fast_decode_many_direct_json,
    )
    from aiochainscan.aiochainscan_fastabi import decode_many_flat as _fast_decode_many_flat_json
    from aiochainscan.aiochainscan_fastabi import decode_many_hex as _fast_decode_many_hex_json
    from aiochainscan.aiochainscan_fastabi import decode_many_raw as _fast_decode_many_raw_json
    from aiochainscan.aiochainscan_fastabi import (
        decode_many_to_arrow as _fast_decode_many_to_arrow,
    )
    from aiochainscan.aiochainscan_fastabi import decode_one as _fast_decode_one_json
    from aiochainscan.aiochainscan_fastabi import decode_one_direct as _fast_decode_one_direct_json

    FASTABI_AVAILABLE = True
    ARROW_AVAILABLE = True

    def _fast_decode_to_arrow(calldatas: list[bytes], abi_json: str) -> Any:
        """Decode many transactions and return Arrow RecordBatch (zero-copy)."""
        return _fast_decode_many_to_arrow(calldatas, abi_json)

    # Wrapper functions that parse JSON returned from Rust
    # This avoids GIL blocking - orjson is optimized for fast object creation
    def _fast_decode_input(input_bytes: bytes, abi_json: str) -> dict[str, Any]:
        """Decode single transaction using Rust + orjson for Python object creation."""
        return cast(dict[str, Any], _parse_json(_fast_decode_input_json(input_bytes, abi_json)))

    def _fast_decode_one(calldata: bytes, abi_json: str) -> dict[str, Any]:
        """Decode single transaction using Rust + orjson for Python object creation."""
        return cast(dict[str, Any], _parse_json(_fast_decode_one_json(calldata, abi_json)))

    def _fast_decode_one_direct(calldata: bytes, abi: list[dict[str, Any]]) -> dict[str, Any]:
        """Decode single transaction using Rust + orjson for Python object creation."""
        return cast(dict[str, Any], _parse_json(_fast_decode_one_direct_json(calldata, abi)))

    def _fast_decode_many(calldatas: list[bytes], abi_json: str) -> list[dict[str, Any]]:
        """Decode many transactions using Rust + orjson for Python object creation."""
        return cast(list[dict[str, Any]], _parse_json(_fast_decode_many_json(calldatas, abi_json)))

    def _fast_decode_many_direct(
        calldatas: list[bytes], abi: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Decode many transactions using Rust + orjson for Python object creation."""
        return cast(
            list[dict[str, Any]], _parse_json(_fast_decode_many_direct_json(calldatas, abi))
        )

    def _fast_decode_many_hex(hex_inputs: list[str], abi_json: str) -> list[dict[str, Any]]:
        """Decode many hex transactions using Rust + orjson for Python object creation."""
        return cast(
            list[dict[str, Any]], _parse_json(_fast_decode_many_hex_json(hex_inputs, abi_json))
        )

    def _fast_decode_many_raw(calldatas: list[bytes], abi_json: str) -> list[list[Any]]:
        """Decode many transactions as raw tuples using Rust + orjson."""
        return cast(list[list[Any]], _parse_json(_fast_decode_many_raw_json(calldatas, abi_json)))

    def _fast_decode_many_flat(calldatas: list[bytes], abi_json: str) -> list[list[Any]]:
        """Decode many transactions as flat lists using Rust + orjson."""
        return cast(list[list[Any]], _parse_json(_fast_decode_many_flat_json(calldatas, abi_json)))

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


def _preprocess_abi(
    abi: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Pre-processes an ABI list into lookup maps for functions and events."""
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

    return function_map, event_map


def _convert_bytes_to_hex(data: Any) -> Any:
    """Recursively traverses data structures and converts bytes to hex strings."""
    if isinstance(data, bytes):
        return '0x' + data.hex()
    if isinstance(data, dict):
        return {key: _convert_bytes_to_hex(value) for key, value in data.items()}
    if isinstance(data, list | tuple):
        return type(data)([_convert_bytes_to_hex(item) for item in cast(Sequence[Any], data)])
    return data


def _convert_large_ints_to_strings(data: Any) -> Any:
    """Recursively converts large integers to strings for compatibility."""
    if isinstance(data, int):
        # Convert integers larger than i64::MAX to strings for consistency with Rust
        if data > 9223372036854775807 or data < -9223372036854775808:
            return str(data)
        return data
    if isinstance(data, dict):
        return {key: _convert_large_ints_to_strings(value) for key, value in data.items()}
    if isinstance(data, list | tuple):
        return type(data)(
            [_convert_large_ints_to_strings(item) for item in cast(Sequence[Any], data)]
        )
    return data


# Function to generate Keccak hash of the input text
def keccak_hash(text: str) -> str:
    return keccak_hex(text)


def _decode_transaction_input_fast(
    transaction: dict[str, Any], abi: list[dict[str, Any]]
) -> dict[str, Any]:
    """Fast Rust-based transaction input decoding."""
    if not transaction.get('input') or len(transaction['input']) < FUNCTION_SELECTOR_LENGTH:
        transaction['decoded_func'] = ''
        transaction['decoded_data'] = {}
        return transaction

    try:
        # Convert hex input to bytes
        input_hex = transaction['input']
        if input_hex.startswith('0x'):
            input_hex = input_hex[2:]
        input_bytes = bytes.fromhex(input_hex)

        # Convert ABI to JSON string
        abi_json = orjson.dumps(abi).decode()

        # Call Rust decoder - returns parsed dict via orjson
        result = _fast_decode_input(input_bytes, abi_json)

        # Map Rust result format to Python format
        transaction['decoded_func'] = result['function_name']
        transaction['decoded_data'] = result['decoded_data']

        return transaction
    except (ValueError, KeyError, TypeError, RuntimeError):
        # Fallback to Python implementation on any error
        return _decode_transaction_input_python(transaction, abi)


def _decode_transaction_input_python(
    transaction: dict[str, Any], abi: list[dict[str, Any]]
) -> dict[str, Any]:
    """Python-based transaction input decoding (fallback)."""
    function_map, _ = _preprocess_abi(abi)

    if not transaction.get('input') or len(transaction['input']) < FUNCTION_SELECTOR_LENGTH:
        transaction['decoded_func'] = ''
        transaction['decoded_data'] = {}
        return transaction

    func_selector = cast(str, transaction['input'])[:FUNCTION_SELECTOR_LENGTH]
    function = function_map.get(func_selector)

    if function:
        # Decode input transaction
        input_types = [
            canonical_abi_type(param) for param in cast(list[dict[str, Any]], function['inputs'])
        ]
        input_data = cast(str, transaction['input'])[FUNCTION_SELECTOR_LENGTH:]
        try:
            decoded_input = _abi_decode(input_types, bytes.fromhex(input_data))

            # Assign the function name directly to transaction
            transaction['decoded_func'] = function['name']

            # Create a new dictionary for decoded transaction
            decoded_transaction: dict[str, Any] = dict(
                zip(
                    [
                        cast(str, param['name'])
                        for param in cast(list[dict[str, Any]], function['inputs'])
                    ],
                    decoded_input,
                    strict=False,
                )
            )
            transaction['decoded_data'] = decoded_transaction
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as e:
            # ValueError: invalid hex input data
            # TypeError: ABI decoding type errors
            # KeyError: missing dict keys during decode
            # IndexError: tuple unpacking errors
            # AttributeError: method call errors
            transaction['decoded_func'] = ''
            transaction['decoded_data'] = {}
            # Log at debug level to help with troubleshooting
            import logging

            logging.getLogger(__name__).debug(
                'Failed to decode transaction input: %s - %s', type(e).__name__, e
            )
    else:
        # No matching function found, assign empty values
        transaction['decoded_func'] = ''
        transaction['decoded_data'] = {}

    if transaction.get('decoded_data'):
        transaction['decoded_data'] = _convert_bytes_to_hex(transaction['decoded_data'])
        # Convert large integers to strings for compatibility with Rust implementation
        transaction['decoded_data'] = _convert_large_ints_to_strings(transaction['decoded_data'])

    return transaction


# Main function that uses fast Rust backend or falls back to Python
def decode_transaction_input(
    transaction: dict[str, Any], abi: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Decode transaction input and return updated transaction with decoded data.
    Uses fast Rust backend when available, falls back to Python implementation.
    """
    if FASTABI_AVAILABLE:
        return _decode_transaction_input_fast(transaction, abi)
    else:
        return _decode_transaction_input_python(transaction, abi)


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
    event: dict[str, Any], indexed_topics: list[str], data: str
) -> dict[str, Any] | None:
    """Decode one event candidate, returning None when its payload is invalid."""
    try:
        decoded_log: dict[str, Any] = {'event': event['name']}
        inputs = cast(list[dict[str, Any]], event.get('inputs', []))
        indexed_params = [param for param in inputs if param.get('indexed') is True]
        for param, topic in zip(indexed_params, indexed_topics, strict=True):
            if _abi_type_is_dynamic(param):
                value: Any = topic.lower()
            else:
                topic_data = topic[2:] if topic[:2].lower() == '0x' else topic
                value = _abi_decode([canonical_abi_type(param)], bytes.fromhex(topic_data))[0]
            decoded_log[cast(str, param.get('name', ''))] = value

        non_indexed_params = [param for param in inputs if param.get('indexed') is not True]
        if non_indexed_params:
            data_bytes = data[2:] if data[:2].lower() == '0x' else data
            non_indexed_values = _abi_decode(
                [canonical_abi_type(param) for param in non_indexed_params],
                bytes.fromhex(data_bytes),
            )
            for param, value in zip(non_indexed_params, non_indexed_values, strict=True):
                decoded_log[cast(str, param.get('name', ''))] = value
        return decoded_log
    except Exception:
        return None


# Function to decode transaction input and return updated log with decoded data
def decode_log_data(log: dict[str, Any], abi: list[dict[str, Any]]) -> dict[str, Any]:
    _, event_map = _preprocess_abi(abi)

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
            for candidate in matching
            if (decoded := _decode_event_candidate(candidate, topics, data)) is not None
        ]
        if len(decoded_candidates) == 1:
            log['decoded_data'] = decoded_candidates[0]
    elif (
        decoded := _decode_event_candidate(event, indexed_topics, cast(str, log.get('data', '0x')))
    ) is not None:
        log['decoded_data'] = decoded
    # If no matching event was found, 'decoded_data' will not be in log
    # which is the desired behavior.

    if log.get('decoded_data'):
        log['decoded_data'] = _convert_bytes_to_hex(log['decoded_data'])
        log['decoded_data'] = _convert_large_ints_to_strings(log['decoded_data'])

    return log


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
        return [decode_transaction_input(tx, abi) for tx in transactions]

    try:
        # Prepare data for batch processing
        calldatas: list[bytes] = []
        valid_indices: list[int] = []

        for i, tx in enumerate(transactions):
            if tx.get('input') and len(tx['input']) >= FUNCTION_SELECTOR_LENGTH:
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
                tx['decoded_func'] = ''
                tx['decoded_data'] = {}
            return transactions

        # Convert ABI to JSON string
        abi_json = orjson.dumps(abi).decode()

        # Call optimized Rust batch decoder with GIL release
        decoded_results = _fast_decode_many(calldatas, abi_json)

        # Map results back to transactions (optimized)
        result_idx = 0
        for i, tx in enumerate(transactions):
            if valid_indices[i] != -1:
                # Valid transaction with result
                result = decoded_results[result_idx]
                tx['decoded_func'] = result['function_name']
                tx['decoded_data'] = result['decoded_data']
                result_idx += 1
            else:
                # Invalid transaction
                tx['decoded_func'] = ''
                tx['decoded_data'] = {}

        return transactions

    except (ValueError, KeyError, TypeError, RuntimeError):
        # Fallback to Python implementation on any error
        return [decode_transaction_input(tx, abi) for tx in transactions]
