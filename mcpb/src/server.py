"""stdio entry point for the MCPB bundle.

The bundle ships no code of its own: ``mcpb/pyproject.toml`` pins the
published ``aiochainscan[mcp]`` release and the host installs it with uv, so
this file only starts the same server as ``aiochainscan mcp``.

Nothing may be written to stdout here: it is the transport.
"""

from __future__ import annotations

import sys


def main() -> None:
    from aiochainscan.mcp_server import MCP_AVAILABLE, create_mcp_server

    if not MCP_AVAILABLE:
        print('MCP not installed. The bundle pins aiochainscan[mcp].', file=sys.stderr)
        raise SystemExit(1)

    create_mcp_server().run()


if __name__ == '__main__':
    main()
