#!/usr/bin/env python3
"""
Unified Scanner Architecture Demonstration.

Shows how to get the same Ethereum balance using different scanner implementations:
1. Legacy Client (existing API)
2. ChainscanClient with Etherscan v1
3. ChainscanClient with Etherscan v2 (multichain)
4. ChainscanClient with OKLink (if available)

All should return identical results for the same address.
"""

import asyncio
import os

from aiochainscan import Client
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method


async def main():
    # Test address with ETH balance
    address = '0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97'

    print(f'🔍 Getting balance for: {address}')
    print('=' * 60)

    # Check API keys
    etherscan_key = os.getenv('ETHERSCAN_KEY')

    if not etherscan_key:
        print('❌ ETHERSCAN_KEY not found')
        return

    results = []

    # Method 1: Legacy Client
    print('\n1️⃣ Legacy Client (traditional approach):')
    try:
        client_legacy = Client.from_config('eth', 'main')
        balance1 = await client_legacy.account.balance(address)
        print(f'   {balance1} wei')
        print(f'   {int(balance1) / 10**18:.6f} ETH')
        results.append(('Legacy Client', balance1))
        await client_legacy.close()
    except Exception as e:
        print(f'   ❌ Error: {e}')

    # Method 2: ChainscanClient with Etherscan v1
    print('\n2️⃣ ChainscanClient + Etherscan v1:')
    try:
        client_v1 = ChainscanClient.from_config('etherscan', 'v1', 'eth', 'main')
        balance2 = await client_v1.call(Method.ACCOUNT_BALANCE, address=address)
        print(f'   {balance2} wei')
        print(f'   {int(balance2) / 10**18:.6f} ETH')
        results.append(('Etherscan v1', balance2))
        await client_v1.close()
    except Exception as e:
        print(f'   ❌ Error: {e}')

    # Method 3: ChainscanClient with Etherscan v2 (multichain)
    print('\n3️⃣ ChainscanClient + Etherscan v2 (multichain):')
    try:
        client_v2 = ChainscanClient.from_config('etherscan', 'v2', 'eth', 'main')
        balance3 = await client_v2.call(Method.ACCOUNT_BALANCE, address=address)
        print(f'   {balance3} wei')
        print(f'   {int(balance3) / 10**18:.6f} ETH')
        results.append(('Etherscan v2', balance3))
        await client_v2.close()
    except Exception as e:
        print(f'   ❌ Error: {e}')

    # Compare results
    print('\n' + '=' * 60)
    print('📊 Results Comparison:')

    if len(results) >= 2:
        # Check if all results are identical
        unique_balances = {result[1] for result in results}
        if len(unique_balances) == 1:
            print('✅ All methods return identical results!')
            print(f'   Balance: {results[0][1]} wei')
            print(f'   Balance: {int(results[0][1]) / 10**18:.6f} ETH')
        else:
            print('⚠️  Results differ:')
            for method, balance in results:
                print(f'   {method}: {balance} wei')
    else:
        print('⚠️  Insufficient successful calls for comparison')

    # Show architecture benefits
    print('\n' + '=' * 60)
    print('🎯 Architecture Comparison:')
    print('\n📍 Legacy approach (per-module):')
    print("   client = Client.from_config('eth', 'main')")
    print('   balance = await client.account.balance(address)')

    print('\n🆕 Unified approach (cross-scanner):')
    print("   client = ChainscanClient.from_config('etherscan', 'v1', 'eth', 'main')")
    print('   balance = await client.call(Method.ACCOUNT_BALANCE, address=address)')

    print('\n✨ Key benefits:')
    print('   • Same interface works across different scanner APIs')
    print('   • Type-safe Method enum (IDE autocomplete)')
    print('   • Automatic parameter mapping for different APIs')
    print('   • Easy to switch between scanners and versions')
    print('   • Future-proof for new scanner implementations')


if __name__ == '__main__':
    asyncio.run(main())
