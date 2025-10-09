#!/usr/bin/env python3
"""
Comprehensive Multi-Scanner Architecture Demo.

Demonstrates the unified scanner architecture with different implementations:
1. Legacy Client (Etherscan via existing config)
2. Etherscan v2 (multichain via unified client)
3. BaseScan (Base network via unified client)
4. Available scanner overview

Shows how the same logical operation works across different APIs.
"""

import asyncio
import os

from aiochainscan import Client
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method


async def main():
    # Test address with ETH balance
    address = '0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97'

    print('🚀 Multi-Scanner Architecture Demonstration')
    print('=' * 70)
    print(f'📍 Target Address: {address}')

    # Check API keys
    etherscan_key = os.getenv('ETHERSCAN_KEY')
    basescan_key = os.getenv('BASESCAN_KEY')
    print(f'🔑 ETHERSCAN_KEY: {"✅ Available" if etherscan_key else "❌ Missing"}')
    print(f'🔑 BASESCAN_KEY: {"✅ Available" if basescan_key else "❌ Missing"}')
    if not etherscan_key:
        print('\n❌ ETHERSCAN_KEY required for demo')
        return

    results = []

    print('\n' + '=' * 70)
    print('📊 Balance Retrieval Methods:')

    # Method 1: Legacy Client (Etherscan via config)
    print('\n1️⃣ Legacy Client (traditional per-module approach):')
    print('   Code: client.account.balance(address)')
    try:
        client_legacy = Client.from_config('eth', 'main')
        balance1 = await client_legacy.account.balance(address)
        print(f'   ✅ Result: {balance1} wei ({int(balance1) / 10**18:.6f} ETH)')
        results.append(('Legacy Client', balance1))
        await client_legacy.close()
    except Exception as e:
        print(f'   ❌ Error: {e}')

    # Method 2: ChainscanClient + Etherscan v2 (multichain)
    print('\n2️⃣ ChainscanClient + Etherscan v2 (multichain support):')
    print('   Code: client.call(Method.ACCOUNT_BALANCE, address=address)')
    try:
        client_v2 = ChainscanClient.from_config('etherscan', 'ethereum')  # v2 default
        balance3 = await client_v2.call(Method.ACCOUNT_BALANCE, address=address)
        print(f'   ✅ Result: {balance3} wei ({int(balance3) / 10**18:.6f} ETH)')
        results.append(('Etherscan v2', balance3))
        await client_v2.close()
    except Exception as e:
        print(f'   ❌ Error: {e}')

    # Method 3: ChainscanClient + BaseScan v1 (Base network)
    if basescan_key:
        print('\n3️⃣ ChainscanClient + BaseScan v1 (Base network):')
        print('   Code: client.call(Method.ACCOUNT_BALANCE, address=address)')
        try:
            client_base = ChainscanClient.from_config('etherscan', 'base')  # v2 default
            balance_base = await client_base.call(Method.ACCOUNT_BALANCE, address=address)
            print(f'   ✅ Result: {balance_base} wei ({int(balance_base) / 10**18:.6f} ETH)')
            results.append(('BaseScan v1', balance_base))
            await client_base.close()
        except Exception as e:
            print(f'   ❌ Error: {e}')
    else:
        print('\n3️⃣ ChainscanClient + BaseScan v1 skipped (BASESCAN_KEY missing)')

    # Show available scanners
    print('\n' + '=' * 70)
    print('🔧 Available Scanner Implementations:')

    available_scanners = ChainscanClient.get_available_scanners()
    for (name, version), scanner_class in available_scanners.items():
        networks = ', '.join(sorted(scanner_class.supported_networks))
        auth_info = f'{scanner_class.auth_mode} ({scanner_class.auth_field})'
        method_count = len(scanner_class.SPECS)
        print(
            f'   📦 {name} {version}: {method_count} methods, networks: {networks}, auth: {auth_info}'
        )

    # Compare results
    print('\n' + '=' * 70)
    print('📈 Results Analysis:')

    if len(results) >= 2:
        etherscan_results = [r for r in results if 'Etherscan' in r[0] or 'Legacy' in r[0]]
        if len(etherscan_results) >= 2:
            etherscan_balances = {r[1] for r in etherscan_results}
            if len(etherscan_balances) == 1:
                print('✅ Legacy client and Etherscan v2 return identical results!')
                print(f'   Consensus balance: {etherscan_results[0][1]} wei')
                print(f'   Consensus balance: {int(etherscan_results[0][1]) / 10**18:.6f} ETH')
            else:
                print('⚠️  Etherscan results differ (unexpected):')
                for method, balance in etherscan_results:
                    print(f'     {method}: {balance} wei')

        print(f'\n📊 Summary: {len(results)} successful calls')
        for method, balance in results:
            if (
                isinstance(balance, str)
                and balance.isdigit()
                or isinstance(balance, int | str)
                and str(balance).isdigit()
            ):
                balance_eth = int(balance) / 10**18
                print(f'   {method}: {balance} wei ({balance_eth:.6f} ETH)')
            else:
                print(f'   {method}: {balance} (raw)')

    # Architecture benefits
    print('\n' + '=' * 70)
    print('🎯 Architecture Benefits Demonstrated:')
    print('\n✨ Unified Interface:')
    print('   • Same Method.ACCOUNT_BALANCE works across all scanners')
    print('   • Same client.call() pattern regardless of implementation')
    print('   • Type-safe operations with IDE autocomplete')

    print('\n🔌 Scanner Flexibility:')
    print('   • Easy to switch between Etherscan v2 and BaseScan/BlockScout')
    print('   • Support for different authentication methods (query vs header)')
    print('   • Automatic parameter mapping (address vs wallet, etc.)')

    print('\n🚀 Future-Proof Design:')
    print('   • Add new scanners with ~30 lines of code')
    print('   • Backward compatibility with legacy Client')
    print('   • Extensible for new blockchain networks')

    print('\n💡 Next Steps:')
    print('   • Try with other networks: client.call(Method.ACCOUNT_BALANCE, address=addr)')
    print('   • Test other methods: Method.ACCOUNT_TRANSACTIONS, Method.TX_BY_HASH')
    print('   • Add custom scanners using @register_scanner decorator')


if __name__ == '__main__':
    asyncio.run(main())
