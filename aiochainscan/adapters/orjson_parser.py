"""Fast JSON parsing utilities using orjson.

This module provides optimized JSON parsing for blockchain explorer API responses.
orjson is significantly faster than the standard library json module, especially
for large payloads like transaction lists.
"""

from __future__ import annotations

from typing import Any

import orjson


def parse_response(raw_bytes: bytes) -> dict[str, Any]:
    """Parse raw bytes response into a dictionary using orjson.

    Args:
        raw_bytes: Raw bytes from HTTP response body

    Returns:
        Parsed JSON as a dictionary

    Raises:
        orjson.JSONDecodeError: If the input is not valid JSON
    """
    return orjson.loads(raw_bytes)  # type: ignore[no-any-return]


def parse_response_str(raw_str: str) -> dict[str, Any]:
    """Parse string response into a dictionary using orjson.

    Args:
        raw_str: JSON string from HTTP response

    Returns:
        Parsed JSON as a dictionary

    Raises:
        orjson.JSONDecodeError: If the input is not valid JSON
    """
    return orjson.loads(raw_str.encode('utf-8'))  # type: ignore[no-any-return]


def serialize(data: Any) -> bytes:
    """Serialize data to JSON bytes using orjson.

    Args:
        data: Python object to serialize (dict, list, etc.)

    Returns:
        JSON as bytes

    Raises:
        TypeError: If the data contains non-serializable types
    """
    return orjson.dumps(data)


def serialize_str(data: Any) -> str:
    """Serialize data to JSON string using orjson.

    Args:
        data: Python object to serialize (dict, list, etc.)

    Returns:
        JSON as string

    Raises:
        TypeError: If the data contains non-serializable types
    """
    return orjson.dumps(data).decode('utf-8')


def parse_api_result(raw_bytes: bytes) -> Any:
    """Parse API response and extract the result field.

    Most blockchain explorer APIs return responses in format:
    {"status": "1", "message": "OK", "result": <data>}

    This function parses and extracts the result field directly.

    Args:
        raw_bytes: Raw bytes from HTTP response body

    Returns:
        The 'result' field from the response, or the full parsed response
        if no 'result' field exists

    Raises:
        orjson.JSONDecodeError: If the input is not valid JSON
    """
    parsed = orjson.loads(raw_bytes)
    if isinstance(parsed, dict) and 'result' in parsed:
        return parsed['result']
    return parsed


def parse_safe(raw_bytes: bytes, default: Any = None) -> Any:
    """Safely parse JSON with a default value on error.

    Args:
        raw_bytes: Raw bytes to parse
        default: Value to return if parsing fails

    Returns:
        Parsed JSON or default value
    """
    try:
        return orjson.loads(raw_bytes)
    except (orjson.JSONDecodeError, TypeError):
        return default
