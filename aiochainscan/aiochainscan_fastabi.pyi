"""Type hints for aiochainscan_fastabi Rust module.

All batch functions return JSON strings to avoid GIL blocking during
Python object creation. Use orjson.loads() for fast parsing.

Shared decode contract (decode_input, decode_one, decode_one_direct,
decode_many, decode_many_direct, decode_many_hex): an unknown function
selector, undecodable/truncated calldata, or a calldata shorter than a
selector answers ``{"function_name": "", "decoded_data": {}}`` -- the empty
result, never an exception. Only a structurally invalid ABI (unparseable
JSON, or a type ethabi's parser panics on, which is caught and re-raised as
a ValueError) raises. Parameter naming: an unnamed input is keyed
``param_{i}`` by position; a duplicate name keeps the plain spelling only
for the first occurrence, later ones are suffixed ``_2`` -- the same
convention as aiochainscan/decode.py's pure floor.
"""

from typing import Any

__version__: str
"""Extension version, compared by aiochainscan.decode against its minimum."""

def decode_input(input_data: bytes, abi_json: str) -> str:
    """Decode a single transaction input (legacy). Returns JSON string.

    Releases the GIL for the decode; a single-entry micro-cache returns the
    previous answer untouched for an identical (calldata, ABI) pair.
    """
    ...

def decode_one(calldata: bytes, abi_json: str) -> str:
    """Decode a single transaction input. Returns JSON string; the decode
    runs with the GIL released. Empty-result contract, see module docstring."""
    ...

def decode_one_direct(calldata: bytes, abi: Any) -> str:
    """Decode a single transaction input with direct Python ABI. Returns JSON
    string. Empty-result contract, see module docstring."""
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

def decode_many_to_arrow(calldatas: list[bytes], abi_json: str) -> Any:
    """Decode many transactions and return as Arrow RecordBatch (zero-copy to Polars).

    Only present when the extension was built with the ``arrow`` cargo
    feature. Returns a PyArrow-compatible RecordBatch that can be passed
    directly to polars.from_arrow() without any data copying.
    """
    ...

def keccak256(input: bytes) -> bytes:
    """Keccak-256 digest (Ethereum flavor, distinct from NIST SHA-3-256)."""
    ...
