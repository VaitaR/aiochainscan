"""Type hints for aiochainscan_fastabi Rust module."""

from typing import Dict, List, Any

def decode_input(input_data: bytes, abi_json: str) -> str:
    """
    Legacy JSON-based decode function for backward compatibility.
    
    Args:
        input_data: Raw transaction input bytes
        abi_json: ABI definition as JSON string
        
    Returns:
        JSON string containing decoded function name and parameters
        
    Raises:
        ValueError: If ABI JSON is invalid or decoding fails
    """
    ...

def decode_one(calldata: bytes, abi_json: str) -> Dict[str, Any]:
    """
    Decode a single transaction input (zero-copy).
    
    Args:
        calldata: Raw transaction input bytes
        abi_json: ABI definition as JSON string
        
    Returns:
        Dictionary with 'function_name' and 'decoded_data' keys
        
    Raises:
        ValueError: If ABI JSON is invalid or decoding fails
    """
    ...

def decode_many(calldatas: List[bytes], abi_json: str) -> List[Dict[str, Any]]:
    """
    Decode multiple transaction inputs in batch (zero-copy).
    
    Args:
        calldatas: List of raw transaction input bytes
        abi_json: ABI definition as JSON string
        
    Returns:
        List of dictionaries with 'function_name' and 'decoded_data' keys
        
    Raises:
        ValueError: If ABI JSON is invalid or decoding fails
    """
    ...