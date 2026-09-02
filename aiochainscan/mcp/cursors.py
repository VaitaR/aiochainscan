"""Opaque pagination cursors for MCP tools.

The MCP cursor wraps the scanner-level cursor contract from
:mod:`aiochainscan.services.pagination` (``fetch_page`` → ``next_cursor``
merged into the next request) in a Base64URL token the agent never needs to
interpret: responses carry a ready-to-use ``next_call`` with the token already
substituted, so the LLM does not have to understand any pagination schema.

Security model (deliberate, see :func:`decode_tool_cursor`): the token is an
unsigned Base64URL-encoded JSON payload — anyone can forge one. The damage a
forged token can do is bounded by TWO mechanisms applied at merge time:

1. **Tool binding** — every token records the tool that issued it; a token
   presented to a different tool is rejected.
2. **Key whitelist** — only known scanner-cursor keys (page/offset and
   cursor-ish state) may be merged into request params. Resource-identity
   params (address/module/action/contract) can never be overridden by a
   cursor, so a forged token cannot re-target a query.

An HMAC signature would add little for a stdio server: the "secret" would
live in the same process (and thus be readable by the same attacker), so
binding + whitelist is the honest boundary here. Tokens are also versioned
(``v``) so the format can evolve.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterable
from typing import Any

import orjson

__all__ = [
    'CURSOR_VERSION',
    'InvalidCursorError',
    'decode_cursor',
    'decode_tool_cursor',
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


def decode_tool_cursor(
    token: str,
    tool: str,
    allowed_keys: Iterable[str],
) -> dict[str, Any]:
    """Decode and validate a tool-bound cursor before merging it into params.

    Validates the two security invariants described in the module docstring:

    - the token must have been issued by ``tool`` (``'tool'`` payload field);
      a cursor from tool A presented to tool B is rejected;
    - the embedded scanner cursor may only contain pagination keys from
      ``allowed_keys``. Unknown keys — in particular resource-identity
      overrides such as ``address``/``module``/``action`` — are rejected
      instead of silently merged over the tool's computed parameters.

    Returns:
        The validated scanner cursor dict (whitelisted keys only; ``{}`` for
        a cursor-less payload).

    Raises:
        InvalidCursorError: On malformed tokens, tool mismatch or
            non-whitelisted cursor keys.
    """
    payload = decode_cursor(token)
    if payload.get('tool') != tool:
        raise InvalidCursorError(
            f'Cursor was not issued by {tool!r}. Make a new request without the cursor '
            'to start over.'
        )
    cursor = payload.get('cursor')
    if cursor is None:
        return {}
    if not isinstance(cursor, dict):
        raise InvalidCursorError(
            'Cursor payload is malformed. Make a new request without the cursor to start over.'
        )
    allowed = set(allowed_keys)
    unknown = sorted(set(cursor) - allowed)
    if unknown:
        raise InvalidCursorError(
            f'Cursor contains keys not allowed for {tool!r}: {", ".join(unknown)}. '
            'Make a new request without the cursor to start over.'
        )
    return dict(cursor)


def unwrap_scanner_cursor(token: str) -> dict[str, Any]:
    """Extract the scanner cursor dict from an MCP cursor token.

    The scanner cursor is merged on top of the tool's base request params
    (the ``{**params, **cursor}`` contract of ``Scanner.fetch_page``).
    """
    return dict(decode_cursor(token).get('cursor') or {})
