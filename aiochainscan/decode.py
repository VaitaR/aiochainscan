from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

import requests
from Crypto.Hash import keccak
from eth_abi.abi import decode

# Try to import fastabi Rust backend
try:
    from aiochainscan_fastabi import decode_input as _fast_decode_input
    from aiochainscan_fastabi import decode_many as _fast_decode_many
    from aiochainscan_fastabi import decode_many_direct as _fast_decode_many_direct
    from aiochainscan_fastabi import decode_many_hex as _fast_decode_many_hex

    FASTABI_AVAILABLE = True
except ImportError:
    FASTABI_AVAILABLE = False

FUNCTION_SELECTOR_LENGTH = 10  # '0x' + 4 bytes


class SignatureDatabase:
    """A class for interacting with an online signature database with in-memory caching."""

    def __init__(self) -> None:
        self.cache: dict[str, str] = {}
        self.api_url: str = 'https://www.4byte.directory/api/v1/signatures/?hex_signature='

    def get_function_signature(self, selector: str) -> str | None:
        if selector in self.cache:
            return self.cache[selector]

        try:
            response = requests.get(f'{self.api_url}{selector}', timeout=5)
            if response.status_code == 200:
                data = cast(dict[str, Any], response.json())
                results = cast(list[dict[str, Any]] | None, data.get('results'))
                if results:
                    signature = cast(str, results[0]['text_signature'])
                    self.cache[selector] = signature  # Save to cache
                    return signature
        except requests.RequestException:
            pass  # Ignore network errors, we just can't find the signature

        return None


# Create a single global instance
sig_db = SignatureDatabase()


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
    k = keccak.new(digest_bits=256)
    k.update(text.encode('utf-8'))
    return k.hexdigest()


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
        abi_json = json.dumps(abi)

        # Call Rust decoder
        result_json = _fast_decode_input(input_bytes, abi_json)
        result = cast(dict[str, Any], json.loads(result_json))

        # Map Rust result format to Python format
        transaction['decoded_func'] = result['function_name']
        transaction['decoded_data'] = result['decoded_data']

        return transaction
    except Exception:
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
            decoded_input = decode(input_types, bytes.fromhex(input_data))

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
        except Exception:
            transaction['decoded_func'] = ''
            transaction['decoded_data'] = {}
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
            decoded_log[cast(str, param['name'])] = decode(
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
            non_indexed_values = decode(
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


def decode_transaction_inputs_batch_zero_copy(
    transactions: list[dict[str, Any]], abi: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    ULTIMATE zero-copy batch decode: NO JSON, direct Python ABI, GIL release.
    This is the fastest possible implementation with minimal overhead.
    """
    if not FASTABI_AVAILABLE or not transactions:
        # Fallback to regular batch function
        return decode_transaction_inputs_batch(transactions, abi)

    try:
        # Prepare calldata as bytes (no hex parsing overhead)
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
                valid_indices.append(-1)

        if not calldatas:
            # No valid transactions
            for tx in transactions:
                tx['decoded_func'] = ''
                tx['decoded_data'] = {}
            return transactions

        # Call ultimate optimized Rust function (NO JSON!)
        decoded_results = cast(list[dict[str, Any]], _fast_decode_many_direct(calldatas, abi))

        # Map results back (minimal overhead)
        result_idx = 0
        for i, tx in enumerate(transactions):
            if valid_indices[i] != -1:
                result = decoded_results[result_idx]
                tx['decoded_func'] = result['function_name']
                tx['decoded_data'] = result['decoded_data']
                result_idx += 1
            else:
                tx['decoded_func'] = ''
                tx['decoded_data'] = {}

        return transactions

    except Exception:
        # Fallback to regular batch on any error
        return decode_transaction_inputs_batch(transactions, abi)


def decode_transaction_inputs_batch_optimized(
    transactions: list[dict[str, Any]], abi: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Ultra-optimized batch decode with GIL release and hex parsing in Rust.
    Uses the fastest possible path with minimal Python overhead.
    """
    if not FASTABI_AVAILABLE or not transactions:
        # Fallback to regular batch function
        return decode_transaction_inputs_batch(transactions, abi)

    try:
        # Extract hex inputs directly (no bytes conversion in Python)
        hex_inputs: list[str] = []
        valid_indices: list[int] = []

        for i, tx in enumerate(transactions):
            if tx.get('input') and len(tx['input']) >= FUNCTION_SELECTOR_LENGTH:
                hex_inputs.append(tx['input'])
                valid_indices.append(i)
            else:
                valid_indices.append(-1)

        if not hex_inputs:
            # No valid transactions
            for tx in transactions:
                tx['decoded_func'] = ''
                tx['decoded_data'] = {}
            return transactions

        # Convert ABI to JSON once
        abi_json = json.dumps(abi)

        # Call ultimate optimized Rust function
        decoded_results = cast(list[dict[str, Any]], _fast_decode_many_hex(hex_inputs, abi_json))

        # Map results back (minimal overhead)
        result_idx = 0
        for i, tx in enumerate(transactions):
            if valid_indices[i] != -1:
                result = decoded_results[result_idx]
                tx['decoded_func'] = result['function_name']
                tx['decoded_data'] = result['decoded_data']
                result_idx += 1
            else:
                tx['decoded_func'] = ''
                tx['decoded_data'] = {}

        return transactions

    except Exception:
        # Fallback to regular batch on any error
        return decode_transaction_inputs_batch(transactions, abi)


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
        abi_json = json.dumps(abi)

        # Call optimized Rust batch decoder with GIL release
        decoded_results = cast(list[dict[str, Any]], _fast_decode_many(calldatas, abi_json))

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

    except Exception:
        # Fallback to Python implementation on any error
        return [decode_transaction_input(tx, abi) for tx in transactions]


def decode_input_with_online_lookup(transaction: dict[str, Any]) -> dict[str, Any]:
    """
    Attempts to decode transaction input using an online signature database.
    This function makes a network request and may be slower.
    Use it when an ABI is not available.
    """
    tx_copy = transaction.copy()
    func_selector = tx_copy.get('input', '')[:FUNCTION_SELECTOR_LENGTH]

    if len(func_selector) < FUNCTION_SELECTOR_LENGTH:
        tx_copy['decoded_func'] = ''
        tx_copy['decoded_data'] = {}
        return tx_copy

    # 1. Find signature via online database
    signature_text = sig_db.get_function_signature(func_selector)

    if signature_text:
        # 2. If found, generate a temporary ABI
        temp_abi = generate_function_abi(signature_text)

        # 3. Use our fast, optimized function for decoding
        return decode_transaction_input(tx_copy, temp_abi)

    # 4. If nothing is found, return the transaction with empty decoded fields
    tx_copy['decoded_func'] = ''
    tx_copy['decoded_data'] = {}
    return tx_copy
