#!/usr/bin/env python3
"""
01_quickstart.py - Getting Started with aiochainscan

This is the simplest way to start using aiochainscan for blockchain data extraction.
Perfect for Data Analysts and Data Engineers who need quick access to on-chain data.

No API key required when using BlockScout V2!
"""

import asyncio

from aiochainscan.core.client import ChainscanClient
from aiochainscan.domain.method import Method


async def main():
    """Basic example: Get wallet balance and recent transactions."""

    # Vitalik's address (well-known public address)
    address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    # Create client for Ethereum mainnet using BlockScout V2 (free, no API key!)
    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    try:
        # 1. Get ETH balance
        print('📊 Fetching wallet data...')
        balance = await client.call(Method.ACCOUNT_BALANCE, address=address)

        # Balance is returned as string in Wei, convert to ETH
        balance_eth = int(balance) / 1e18
        print(f'\n💰 Balance: {balance_eth:.4f} ETH')

        # 2. Get recent transactions (last 10)
        txs = await client.call(
            Method.ACCOUNT_TRANSACTIONS,
            address=address,
        )

        # txs is a list of transactions
        items = txs[:5] if isinstance(txs, list) else []

        print(f'\n📝 Recent Transactions ({len(items)} shown):')
        for tx in items:
            tx_hash = tx.get('hash', '')[:16] + '...'
            value_wei = int(tx.get('value', 0))
            value_eth = value_wei / 1e18
            tx_types = tx.get('transaction_types', ['transfer'])
            tx_type = tx_types[0] if tx_types else 'transfer'
            print(f'  • {tx_hash} | {value_eth:.4f} ETH | {tx_type}')

        # 3. Get token portfolio (all ERC20 tokens)
        print('\n🪙 Token Portfolio:')
        tokens = await client.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address=address)

        # tokens is a list directly
        token_items = tokens[:5] if isinstance(tokens, list) else []
        for token in token_items:
            symbol = token.get('token', {}).get('symbol', '???')
            balance = token.get('value', '0')
            decimals = int(token.get('token', {}).get('decimals', 18))
            balance_human = int(balance) / (10**decimals) if decimals > 0 else 0
            print(f'  • {symbol}: {balance_human:,.2f}')

    finally:
        # Always close the client to release resources
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
