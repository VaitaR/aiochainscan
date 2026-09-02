#!/usr/bin/env python3
"""
06_multichain_comparison.py - Compare Data Across Blockchains

Advanced example: Query the same address across multiple chains.
Useful for portfolio tracking and cross-chain analytics.

Supported networks (BlockScout V2):
- ethereum, polygon, arbitrum, optimism, base, gnosis, zksync, scroll, linea, celo, rootstock
"""

import asyncio
from dataclasses import dataclass

from aiochainscan.core.client import ChainscanClient
from aiochainscan.domain.method import Method


@dataclass
class ChainBalance:
    """Balance on a specific chain."""

    chain: str
    native_balance: float
    native_symbol: str
    token_count: int
    is_active: bool


# Chain configurations
CHAINS = {
    'ethereum': {'symbol': 'ETH', 'name': 'Ethereum'},
    'polygon': {'symbol': 'MATIC', 'name': 'Polygon'},
    'arbitrum': {'symbol': 'ETH', 'name': 'Arbitrum One'},
    'optimism': {'symbol': 'ETH', 'name': 'Optimism'},
    'base': {'symbol': 'ETH', 'name': 'Base'},
    'gnosis': {'symbol': 'xDAI', 'name': 'Gnosis Chain'},
}


async def check_chain(chain: str, address: str) -> ChainBalance:
    """Check balance on a specific chain."""

    config = CHAINS.get(chain, {'symbol': '???', 'name': chain})

    try:
        client = ChainscanClient.from_config('blockscout_v2', chain)

        try:
            # Get native balance - BlockScout V2 returns string
            balance_data = await client.call(Method.ACCOUNT_BALANCE, address=address)

            native_balance = 0.0
            if isinstance(balance_data, str):
                native_balance = int(balance_data) / 1e18
            elif isinstance(balance_data, dict):
                native_balance = int(balance_data.get('coin_balance', 0)) / 1e18

            # Get token count - BlockScout V2 returns list directly
            tokens_data = await client.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address=address)

            if isinstance(tokens_data, list):
                token_count = len(tokens_data)
            elif isinstance(tokens_data, dict):
                token_count = len(tokens_data.get('items', []))
            else:
                token_count = 0

            return ChainBalance(
                chain=config['name'],
                native_balance=native_balance,
                native_symbol=config['symbol'],
                token_count=token_count,
                is_active=native_balance > 0 or token_count > 0,
            )

        finally:
            await client.close()

    except Exception:
        return ChainBalance(
            chain=config['name'],
            native_balance=0.0,
            native_symbol=config['symbol'],
            token_count=0,
            is_active=False,
        )


async def main():
    """Check wallet across multiple chains."""

    # Address to check (should be active on multiple chains)
    address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'  # Vitalik

    print('🌐 Multi-Chain Portfolio Analysis')
    print('=' * 60)
    print(f'Address: {address[:20]}...\n')

    # Check all chains concurrently
    tasks = [check_chain(chain, address) for chain in CHAINS]

    print('🔄 Querying chains...')
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Display results
    print('\n📊 Results:\n')
    print(f'{"Chain":<20} {"Balance":<20} {"Tokens":<10} {"Status":<10}')
    print('-' * 60)

    active_chains = 0
    total_tokens = 0

    for result in results:
        if isinstance(result, ChainBalance):
            status = '✅ Active' if result.is_active else '⬜ Empty'
            balance_str = f'{result.native_balance:.4f} {result.native_symbol}'

            print(f'{result.chain:<20} {balance_str:<20} {result.token_count:<10} {status:<10}')

            if result.is_active:
                active_chains += 1
                total_tokens += result.token_count
        else:
            print(f'{"Error":<20} {str(result)[:40]}')

    # Summary
    print('\n' + '=' * 60)
    print(f'📈 Summary: Active on {active_chains}/{len(CHAINS)} chains')
    print(f'   Total token types across chains: {total_tokens}')


if __name__ == '__main__':
    asyncio.run(main())
