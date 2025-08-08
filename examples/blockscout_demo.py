#!/usr/bin/env python3
"""
BlockScout API Demo - FIXED VERSION

Demonstrates the BlockScout scanner integration with proper error handling
and testing on Ethereum mainnet with Vitalik Buterin's address.
BlockScout provides Etherscan-compatible API without requiring API keys.
"""

import asyncio

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method


async def test_blockscout_network(network_name: str, api_kind: str, test_address: str):
    """Test a specific BlockScout network."""

    print(f'\n📍 Testing {network_name}:')

    try:
        # Create client
        client = ChainscanClient(
            scanner_name='blockscout',
            scanner_version='v1',
            api_kind=api_kind,
            network=network_name.lower(),
            api_key='',  # BlockScout works without API key
        )

        print(f'   ✅ Client: {client}')

        # Get instance domain
        if hasattr(client._scanner, 'instance_domain'):
            print(f'   🔗 Instance: {client._scanner.instance_domain}')

        print(f'   🎯 Methods: {len(client.get_supported_methods())}')
        print(f'   📡 Testing ACCOUNT_BALANCE for {test_address[:12]}...')

        # Test account balance
        balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)

        # Proper error checking!
        if balance is None:
            print('   ❌ Error: Got None response (API might not support this network)')
            result = False
        elif isinstance(balance, dict) and 'error' in balance:
            print(f'   ❌ Error: {balance["error"]}')
            result = False
        elif isinstance(balance, str | int):
            balance_wei = int(balance)
            balance_eth = balance_wei / 10**18
            print(f'   ✅ Balance: {balance_eth:.6f} ETH ({balance_wei:,} wei)')
            result = True
        else:
            print(f'   ⚠️  Unexpected response: {type(balance)} = {balance}')
            result = False

        await client.close()
        return result

    except Exception as e:
        print(f'   ❌ Error: {e}')
        return False


async def test_blockscout_ethereum_mainnet():
    """Test BlockScout with Ethereum mainnet using Vitalik's address."""

    print("\n🔥 Testing Ethereum Mainnet with Vitalik Buterin's Address")
    print('=' * 60)

    # Vitalik Buterin's actual address
    vitalik_address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    print(f'👤 Address: {vitalik_address}')
    print('🔗 Network: Ethereum Mainnet')

    # Check if BlockScout supports Ethereum mainnet
    try:
        # Try to find Ethereum mainnet BlockScout instance
        from aiochainscan.scanners.blockscout_v1 import BlockScoutV1

        print('\n📋 Available BlockScout networks:')
        for network in sorted(BlockScoutV1.supported_networks):
            instance = BlockScoutV1.NETWORK_INSTANCES.get(network, 'Unknown')
            print(f'   • {network}: {instance}')

        # Test if 'eth' or 'main' network exists
        if 'eth' in BlockScoutV1.supported_networks:
            result = await test_blockscout_network('eth', 'blockscout_eth', vitalik_address)
        elif 'main' in BlockScoutV1.supported_networks:
            result = await test_blockscout_network('main', 'blockscout_main', vitalik_address)
        else:
            print("\n❌ BlockScout doesn't support Ethereum mainnet directly")
            print('🔍 Testing Sepolia testnet instead...')
            result = await test_blockscout_network(
                'sepolia', 'blockscout_sepolia', vitalik_address
            )

        return result

    except Exception as e:
        print(f'\n❌ Error testing Ethereum mainnet: {e}')
        return False


async def test_blockscout_comprehensive():
    """Comprehensive test of BlockScout functionality."""

    print('\n🧪 Comprehensive BlockScout Testing')
    print('=' * 60)

    # Vitalik's address for testing
    vitalik_address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    # Test different networks
    networks_to_test = [
        ('sepolia', 'blockscout_sepolia'),
        ('gnosis', 'blockscout_gnosis'),
        ('polygon', 'blockscout_polygon'),
    ]

    results = []

    for network, api_kind in networks_to_test:
        result = await test_blockscout_network(network, api_kind, vitalik_address)
        results.append((network, result))

    return results


async def test_blockscout_methods():
    """Test different BlockScout methods."""

    print('\n🔧 Testing BlockScout Methods')
    print('=' * 60)

    vitalik_address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    try:
        # Use Sepolia as most likely to work
        client = ChainscanClient(
            scanner_name='blockscout',
            scanner_version='v1',
            api_kind='blockscout_sepolia',
            network='sepolia',
            api_key='',
        )

        print(f'🧪 Testing on Sepolia with {vitalik_address[:12]}...')

        methods_to_test = [
            Method.ACCOUNT_BALANCE,
            Method.ACCOUNT_TRANSACTIONS,
            Method.ACCOUNT_INTERNAL_TXS,
            Method.ACCOUNT_ERC20_TRANSFERS,
        ]

        results = {}

        for method in methods_to_test:
            try:
                print(f'\n📡 Testing {method}...')

                if method == Method.ACCOUNT_BALANCE:
                    response = await client.call(method, address=vitalik_address)
                elif method in [
                    Method.ACCOUNT_TRANSACTIONS,
                    Method.ACCOUNT_INTERNAL_TXS,
                    Method.ACCOUNT_ERC20_TRANSFERS,
                ]:
                    response = await client.call(method, address=vitalik_address, page=1, offset=5)
                else:
                    response = await client.call(method, address=vitalik_address)

                if response is None:
                    print('   ❌ Got None response')
                    results[method] = False
                elif isinstance(response, dict) and 'error' in response:
                    print(f'   ❌ Error: {response["error"]}')
                    results[method] = False
                elif isinstance(response, list):
                    print(f'   ✅ Got list with {len(response)} items')
                    results[method] = True
                elif isinstance(response, str | int):
                    print(f'   ✅ Got value: {response}')
                    results[method] = True
                else:
                    print(f'   ⚠️  Unexpected: {type(response)}')
                    results[method] = False

            except Exception as e:
                print(f'   ❌ Exception: {e}')
                results[method] = False

        await client.close()

        # Summary
        successful = sum(results.values())
        total = len(results)
        print(f'\n📊 Method test results: {successful}/{total} successful')

        return results

    except Exception as e:
        print(f'❌ Error in method testing: {e}')
        return {}


async def main():
    """Main demonstration function."""

    print('🔗 BlockScout Scanner Demonstration - FIXED VERSION')
    print('=' * 60)

    print('🌐 BlockScout Features:')
    print('   • Etherscan-compatible API')
    print('   • No API key required')
    print('   • Multiple blockchain networks')
    print('   • Real-time data')
    print('   • Open source explorer')

    print('\n' + '=' * 60)
    print('📦 BlockScout Scanner Capabilities:')

    # Show scanner info
    try:
        client = ChainscanClient(
            scanner_name='blockscout',
            scanner_version='v1',
            api_kind='blockscout_sepolia',
            network='sepolia',
            api_key='',
        )

        scanner = client._scanner
        print(f'   📦 Scanner: {scanner.name} v{scanner.version}')
        print(f'   🌐 Networks: {", ".join(sorted(scanner.supported_networks))}')
        print(f'   🔐 Auth: {scanner.auth_mode} (API key optional)')
        print(f'   ⚙️  Methods: {len(scanner.SPECS)} inherited from EtherscanV1')

        await client.close()

    except Exception as e:
        print(f'❌ Error getting scanner info: {e}')

    # Run tests
    print('\n' + '=' * 60)

    # Test 1: Ethereum mainnet (or best available)
    mainnet_result = await test_blockscout_ethereum_mainnet()

    # Test 2: Comprehensive network testing
    network_results = await test_blockscout_comprehensive()

    # Test 3: Method testing
    method_results = await test_blockscout_methods()

    # Final summary
    print('\n' + '=' * 60)
    print('📊 FIXED BlockScout Demo Results:')

    print(f'\n🔥 Ethereum Test: {"✅ PASSED" if mainnet_result else "❌ FAILED"}')

    print('\n🌐 Network Tests:')
    successful_networks = sum(1 for _, result in network_results if result)
    total_networks = len(network_results)
    for network, result in network_results:
        status = '✅ PASSED' if result else '❌ FAILED'
        print(f'   {network}: {status}')
    print(f'   Total: {successful_networks}/{total_networks} networks working')

    print('\n🔧 Method Tests:')
    if method_results:
        successful_methods = sum(method_results.values())
        total_methods = len(method_results)
        print(f'   Total: {successful_methods}/{total_methods} methods working')

        for method, result in method_results.items():
            status = '✅ WORKS' if result else '❌ FAILS'
            method_name = str(method).replace('Method.', '')
            print(f'   {method_name}: {status}')

    # Overall assessment
    overall_success = (
        mainnet_result
        or successful_networks > 0
        or (method_results and sum(method_results.values()) > 0)
    )

    print(
        f'\n🎯 Overall BlockScout Status: {"✅ WORKING" if overall_success else "❌ NOT WORKING"}'
    )

    if not overall_success:
        print('\n💡 Possible issues:')
        print('   • BlockScout instances might be down')
        print('   • Network configuration issues')
        print('   • API rate limiting')
        print('   • Test address has no activity on tested networks')
    else:
        print('\n🎉 BlockScout integration is functional!')
        print('   Some networks/methods may not work due to:')
        print('   • Different BlockScout instance capabilities')
        print('   • Network-specific limitations')
        print('   • Temporary service issues')


if __name__ == '__main__':
    asyncio.run(main())
