"""MCP (Model Context Protocol) adapter layer for aiochainscan.

Package layout:

- :mod:`aiochainscan.mcp.envelope` — the standardized ``ToolResponse``
  contract (data / notes / instructions / pagination / content_text).
- :mod:`aiochainscan.mcp.cursors` — opaque Base64URL pagination cursors.
- :mod:`aiochainscan.mcp.tools` — the agent-facing tools as plain
  ``client -> ToolResponse`` functions plus the client pool.
- :mod:`aiochainscan.mcp.server` — FastMCP wiring (requires the ``mcp``
  extra; everything else imports without it).

The MCP layer is an adapter over :class:`aiochainscan.ChainscanClient`:
tools compose client methods and never bypass the network layer.
"""

from .cursors import InvalidCursorError, decode_cursor, decode_tool_cursor, encode_cursor
from .envelope import (
    NextCall,
    Pagination,
    ToolResponse,
    build_tool_response,
    format_units,
    truncate_long_strings,
)

__all__ = [
    'InvalidCursorError',
    'NextCall',
    'Pagination',
    'ToolResponse',
    'build_tool_response',
    'decode_cursor',
    'decode_tool_cursor',
    'encode_cursor',
    'format_units',
    'truncate_long_strings',
]
