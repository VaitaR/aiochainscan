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
            inputs = ','.join([cast(str, param['type']) for param in inputs_list])
            signature_text = f'{name}({inputs})'
            # 4-byte selector
            selector = '0x' + keccak_hash(signature_text)[:8]
            function_map[selector] = item
        elif item_type == 'event':
            name = cast(str, item.get('name', ''))
            inputs_list = cast(list[dict[str, Any]], item.get('inputs', []))
            inputs = ','.join([cast(str, param['type']) for param in inputs_list])
            signature_text = f'{name}({inputs})'
            # 32-byte topic hash
            topic_hash = '0x' + keccak_hash(signature_text)
            event_map[topic_hash] = item

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
            cast(str, param['type']) for param in cast(list[dict[str, Any]], function['inputs'])
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


def generate_function_abi(signature: str) -> list[dict[str, Any]]:
    # Extract the function name and parameters from the signature
    func_name, params = signature.split('(')
    params = params[:-1]  # Remove the trailing ')'

    # Create a list of dictionaries for each parameter
    inputs: list[dict[str, Any]] = []

    # Handle empty parameters (functions with no arguments)
    if params.strip():
        # Split parameters into individual items
        param_list = params.split(',')

        for param in param_list:
            param_stripped = param.strip()
            if not param_stripped:
                continue

            # Split only on the first space to handle types like 'string memory'
            parts = param_stripped.split(' ', 1)
            if len(parts) == 2:
                param_type, param_name = parts
                inputs.append({'type': param_type.strip(), 'name': param_name.strip()})
            else:
                # Handle parameters without names, e.g., "transfer(address,uint256)"
                inputs.append({'type': parts[0].strip(), 'name': f'param_{len(inputs)}'})

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


# Function to decode transaction input and return updated log with decoded data
def decode_log_data(log: dict[str, Any], abi: list[dict[str, Any]]) -> dict[str, Any]:
    _, event_map = _preprocess_abi(abi)

    if not log.get('topics'):
        # A log without topics cannot be decoded
        return log

    receipt_event_signature_hex = log['topics'][0]
    event = event_map.get(receipt_event_signature_hex)

    if event:
        decoded_log: dict[str, Any] = {'event': event['name']}

        # Decode indexed topics
        indexed_params: list[dict[str, Any]] = [
            input for input in cast(list[dict[str, Any]], event['inputs']) if input['indexed']
        ]
        for i, param in enumerate(indexed_params):
            topic = log['topics'][i + 1]
            decoded_log[cast(str, param['name'])] = _abi_decode(
                [cast(str, param['type'])], bytes.fromhex(cast(str, topic)[2:])
            )[0]

        # Decode non-indexed data
        non_indexed_params: list[dict[str, Any]] = [
            input for input in cast(list[dict[str, Any]], event['inputs']) if not input['indexed']
        ]
        if log.get('data', '0x') != '0x':
            non_indexed_types: list[str] = [
                cast(str, param['type']) for param in non_indexed_params
            ]
            non_indexed_values = _abi_decode(
                non_indexed_types, bytes.fromhex(cast(str, log['data'])[2:])
            )
            for i, param in enumerate(non_indexed_params):
                decoded_log[cast(str, param['name'])] = non_indexed_values[i]

        log['decoded_data'] = decoded_log
    # If no matching event was found, 'decoded_data' will not be in log
    # which is the desired behavior.

    if log.get('decoded_data'):
        log['decoded_data'] = _convert_bytes_to_hex(log['decoded_data'])

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
