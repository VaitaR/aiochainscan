#!/usr/bin/env python3
"""
03_multi_wallet_analysis.py - Analyze Multiple Wallets

Advanced example for Data Analysts: Fetch data for multiple addresses
concurrently and aggregate for portfolio analysis.

Use case: Track whale wallets, compare holdings, build dashboards.
"""

import asyncio
from dataclasses import dataclass

from aiochainscan.core.client import ChainscanClient
from aiochainscan.domain.method import Method


@dataclass
class WalletSummary:
    """Summary of wallet holdings."""

    address: str
    eth_balance: float
    token_count: int
    top_tokens: list[tuple[str, float]]  # (symbol, balance)
    tx_count: int


async def analyze_wallet(client: ChainscanClient, address: str) -> WalletSummary:
    """Fetch and analyze a single wallet."""

    # Fetch all data concurrently
    balance_task = client.call(Method.ACCOUNT_BALANCE, address=address)
    tokens_task = client.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address=address)

    balance_data, tokens_data = await asyncio.gather(
        balance_task, tokens_task, return_exceptions=True
    )

    # Parse balance - BlockScout V2 returns string (Wei value)
    eth_balance = 0.0
    if isinstance(balance_data, str):
        eth_balance = int(balance_data) / 1e18
    elif isinstance(balance_data, dict):
        eth_balance = int(balance_data.get('coin_balance', 0)) / 1e18

    # Parse tokens - BlockScout V2 returns list directly
    top_tokens = []
    token_count = 0

    items = []
    if isinstance(tokens_data, list):
        items = tokens_data
    elif isinstance(tokens_data, dict):
        items = tokens_data.get('items', [])

    token_count = len(items)

    # Get top 5 tokens by value
    for item in items[:5]:
        token = item.get('token', {})
        symbol = token.get('symbol', '???')
        decimals = int(token.get('decimals', 18))
        balance = int(item.get('value', 0)) / (10**decimals) if decimals > 0 else 0
        top_tokens.append((symbol, balance))

    return WalletSummary(
        address=address,
        eth_balance=eth_balance,
        token_count=token_count,
        top_tokens=top_tokens,
        tx_count=0,  # Would need separate call
    )


async def main():
    """Analyze multiple wallets and create summary report."""

    # Famous Ethereum wallets (public addresses)
    wallets = [
        ('Vitalik', '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'),
        ('Ethereum Foundation', '0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe'),
        ('Binance Hot Wallet', '0x28C6c06298d514Db089934071355E5743bf21d60'),
    ]

    print('🔍 Multi-Wallet Analysis')
    print('=' * 60)

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    try:
        # Analyze all wallets concurrently
        tasks = [analyze_wallet(client, address) for name, address in wallets]

        summaries = await asyncio.gather(*tasks, return_exceptions=True)

        # Print results
        for (name, _), summary in zip(wallets, summaries, strict=False):
            print(f'\n📊 {name}')
            print(f'   Address: {summary.address[:20]}...')

            if isinstance(summary, WalletSummary):
                print(f'   ETH Balance: {summary.eth_balance:,.4f} ETH')
                print(f'   Token Types: {summary.token_count}')

                if summary.top_tokens:
                    print('   Top Tokens:')
                    for symbol, balance in summary.top_tokens:
                        print(f'     • {symbol}: {balance:,.2f}')
            else:
                print(f'   ⚠️ Error: {summary}')

        # Summary statistics
        print('\n' + '=' * 60)
        print('📈 Portfolio Summary')

        valid_summaries = [s for s in summaries if isinstance(s, WalletSummary)]
        if valid_summaries:
            total_eth = sum(s.eth_balance for s in valid_summaries)
            total_tokens = sum(s.token_count for s in valid_summaries)

            print(f'   Total ETH across {len(valid_summaries)} wallets: {total_eth:,.4f} ETH')
            print(f'   Total unique token types: {total_tokens}')

    finally:
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
