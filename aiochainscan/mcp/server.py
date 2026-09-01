"""FastMCP wiring for the aiochainscan MCP server.

Registers the agent-facing tools from :mod:`aiochainscan.mcp.tools` on a
``FastMCP`` instance, converts :class:`ToolResponse` envelopes into MCP
content blocks (compact ``content_text`` for text consumers + the structured
payload as ``structuredContent``), and pools one client per
``(scanner, chain)`` target for the lifetime of the server process.

This is the only module that imports ``mcp``; everything else in the package
works without the ``mcp`` extra.
"""

from __future__ import annotations

from typing import Any

import orjson

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import CallToolResult, TextContent

    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised via test_imports
    MCP_AVAILABLE = False

from . import tools
from .envelope import ToolResponse

__all__ = ['MCP_AVAILABLE', 'TOOL_NAMES', 'create_mcp_server']

TOOL_NAMES = (
    'get_wallet_balance',
    'get_address_overview',
    'get_transactions',
    'get_transaction_info',
    'get_token_portfolio',
    'get_token_info',
    'get_token_holders',
    'get_top_token_holders',
    'get_contract_abi',
    'read_contract',
    'resolve_ens',
    'list_chains',
)

_SERVER_INSTRUCTIONS = """\
aiochainscan MCP server — multi-scanner blockchain data for AI agents.

Conventions:
- Every tool returns an envelope: {data, notes, instructions, pagination}.
  `notes` carry limits/caveats, `instructions` suggest the next call, and
  `pagination.next_call` is a ready-to-execute follow-up when more pages exist.
- Values: Wei-scale amounts are exact strings; human-readable values sit next
  to `_wei`/`_raw` fields. Addresses are EIP-55 checksummed.
- `chain` accepts names ('ethereum', 'base'), numeric IDs (8453) or a
  self-hosted instance URL ('https://my-blockscout.internal').
- `scanner` overrides the data source: 'blockscout' (default, keyless),
  'blockscout_v2', 'etherscan' (needs ETHERSCAN_KEY), 'nodereal' (BSC).
- Tools are read-only and degrade honestly: missing scanner capabilities land
  in `notes` instead of failing the call.
"""

_CHAIN_DOC = (
    'Chain name (e.g. "ethereum", "base", "gnosis"), numeric chain ID (e.g. 8453), '
    'or a self-hosted instance URL (e.g. "https://my-blockscout.internal").'
)
_SCANNER_DOC = (
    'Optional scanner override: "blockscout" (default, keyless, widest free '
    'surface), "blockscout_v2" (keyless), "etherscan" (all chains, needs '
    'ETHERSCAN_KEY) or "nodereal" (BSC). Omit to use the default.'
)
_CURSOR_DOC = 'Opaque pagination cursor from a previous response (pagination.next_cursor).'


def _envelope_result(response: ToolResponse) -> Any:
    """Convert an envelope into an MCP CallToolResult (text + structured)."""
    payload = response.to_payload()
    text = response.content_text or orjson.dumps(payload).decode()
    return CallToolResult(
        content=[TextContent(type='text', text=text)],
        structuredContent=payload,
    )


def create_mcp_server(pool: tools.ClientPool | None = None) -> Any:
    """Build the FastMCP server with all aiochainscan tools registered."""
    if not MCP_AVAILABLE:
        raise ImportError(
            'MCP not installed. Install with: pip install aiochainscan[mcp] or pip install mcp'
        )

    mcp: Any = FastMCP('aiochainscan', instructions=_SERVER_INSTRUCTIONS)
    client_pool = pool if pool is not None else tools.ClientPool()

    @mcp.tool()
    async def get_wallet_balance(
        address: str,
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Get the native coin (ETH/BNB/MATIC...) balance of a wallet.

        Returns Wei (exact string) and a human-readable amount. For ERC-20 or
        NFT holdings use get_token_portfolio / get_address_overview instead.
        """
        client = client_pool.get(scanner, chain)
        return _envelope_result(await tools.get_wallet_balance(client, address))

    @mcp.tool()
    async def get_address_overview(
        address: str,
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Composite address snapshot: balance, newest transactions, ERC-20 tokens and NFT collections.

        Runs all sub-queries concurrently; partial failures are reported in
        `notes` without failing the call.
        """
        client = client_pool.get(scanner, chain)
        return _envelope_result(await tools.get_address_overview(client, address))

    @mcp.tool()
    async def get_transactions(
        address: str,
        cursor: str | None = None,
        limit: int = 50,
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Get one page of an address's transactions (newest first), curated for context economy.

        Use pagination.next_call from the response to fetch subsequent pages.
        """
        client = client_pool.get(scanner, chain)
        return _envelope_result(
            await tools.get_transactions(
                client, address, cursor=cursor, limit=limit, chain=chain, scanner=scanner
            )
        )

    @mcp.tool()
    async def get_transaction_info(
        tx_hash: str,
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Get transaction details with the call input decoded via the contract ABI (fastabi).

        When the recipient contract is verified, decoded_input replaces the raw
        calldata; otherwise raw_input is kept (truncated) with an honest note.
        """
        client = client_pool.get(scanner, chain)
        return _envelope_result(await tools.get_transaction_info(client, tx_hash))

    @mcp.tool()
    async def get_token_portfolio(
        address: str,
        cursor: str | None = None,
        limit: int = 20,
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Get ERC-20 token holdings of an address (one curated page, paginated)."""
        client = client_pool.get(scanner, chain)
        return _envelope_result(
            await tools.get_token_portfolio(
                client, address, cursor=cursor, limit=limit, chain=chain, scanner=scanner
            )
        )

    @mcp.tool()
    async def get_token_info(
        token_address: str,
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Get token metadata: name, symbol, decimals, total supply (raw + formatted), holder count."""
        client = client_pool.get(scanner, chain)
        return _envelope_result(await tools.get_token_info(client, token_address))

    @mcp.tool()
    async def get_token_holders(
        token_address: str,
        cursor: str | None = None,
        limit: int = 50,
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Get token holders (one curated page) with human-readable balances and total counts."""
        client = client_pool.get(scanner, chain)
        return _envelope_result(
            await tools.get_token_holders(
                client, token_address, cursor=cursor, limit=limit, chain=chain, scanner=scanner
            )
        )

    @mcp.tool()
    async def get_top_token_holders(
        token_address: str,
        limit: int = 100,
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Get the top-N holders by balance (order guaranteed; Etherscan PRO — needs scanner "etherscan")."""
        client = client_pool.get(scanner, chain)
        return _envelope_result(await tools.get_top_token_holders(client, token_address, limit))

    @mcp.tool()
    async def get_contract_abi(
        address: str,
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Get a curated summary of a verified contract ABI: function/event signatures.

        read_contract fetches and applies the full ABI automatically — this
        tool is for discovery.
        """
        client = client_pool.get(scanner, chain)
        return _envelope_result(await tools.get_contract_abi(client, address))

    @mcp.tool()
    async def read_contract(
        address: str,
        function_name: str,
        args: str = '[]',
        block: str = 'latest',
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Call a view/pure contract function via auto-fetched ABI + eth_call, outputs decoded.

        No manual ABI needed: the verified ABI is fetched, the function found
        by name, arguments encoded and outputs decoded automatically.
        `args` is a JSON array string, e.g. '["0xabc...", 5]'; numeric strings
        coerce to ints, 0x-hex strings pass through for bytes arguments.
        """
        client = client_pool.get(scanner, chain)
        return _envelope_result(
            await tools.read_contract(client, address, function_name, args=args, block=block)
        )

    @mcp.tool()
    async def resolve_ens(
        name_or_address: str,
        chain: str = 'ethereum',
        scanner: str | None = None,
    ) -> Any:
        """Resolve ENS both directions: 'vitalik.eth' -> address, or address -> ENS name."""
        client = client_pool.get(scanner, chain)
        return _envelope_result(await tools.resolve_ens(client, name_or_address))

    @mcp.tool()
    async def list_chains(query: str | None = None) -> Any:
        """List chains served by these tools, filterable by name/alias/chain-ID substring."""
        return _envelope_result(tools.list_chains(query))

    return mcp
