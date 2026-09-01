"""Opaque pagination cursors for MCP tools.

The MCP cursor wraps the scanner-level cursor contract from
:mod:`aiochainscan.services.pagination` (``fetch_page`` → ``next_cursor``
merged into the next request) in a Base64URL token the agent never needs to
interpret: responses carry a ready-to-use ``next_call`` with the token already
substituted, so the LLM does not have to understand any pagination schema.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

import orjson

__all__ = [
    'CURSOR_VERSION',
    'InvalidCursorError',
    'decode_cursor',
    'encode_cursor',
    'unwrap_scanner_cursor',
]

CURSOR_VERSION = 1
"""Schema version embedded in every cursor token."""


class InvalidCursorError(ValueError):
    """Raised when a pagination cursor is malformed, foreign or corrupted."""


def encode_cursor(payload: dict[str, Any]) -> str:
    """Serialize a cursor payload into an unpadded Base64URL token."""
    token = base64.urlsafe_b64encode(orjson.dumps({**payload, 'v': CURSOR_VERSION})).decode(
        'ascii'
    )
    return token.rstrip('=')


def decode_cursor(token: str) -> dict[str, Any]:
    """Decode a cursor token produced by :func:`encode_cursor`.

    Raises:
        InvalidCursorError: Empty, non-Base64, non-JSON, or wrong-version
            tokens — with an actionable message ("start over without the
            cursor") for the agent.
    """
    if not token:
        raise InvalidCursorError('Cursor cannot be empty.')
    try:
        padded = token + '=' * (-len(token) % 4)
        payload = orjson.loads(base64.urlsafe_b64decode(padded.encode('ascii')))
    except (
        ValueError,
        TypeError,
        binascii.Error,
        orjson.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        raise InvalidCursorError(
            'Invalid or expired cursor. Make a new request without the cursor to start over.'
        ) from exc
    if not isinstance(payload, dict) or payload.get('v') != CURSOR_VERSION:
        raise InvalidCursorError(
            'Cursor schema not recognized. Make a new request without the cursor to start over.'
        )
    return payload


def unwrap_scanner_cursor(token: str) -> dict[str, Any]:
    """Extract the scanner cursor dict from an MCP cursor token.

    The scanner cursor is merged on top of the tool's base request params
    (the ``{**params, **cursor}`` contract of ``Scanner.fetch_page``).
    """
    return dict(decode_cursor(token).get('cursor') or {})
