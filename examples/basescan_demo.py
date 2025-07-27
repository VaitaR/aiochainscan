#!/usr/bin/env python3
"""
BaseScan Demo - Demonstration of inherited scanner functionality.

Shows how BaseScanV1 inherits all functionality from EtherscanV1
while working with Base network endpoints.
"""

import asyncio
import os

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method


async def main():
    # Test address on Base network
    address = '0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97'

    print('🔗 BaseScan Scanner Demonstration')
    print('=' * 60)
    print(f'📍 Target Address: {address}')
    print('�� Network: Base mainnet')

    # Check API keys
    etherscan_key = os.getenv('ETHERSCAN_KEY')
    basescan_key = os.getenv('BASESCAN_KEY')

    print(f'🔑 ETHERSCAN_KEY: {"✅ Available" if etherscan_key else "❌ Missing"}')
    print(f'🔑 BASESCAN_KEY: {"✅ Available" if basescan_key else "❌ Missing"}')

    if not basescan_key:
        print('\n❌ BASESCAN_KEY required for BaseScan demo')
        print('💡 Get your API key at: https://basescan.org/apis')
        return

    results = []

    print('\n' + '=' * 60)
    print('�� Scanner Comparison:')

    # Method 1: Traditional Etherscan (for comparison)
    if etherscan_key:
        print('\n1️⃣ Etherscan (Ethereum mainnet - for comparison):')
        try:
            client_eth = ChainscanClient.from_config('etherscan', 'v1', 'eth', 'main')
            balance_eth = await client_eth.call(Method.ACCOUNT_BALANCE, address=address)
            print(f'   ✅ ETH Balance: {balance_eth} wei ({int(balance_eth) / 10**18:.6f} ETH)')
            results.append(('Etherscan (ETH)', balance_eth))
            await client_eth.close()
        except Exception as e:
            print(f'   ❌ Error: {e}')

    # Method 2: BaseScan (Base network)
    print('\n2️⃣ BaseScan (Base mainnet):')
    try:
        client_base = ChainscanClient.from_config('basescan', 'v1', 'base', 'main')
        balance_base = await client_base.call(Method.ACCOUNT_BALANCE, address=address)
        print(f'   ✅ BASE Balance: {balance_base} wei ({int(balance_base) / 10**18:.6f} ETH)')
        results.append(('BaseScan (BASE)', balance_base))
        await client_base.close()
    except Exception as e:
        print(f'   ❌ Error: {e}')

    # Show BaseScan capabilities
    print('\n' + '=' * 60)
    print('🔧 BaseScan Capabilities:')

    base_scanner = ChainscanClient.get_available_scanners()[('basescan', 'v1')]
    print(f'   📦 Scanner: {base_scanner.name} v{base_scanner.version}')
    print(f'   🌐 Networks: {", ".join(sorted(base_scanner.supported_networks))}')
    print(f'   🔐 Auth: {base_scanner.auth_mode} ({base_scanner.auth_field})')
    print(f'   ⚙️  Methods: {len(base_scanner.SPECS)} inherited from EtherscanV1')

    print('\n📋 Inherited Methods:')
    methods = list(base_scanner.SPECS.keys())
    for i, method in enumerate(methods, 1):
        method_name = str(method).replace('Method.', '')
        print(f'   {i:2d}. {method_name}')

    # Architecture demonstration
    print('\n' + '=' * 60)
    print('🏗️  Architecture Benefits Demonstrated:')

    print('\n✨ Code Reuse:')
    print('   • BaseScan inherits ALL 17 methods from EtherscanV1')
    print('   • Zero code duplication - just change name and networks')
    print('   • Automatic updates when EtherscanV1 gets new features')

    print('\n🔌 Easy Configuration:')
    print('   • Same ChainscanClient.from_config() pattern')
    print('   • Automatic BASESCAN_KEY detection from environment')
    print('   • Same Method enum works across all scanners')

    print('\n💡 Usage Examples:')
    print('   # Get balance')
    print("   balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')")
    print('   ')
    print('   # Get transactions')
    print("   txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address='0x...')")
    print('   ')
    print('   # Get contract ABI')
    print("   abi = await client.call(Method.CONTRACT_ABI, address='0x...')")

    # Show class hierarchy
    print('\n🧬 Class Hierarchy:')
    print('   Scanner (ABC)')
    print('   └── EtherscanV1')
    print('       └── BaseScanV1  ← Inherits all SPECS and functionality')

    if len(results) >= 2:
        print('\n📈 Network Comparison:')
        for network, balance in results:
            try:
                eth_balance = int(balance) / 10**18
                print(f'   {network}: {balance} wei ({eth_balance:.6f} ETH)')
            except (ValueError, TypeError):
                print(f'   {network}: {balance}')


if __name__ == '__main__':
    asyncio.run(main())
