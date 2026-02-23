"""
MCP (Model Context Protocol) Server for aiochainscan.

Run with: python -m aiochainscan.mcp_server
Or: uv run -m aiochainscan.mcp_server

This exposes blockchain data tools to AI agents (Claude Desktop, Cursor, etc.)
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP as FastMCPType
else:
    FastMCPType = Any

try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    FastMCP = None  # type: ignore[misc, assignment]

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method


def create_mcp_server() -> FastMCPType:
    """Create and configure the MCP server with blockchain tools."""

    if not MCP_AVAILABLE:
        raise ImportError(
            'MCP not installed. Install with: pip install aiochainscan[mcp] or pip install mcp'
        )

    mcp = FastMCP('aiochainscan')

    @mcp.tool()
    async def get_wallet_balance(address: str, network: str = 'ethereum') -> str:
        """
        Get the native token (ETH, MATIC, etc.) balance of a blockchain wallet.

        Use this tool to check how much native cryptocurrency a wallet holds.
        Do NOT use this for ERC20/ERC721 tokens - use get_token_portfolio instead.

        Args:
            address: The 0x-prefixed hexadecimal wallet address (42 characters).
            network: The blockchain network. Options: ethereum, polygon, arbitrum,
                     optimism, base, gnosis, bsc. Default: ethereum.

        Returns:
            A formatted string with the balance in human-readable format.
        """
        async with ChainscanClient.from_config('blockscout_v2', network) as client:
            balance_wei = await client.call(Method.ACCOUNT_BALANCE, address=address)
            balance_eth = (
                int(balance_wei) / 10**18 if isinstance(balance_wei, str) else balance_wei / 10**18
            )
            return f'Balance: {balance_eth:.6f} (Native Token on {network})'

    @mcp.tool()
    async def get_recent_transactions(
        address: str, network: str = 'ethereum', limit: int = 10
    ) -> str:
        """
        Get recent transactions for a wallet address.

        Use this to see the latest activity on a blockchain wallet.
        Returns transaction hashes, values, and timestamps.

        Args:
            address: The 0x-prefixed wallet address.
            network: The blockchain network (ethereum, polygon, etc.).
            limit: Maximum number of transactions to return (1-50). Default: 10.

        Returns:
            A formatted list of recent transactions.
        """
        limit = min(max(1, limit), 50)  # Clamp between 1-50

        async with ChainscanClient.from_config('blockscout_v2', network) as client:
            txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address=address)
            items = txs[:limit] if isinstance(txs, list) else txs.get('items', [])[:limit]

            if not items:
                return f'No transactions found for {address} on {network}'

            result = [f'Recent {len(items)} transactions for {address[:10]}...:\n']
            for tx in items:
                tx_hash = tx.get('hash', '')[:16]
                value = int(tx.get('value', 0)) / 10**18
                result.append(f'  • {tx_hash}... | {value:.4f} ETH')

            return '\n'.join(result)

    @mcp.tool()
    async def get_token_portfolio(address: str, network: str = 'ethereum') -> str:
        """
        Get all ERC20 tokens held by a wallet.

        Use this to see which tokens (USDT, USDC, UNI, etc.) a wallet holds.
        This is different from native balance - use get_wallet_balance for ETH/MATIC.

        Args:
            address: The 0x-prefixed wallet address.
            network: The blockchain network.

        Returns:
            A list of tokens with symbols and balances.
        """
        async with ChainscanClient.from_config('blockscout_v2', network) as client:
            tokens = await client.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address=address)
            items = tokens[:20] if isinstance(tokens, list) else tokens.get('items', [])[:20]

            if not items:
                return f'No tokens found for {address} on {network}'

            result = [f'Token portfolio for {address[:10]}... ({len(items)} tokens):\n']
            for token in items:
                token_info = token.get('token', {})
                symbol = token_info.get('symbol', '???')
                decimals = int(token_info.get('decimals', 18))
                value = int(token.get('value', 0))
                balance = value / (10**decimals) if decimals > 0 else value
                result.append(f'  • {symbol}: {balance:,.4f}')

            return '\n'.join(result)

    return mcp


# CLI entry point
if __name__ == '__main__':
    if not MCP_AVAILABLE:
        print('Error: MCP not installed. Run: pip install mcp')
        exit(1)

    server: FastMCPType = create_mcp_server()
    server.run()
