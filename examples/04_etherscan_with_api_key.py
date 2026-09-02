#!/usr/bin/env python3
"""
04_etherscan_with_api_key.py - Using Etherscan with API Key

For production use and higher rate limits, use Etherscan with an API key.
This example shows proper configuration for Data Engineering pipelines.

Get your free API key at: https://etherscan.io/apis
"""

import asyncio
import os

from aiochainscan.core.client import ChainscanClient
from aiochainscan.domain.method import Method


async def main():
    """Example using Etherscan with API key for production workloads."""

    # Get API key from environment
    api_key = os.getenv('ETHERSCAN_KEY')

    if not api_key:
        print('⚠️  ETHERSCAN_KEY not set!')
        print('   Get your free API key at: https://etherscan.io/apis')
        print("   Then run: export ETHERSCAN_KEY='your_key_here'")
        print('\n   Falling back to BlockScout V2 (no key needed)...')

        # Fallback to BlockScout
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
        is_etherscan = False
    else:
        # Use Etherscan with API key
        print(f'✅ Using Etherscan API (key: {api_key[:8]}...)')
        client = ChainscanClient.from_config('etherscan', 'ethereum', api_key=api_key)
        is_etherscan = True

    address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    try:
        print(f'\n📊 Fetching data for {address[:16]}...\n')

        # 1. Account balance
        balance_raw = await client.call(Method.ACCOUNT_BALANCE, address=address)
        # Handle different response formats
        balance_eth = int(balance_raw) / 1e18 if isinstance(balance_raw, str) else balance_raw
        print(f'💰 Balance: {balance_eth:.4f} ETH')

        # 2. Normal transactions - different params for each API
        if is_etherscan:
            txs = await client.call(
                Method.ACCOUNT_TRANSACTIONS,
                address=address,
                startblock=0,
                endblock=99999999,
                page=1,
                offset=10,
                sort='desc',
            )
        else:
            # BlockScout V2 doesn't use Etherscan-style pagination
            txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address=address)
            txs = txs[:10]  # Limit manually

        if isinstance(txs, list):
            print(f'\n📝 Last {len(txs)} transactions:')
            for tx in txs[:5]:
                tx_hash = tx.get('hash', '')[:16]
                value_wei = int(tx.get('value', 0))
                value_eth = value_wei / 1e18
                print(f'   {tx_hash}... | {value_eth:.4f} ETH')

        # 3. Internal transactions (Etherscan specialty)
        if is_etherscan:
            internal_txs = await client.call(
                Method.ACCOUNT_INTERNAL_TRANSACTIONS,
                address=address,
                startblock=0,
                endblock=99999999,
                page=1,
                offset=5,
            )

            if isinstance(internal_txs, list) and internal_txs:
                print(f'\n🔄 Internal transactions ({len(internal_txs)}):')
                for tx in internal_txs[:3]:
                    from_addr = tx.get('from', '')[:12]
                    to_addr = tx.get('to', '')[:12]
                    value = int(tx.get('value', 0)) / 1e18
                    print(f'   {from_addr}... → {to_addr}... | {value:.4f} ETH')
        else:
            print('\n🔄 Internal transactions: (Use Etherscan API key for this feature)')

        # 4. Gas Oracle (real-time gas prices)
        if is_etherscan:
            try:
                gas = await client.call(Method.GAS_ORACLE)
                if isinstance(gas, dict):
                    print('\n⛽ Gas Prices (Gwei):')
                    print(f'   Safe Low: {gas.get("SafeGasPrice", "N/A")}')
                    print(f'   Standard: {gas.get("ProposeGasPrice", "N/A")}')
                    print(f'   Fast: {gas.get("FastGasPrice", "N/A")}')
            except Exception as e:
                print(f'\n⛽ Gas Oracle: {e}')
        else:
            print('\n⛽ Gas Oracle: (Use Etherscan API key for real-time gas prices)')

    finally:
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
