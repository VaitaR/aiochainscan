import codecs

from Crypto.Hash import keccak
from eth_abi import decode


# Function to generate Keccak hash of the input text
def keccak_hash(text):
    k = keccak.new(digest_bits=256)
    k.update(text.encode('utf-8'))
    return k.hexdigest()


# Function to decode transaction input and return updated transaction with decoded data
def decode_transaction_input(transaction: dict, abi: list):
    function_list = [item for item in abi if item['type'] == 'function']

    # Extract the function selector from the transaction input
    func_selector = transaction['input'][:10]  # '0x' + first 4 bytes
    for function in function_list:
        # Generate function signature hash
        name = function['name']
        inputs = ','.join([param['type'] for param in function['inputs']])
        func_signature_text = f'{name}({inputs})'
        func_signature_hash = (
            '0x' + keccak_hash(func_signature_text)[:8]
        )  # Only need the first 4 bytes

        # Check if the function selector matches
        if func_selector == func_signature_hash:
            # Decode input transaction
            input_types = [param['type'] for param in function['inputs']]
            input_transaction = transaction['input'][
                10:
            ]  # Exclude the first 4 bytes (function selector)
            decoded_input = decode(input_types, codecs.decode(input_transaction, 'hex'))

            # Assign the function name directly to transaction
            transaction['decoded_func'] = name

            # Create a new dictionary for decoded transaction
            decoded_transaction = dict(
                zip([param['name'] for param in function['inputs']], decoded_input, strict=False)
            )

            # Assign the decoded input transaction to 'decoded_transaction' key in the transaction object
            transaction['decoded_data'] = decoded_transaction
            break  # Exit the loop if a matching function is found

    else:
        # TODO check on errors and bugs if function_name not empty
        # No matching function found, assign empty values
        # if transaction['function_name'] and transaction['function_name'] != '':
        #     func_name = transaction['function_name'].split('(',1)[0]

        transaction['decoded_func'] = ''  # should be str as on table
        transaction['decoded_data'] = {}

    # convert bytes data type (ordinary decoded), if it exists, to correctly save in db
    if isinstance(transaction['decoded_data'], dict):
        for key, value in transaction['decoded_data'].items():
            if isinstance(value, bytes):
                transaction['decoded_data'][key] = value.hex().rstrip('0')
            elif isinstance(value, list | tuple):
                # create new list with converted bytes
                converted_list = []
                for item in value:
                    if isinstance(item, bytes):
                        # convert bytes to hex and remove trailing zeros
                        converted_list.append(item.hex().rstrip('0'))
                # replace original list with converted list
                transaction['decoded_data'][key] = converted_list

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
            if param_stripped:  # Skip empty parameters
                parts = param_stripped.split(' ')
                if len(parts) >= 2:
                    param_type = parts[0]
                    param_name = ' '.join(parts[1:])  # Handle names with spaces
                    inputs.append({'type': param_type, 'name': param_name})

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
    receipt_event_signature_hex = log['topics'][0]
    event_list = [item for item in abi if item['type'] == 'event']
    # print('Event list:', event_list)

    for event in event_list:
        # Generate event signature hash
        name = event['name']
        inputs = ','.join([param['type'] for param in event['inputs']])
        event_signature_text = f'{name}({inputs})'
        event_signature_hex = '0x' + keccak_hash(event_signature_text)

        # Check if the event signature matches the log's signature
        if event_signature_hex == receipt_event_signature_hex:
            decoded_log = {'event': event['name']}

            # Decode indexed topics
            indexed_params = [input for input in event['inputs'] if input['indexed']]
            for i, param in enumerate(indexed_params):
                topic = log['topics'][i + 1]
                decoded_log[param['name']] = decode(
                    [param['type']], codecs.decode(topic[2:], 'hex_codec')
                )[0]

            # Decode non-indexed data
            non_indexed_params = [input for input in event['inputs'] if not input['indexed']]
            non_indexed_types = [param['type'] for param in non_indexed_params]
            non_indexed_values = decode(
                non_indexed_types, codecs.decode(log['data'][2:], 'hex_codec')
            )
            for i, param in enumerate(non_indexed_params):
                decoded_log[param['name']] = non_indexed_values[i]

            log['decoded_data'] = decoded_log

            # convert bytes data type (ordinary decoded), if it exists, to correctly save in db
            if isinstance(log['decoded_data'], dict):
                for key, value in log['decoded_data'].items():
                    if isinstance(value, bytes):
                        log['decoded_data'][key] = value.hex()
            break  # Break the inner loop as we've found the matching event

    # If no matching event was found, assign an empty dictionary
    # if 'decoded_data' not in log:
    #     print( f"No matching event found for log: {log}" )

    return log
