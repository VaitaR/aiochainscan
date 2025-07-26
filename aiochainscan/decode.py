import requests
from Crypto.Hash import keccak
from eth_abi import decode

FUNCTION_SELECTOR_LENGTH = 10  # '0x' + 4 bytes


class SignatureDatabase:
    """A class for interacting with an online signature database with in-memory caching."""

    def __init__(self):
        self.cache: dict[str, str] = {}
        self.api_url = 'https://www.4byte.directory/api/v1/signatures/?hex_signature='

    def get_function_signature(self, selector: str) -> str | None:
        if selector in self.cache:
            return self.cache[selector]

        try:
            response = requests.get(f'{self.api_url}{selector}', timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('results'):
                    signature = data['results'][0]['text_signature']
                    self.cache[selector] = signature  # Save to cache
                    return signature
        except requests.RequestException:
            pass  # Ignore network errors, we just can't find the signature

        return None


# Create a single global instance
sig_db = SignatureDatabase()


def _preprocess_abi(abi: list) -> tuple[dict, dict]:
    """Pre-processes an ABI list into lookup maps for functions and events."""
    function_map = {}
    event_map = {}

    for item in abi:
        item_type = item.get('type')
        if item_type == 'function':
            name = item.get('name', '')
            inputs = ','.join([param['type'] for param in item.get('inputs', [])])
            signature_text = f'{name}({inputs})'
            # 4-byte selector
            selector = '0x' + keccak_hash(signature_text)[:8]
            function_map[selector] = item
        elif item_type == 'event':
            name = item.get('name', '')
            inputs = ','.join([param['type'] for param in item.get('inputs', [])])
            signature_text = f'{name}({inputs})'
            # 32-byte topic hash
            topic_hash = '0x' + keccak_hash(signature_text)
            event_map[topic_hash] = item

    return function_map, event_map


def _convert_bytes_to_hex(data):
    """Recursively traverses data structures and converts bytes to hex strings."""
    if isinstance(data, bytes):
        return '0x' + data.hex()
    if isinstance(data, dict):
        return {key: _convert_bytes_to_hex(value) for key, value in data.items()}
    if isinstance(data, list | tuple):
        return type(data)([_convert_bytes_to_hex(item) for item in data])
    return data


# Function to generate Keccak hash of the input text
def keccak_hash(text):
    k = keccak.new(digest_bits=256)
    k.update(text.encode('utf-8'))
    return k.hexdigest()


# Function to decode transaction input and return updated transaction with decoded data
def decode_transaction_input(transaction: dict, abi: list):
    function_map, _ = _preprocess_abi(abi)

    if not transaction.get('input') or len(transaction['input']) < FUNCTION_SELECTOR_LENGTH:
        transaction['decoded_func'] = ''
        transaction['decoded_data'] = {}
        return transaction

    func_selector = transaction['input'][:FUNCTION_SELECTOR_LENGTH]
    function = function_map.get(func_selector)

    if function:
        # Decode input transaction
        input_types = [param['type'] for param in function['inputs']]
        input_data = transaction['input'][FUNCTION_SELECTOR_LENGTH:]
        try:
            decoded_input = decode(input_types, bytes.fromhex(input_data))

            # Assign the function name directly to transaction
            transaction['decoded_func'] = function['name']

            # Create a new dictionary for decoded transaction
            decoded_transaction = dict(
                zip([param['name'] for param in function['inputs']], decoded_input, strict=False)
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

    return transaction


def generate_function_abi(signature: str) -> list:
    # Extract the function name and parameters from the signature
    func_name, params = signature.split('(')
    params = params[:-1]  # Remove the trailing ')'

    # Create a list of dictionaries for each parameter
    inputs = []

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
    function_abi = [
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
    transaction: dict, signature_name: str = 'function_name'
):
    signature = transaction[signature_name]
    function_abi = generate_function_abi(signature)
    transaction = decode_transaction_input(transaction, function_abi)
    return transaction


# Function to decode transaction input and return updated log with decoded data
def decode_log_data(log: dict, abi: list):
    _, event_map = _preprocess_abi(abi)

    if not log.get('topics'):
        # A log without topics cannot be decoded
        return log

    receipt_event_signature_hex = log['topics'][0]
    event = event_map.get(receipt_event_signature_hex)

    if event:
        decoded_log = {'event': event['name']}

        # Decode indexed topics
        indexed_params = [input for input in event['inputs'] if input['indexed']]
        for i, param in enumerate(indexed_params):
            topic = log['topics'][i + 1]
            decoded_log[param['name']] = decode([param['type']], bytes.fromhex(topic[2:]))[0]

        # Decode non-indexed data
        non_indexed_params = [input for input in event['inputs'] if not input['indexed']]
        if log.get('data', '0x') != '0x':
            non_indexed_types = [param['type'] for param in non_indexed_params]
            non_indexed_values = decode(non_indexed_types, bytes.fromhex(log['data'][2:]))
            for i, param in enumerate(non_indexed_params):
                decoded_log[param['name']] = non_indexed_values[i]

        log['decoded_data'] = decoded_log
    # If no matching event was found, 'decoded_data' will not be in log
    # which is the desired behavior.

    if log.get('decoded_data'):
        log['decoded_data'] = _convert_bytes_to_hex(log['decoded_data'])

    return log


def decode_input_with_online_lookup(transaction: dict) -> dict:
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
