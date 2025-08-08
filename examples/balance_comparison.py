#!/usr/bin/env python3
"""
Simple comparison of getting Ether balance through different API methods.

This example shows how to get the same balance using:
1. Legacy Client (etherscan v1 style)
2. New ChainscanClient with etherscan v1
3. OKLink API (when available)

All three should return the same balance for the same address.
"""

import asyncio
import os

from aiochainscan import Client, get_balance
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

# Test address with some ETH balance
TEST_ADDRESS = '0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97'


async def main():
    print('🔍 Balance Comparison for Address:', TEST_ADDRESS)
    print('=' * 60)

    # Check if we have required API keys
    etherscan_key = os.getenv('ETHERSCAN_KEY')
    oklink_key = os.getenv('OKLINK_KEY')

    if not etherscan_key:
        print('❌ ETHERSCAN_KEY not found in environment variables')
        return

    print('✅ ETHERSCAN_KEY found')
    if oklink_key:
        print('✅ OKLINK_KEY found')
    else:
        print('⚠️  OKLINK_KEY not found - OKLink test will be skipped')

    print('\n' + '=' * 60)

    # Method 1: Legacy Client (etherscan v1 style)
    print('\n1️⃣ Legacy Client (etherscan v1 style):')
    try:
        client_v1 = Client.from_config('eth', 'main')
        balance_v1 = await client_v1.account.balance(TEST_ADDRESS)
        print(f'   Balance: {balance_v1} wei')
        print(f'   Balance: {int(balance_v1) / 10**18:.6f} ETH')
        await client_v1.close()
    except Exception as e:
        print(f'   ❌ Error: {e}')

    # Method 2: Facade (preferred)
    print('\n2️⃣ Facade (preferred):')
    try:
        balance_v2 = await get_balance(
            address=TEST_ADDRESS, api_kind='eth', network='main', api_key=etherscan_key
        )
        print(f'   Balance: {balance_v2} wei')
        print(f'   Balance: {int(balance_v2) / 10**18:.6f} ETH')
    except Exception as e:
        print(f'   ❌ Error: {e}')

    # Method 3: OKLink API for Ethereum
    print('\n3️⃣ OKLink API for Ethereum:')
    if oklink_key:
        try:
            # Create UrlBuilder and ChainscanClient for OKLink
            from aiochainscan.url_builder import UrlBuilder

            oklink_url_builder = UrlBuilder(oklink_key, 'oklink_eth', 'main')
            client_oklink = ChainscanClient(
                scanner_name='oklink_eth',
                scanner_version='v1',
                api_kind='oklink_eth',
                network='main',
                api_key=oklink_key,
            )

            balance_oklink = await client_oklink.call(Method.ACCOUNT_BALANCE, address=TEST_ADDRESS)
            print(f'   Balance: {balance_oklink} wei')

            # Convert to ETH if it's a numeric string
            try:
                balance_eth = float(balance_oklink) / 10**18
                print(f'   Balance: {balance_eth:.6f} ETH')
            except (ValueError, TypeError):
                print(f'   Balance (raw): {balance_oklink}')

            await client_oklink.close()
        except Exception as e:
            print(f'   ❌ Error: {e}')
    else:
        print('   ❌ OKLINK_KEY not available')

    # Comparison
    print('\n' + '=' * 60)
    print('📊 Results Comparison:')

    try:
        results = []
        if 'balance_v1' in locals():
            results.append(('Legacy Client', balance_v1))
        if 'balance_v2' in locals():
            results.append(('ChainscanClient', balance_v2))
        if 'balance_oklink' in locals():
            results.append(('OKLink', balance_oklink))

        if len(results) >= 2:
            # Compare results
            if len({result[1] for result in results}) == 1:
                print('✅ All methods return identical results!')
                print(f'   All methods: {results[0][1]} wei')
            else:
                print('⚠️  Results differ:')
                for method, balance in results:
                    print(f'   {method}: {balance} wei')
        else:
            print('⚠️  Cannot compare - insufficient successful methods')
    except Exception as e:
        print(f'❌ Comparison error: {e}')

    print('\n💡 This example demonstrates:')
    print('   • Legacy Client vs new ChainscanClient')
    print('   • Different scanner implementations (Etherscan vs OKLink)')
    print('   • Unified Method enum usage across different APIs')


if __name__ == '__main__':
    asyncio.run(main())
