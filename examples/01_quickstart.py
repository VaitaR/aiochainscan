#!/usr/bin/env python3
"""Quickstart: balance, transactions and token holdings for one address.

Self-contained — needs nothing but the published package:

    pip install aiochainscan
    python 01_quickstart.py [address]

Blockscout serves this without an API key. Public instances are shared
infrastructure and may rate-limit or refuse a burst; for unattended work use
Etherscan (ETHERSCAN_KEY) or a self-hosted instance.
"""

from __future__ import annotations

import asyncio
import sys

from aiochainscan import ChainscanClient, to_decimal_amount, wei_to_ether

VITALIK = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'


async def main(address: str) -> None:
    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        balance = await client.get_balance(address)
        transactions = await client.get_transactions_normalized(address)
        tokens = await client.get_token_portfolio(address)

    # Wei arrives as a base-unit string. wei_to_ether is exact Decimal math:
    # int(wei) / 1e18 starts losing digits at ~9.2 ETH.
    print(f'Address: {address}')
    print(f'Balance: {wei_to_ether(balance):.6f} ETH')

    print(f'\nMost recent transactions ({len(transactions)} in this page):')
    for tx in transactions[:5]:
        when = tx.timestamp.date().isoformat() if tx.timestamp else 'unknown date'
        print(
            f'  {tx.hash[:18] if tx.hash else "?":<20} {wei_to_ether(tx.value_wei):>14.6f} ETH  {when}'
        )

    print(f'\nToken holdings ({len(tokens)}):')
    for item in tokens[:5]:
        token = item.get('token', {})
        symbol = token.get('symbol') or '???'
        decimals = int(token.get('decimals') or 18)
        amount = to_decimal_amount(item.get('value', '0'), decimals=decimals)
        print(f'  {symbol:<12} {amount:>24,.4f}')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else VITALIK))
