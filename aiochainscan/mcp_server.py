"""
MCP (Model Context Protocol) server entry point for aiochainscan.

Run with: python -m aiochainscan.mcp_server
Or: uv run -m aiochainscan.mcp_server

Exposes blockchain data tools to AI agents (Claude Desktop, Cursor, etc.)
over stdio. The implementation lives in :mod:`aiochainscan.mcp`
(envelope/cursors/tools in :mod:`aiochainscan.mcp.tools`, FastMCP wiring in
:mod:`aiochainscan.mcp.server`); this module only preserves the historical
``create_mcp_server`` import path and the CLI entry point.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiochainscan.mcp.server import TOOL_NAMES

__all__ = ['MCP_AVAILABLE', 'TOOL_NAMES', 'create_mcp_server']

from aiochainscan.mcp.server import MCP_AVAILABLE, TOOL_NAMES, create_mcp_server

# CLI entry point
if __name__ == '__main__':
    if not MCP_AVAILABLE:
        print('Error: MCP not installed. Run: pip install aiochainscan[mcp]')
        raise SystemExit(1)

    create_mcp_server().run()
