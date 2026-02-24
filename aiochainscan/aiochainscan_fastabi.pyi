"""Type hints for aiochainscan_fastabi Rust module.

All batch functions return JSON strings to avoid GIL blocking during
Python object creation. Use orjson.loads() for fast parsing.
"""

from typing import Any

def decode_input(input_data: bytes, abi_json: str) -> str:
    """Decode a single transaction input (legacy). Returns JSON string."""
    ...

def decode_one(calldata: bytes, abi_json: str) -> str:
    """Decode a single transaction input. Returns JSON string."""
    ...

def decode_one_direct(calldata: bytes, abi: Any) -> str:
    """Decode a single transaction input with direct Python ABI. Returns JSON string."""
    ...

def decode_many(calldatas: list[bytes], abi_json: str) -> str:
    """Decode many transactions. Returns JSON string of list[dict]."""
    ...

def decode_many_direct(calldatas: list[bytes], abi: Any) -> str:
    """Decode many transactions with direct Python ABI. Returns JSON string of list[dict]."""
    ...

def decode_many_hex(hex_inputs: list[str], abi_json: str) -> str:
    """Decode many hex transactions. Returns JSON string of list[dict]."""
    ...

def decode_many_raw(calldatas: list[bytes], abi_json: str) -> str:
    """Decode many transactions as raw tuples. Returns JSON string of [[name, [params]], ...]."""
    ...

def decode_many_flat(calldatas: list[bytes], abi_json: str) -> str:
    """Decode many transactions as flat lists. Returns JSON string of [[name, param1, ...], ...]."""
    ...
