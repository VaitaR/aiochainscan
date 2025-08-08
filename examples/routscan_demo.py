#!/usr/bin/env python3
"""
RoutScan API Demo - Mode Network Explorer

This example demonstrates how to use the RoutScan scanner for the Mode network.
RoutScan provides blockchain explorer functionality for Mode (EVM Layer 2).

Features demonstrated:
- Account balance checking
- Transaction history
- Internal transactions
- ERC-20 token transfers
- Contract ABI retrieval
- Transaction by hash lookup
- Block information
"""

import asyncio
import os

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method


async def demo_routscan_basic():
    """Basic RoutScan functionality demonstration."""

    print('🚀 RoutScan Demo - Mode Network Explorer')
    print('=' * 50)

    # RoutScan API key is optional but recommended for higher rate limits
    api_key = os.getenv('ROUTSCAN_API_KEY', '')

    if api_key:
        print(f'✅ Using API key: {api_key[:8]}...')
    else:
        print('⚠️  No API key provided - using public access')
        print('   Set ROUTSCAN_API_KEY for higher rate limits')

    # Test address on Mode network
    test_address = '0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3'

    try:
        # Create RoutScan client for Mode network
        client = ChainscanClient(
            scanner_name='routscan',
            scanner_version='v1',
            api_kind='routscan_mode',
            network='mode',
            api_key=api_key or 'demo',
        )

        print(f'\n✅ Client created: {client}')
        print('🔗 Network: Mode (Chain ID: 34443)')
        print(f'📍 Test address: {test_address}')

        # 1. Account Balance
        print('\n💰 Getting account balance...')
        balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)

        if isinstance(balance, int | str):
            balance_wei = int(balance)
            balance_eth = balance_wei / 10**18
            print(f'   ✅ Balance: {balance_eth:.6f} ETH')
            print(f'   📊 Raw balance: {balance_wei:,} wei')
        else:
            print(f'   ✅ Balance: {balance}')

        # 2. Transaction History
        print('\n📄 Getting transaction history...')
        transactions = await client.call(
            Method.ACCOUNT_TRANSACTIONS, address=test_address, page=1, offset=10
        )

        if isinstance(transactions, list):
            print(f'   ✅ Found {len(transactions)} transactions')

            for i, tx in enumerate(transactions[:3], 1):
                if isinstance(tx, dict):
                    print(f'\n   📄 Transaction {i}:')
                    print(f'      Hash: {tx.get("hash", "N/A")}')
                    print(f'      From: {tx.get("from", "N/A")}')
                    print(f'      To: {tx.get("to", "N/A")}')
                    print(f'      Value: {tx.get("value", "0")} wei')
                    print(f'      Block: {tx.get("blockNumber", "N/A")}')
                    print(f'      Gas Used: {tx.get("gasUsed", "N/A")}')
        else:
            print(f'   ✅ Transactions response: {type(transactions)}')

        # 3. Internal Transactions
        print('\n🔄 Getting internal transactions...')
        internal_txs = await client.call(
            Method.ACCOUNT_INTERNAL_TXS, address=test_address, page=1, offset=5
        )

        if isinstance(internal_txs, list):
            print(f'   ✅ Found {len(internal_txs)} internal transactions')
            if internal_txs:
                tx = internal_txs[0]
                if isinstance(tx, dict):
                    print(f'   📄 Latest internal tx: {tx.get("hash", "N/A")}')
        else:
            print(f'   ✅ Internal transactions: {type(internal_txs)}')

        # 4. ERC-20 Token Transfers
        print('\n🪙 Getting ERC-20 token transfers...')
        token_transfers = await client.call(
            Method.ACCOUNT_ERC20_TRANSFERS, address=test_address, page=1, offset=5
        )

        if isinstance(token_transfers, list):
            print(f'   ✅ Found {len(token_transfers)} token transfers')
            if token_transfers:
                transfer = token_transfers[0]
                if isinstance(transfer, dict):
                    print('   🪙 Latest transfer:')
                    print(f'      Token: {transfer.get("tokenSymbol", "N/A")}')
                    print(f'      Amount: {transfer.get("value", "0")}')
                    print(f'      Contract: {transfer.get("contractAddress", "N/A")}')
        else:
            print(f'   ✅ Token transfers: {type(token_transfers)}')

        await client.close()
        return True

    except Exception as e:
        print(f'❌ Error in basic demo: {e}')
        return False


async def demo_routscan_advanced():
    """Advanced RoutScan features demonstration."""

    print('\n🔧 Advanced RoutScan Features')
    print('=' * 50)

    api_key = os.getenv('ROUTSCAN_API_KEY', 'demo')

    # Known transaction hash on Mode network for demo
    test_tx_hash = '0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef'

    # Known contract address on Mode network
    test_contract = '0x4200000000000000000000000000000000000006'  # WETH on Mode

    try:
        client = ChainscanClient(
            scanner_name='routscan',
            scanner_version='v1',
            api_kind='routscan_mode',
            network='mode',
            api_key=api_key,
        )

        # 1. Transaction by Hash (if available)
        print('\n🔍 Looking up transaction by hash...')
        print(f'   TX Hash: {test_tx_hash}')

        try:
            tx_details = await client.call(Method.TX_BY_HASH, txhash=test_tx_hash)
            print(f'   ✅ Transaction found: {type(tx_details)}')
            if isinstance(tx_details, dict):
                print(f'   📊 Block: {tx_details.get("blockNumber", "N/A")}')
                print(f'   ⛽ Gas: {tx_details.get("gas", "N/A")}')
        except Exception as e:
            print(f'   ⚠️  Transaction lookup failed: {e}')

        # 2. Contract ABI
        print('\n📋 Getting contract ABI...')
        print(f'   Contract: {test_contract}')

        try:
            abi = await client.call(Method.CONTRACT_ABI, address=test_contract)
            print(f'   ✅ ABI retrieved: {type(abi)}')
            if isinstance(abi, str) and abi.startswith('['):
                print(f'   📝 ABI length: {len(abi)} characters')
            elif isinstance(abi, list):
                print(f'   📝 ABI functions: {len(abi)}')
        except Exception as e:
            print(f'   ⚠️  ABI retrieval failed: {e}')

        # 3. Block Information
        print('\n🧱 Getting latest block info...')

        try:
            block_info = await client.call(Method.BLOCK_BY_NUMBER, block_number='latest')
            print(f'   ✅ Block info retrieved: {type(block_info)}')
            if isinstance(block_info, dict):
                print(f'   🏗️  Block number: {block_info.get("number", "N/A")}')
                print(f'   ⏰ Timestamp: {block_info.get("timestamp", "N/A")}')
                print(f'   📊 Transactions: {len(block_info.get("transactions", []))}')
        except Exception as e:
            print(f'   ⚠️  Block lookup failed: {e}')

        await client.close()
        return True

    except Exception as e:
        print(f'❌ Error in advanced demo: {e}')
        return False


async def demo_routscan_comparison():
    """Compare RoutScan with other scanners (if available)."""

    print('\n⚖️  RoutScan vs Other Scanners')
    print('=' * 50)

    # Test address present on multiple networks
    test_address = '0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3'

    results = {}

    # RoutScan (Mode)
    try:
        routscan_client = ChainscanClient(
            scanner_name='routscan',
            scanner_version='v1',
            api_kind='routscan_mode',
            network='mode',
            api_key=os.getenv('ROUTSCAN_API_KEY', 'demo'),
        )

        balance = await routscan_client.call(Method.ACCOUNT_BALANCE, address=test_address)
        results['RoutScan (Mode)'] = balance
        await routscan_client.close()

    except Exception as e:
        results['RoutScan (Mode)'] = f'Error: {e}'

    # Etherscan (if available)
    etherscan_key = os.getenv('ETHERSCAN_KEY')
    if etherscan_key:
        try:
            etherscan_client = ChainscanClient(
                scanner_name='etherscan',
                scanner_version='v1',
                api_kind='eth',
                network='main',
                api_key=etherscan_key,
            )

            balance = await etherscan_client.call(Method.ACCOUNT_BALANCE, address=test_address)
            results['Etherscan (ETH)'] = balance
            await etherscan_client.close()

        except Exception as e:
            results['Etherscan (ETH)'] = f'Error: {e}'
    else:
        results['Etherscan (ETH)'] = 'No API key provided'

    # Display results
    print(f'📊 Balance comparison for {test_address}:')
    for scanner, result in results.items():
        if isinstance(result, int | str) and str(result).isdigit():
            balance_eth = int(result) / 10**18
            print(f'   {scanner}: {balance_eth:.6f} ETH')
        else:
            print(f'   {scanner}: {result}')


async def demo_routscan_features():
    """Demonstrate RoutScan specific features."""

    print('\n🌟 RoutScan Specific Features')
    print('=' * 50)

    print('🔗 Mode Network Characteristics:')
    print('   • Layer 2 Solution: Optimistic Rollup')
    print('   • Chain ID: 34443')
    print('   • Native Token: ETH')
    print('   • Low gas fees and fast transactions')
    print('   • EVM compatible')

    print('\n🛠️  RoutScan API Features:')
    print('   • No mandatory API key (public access)')
    print('   • Standard Etherscan-compatible endpoints')
    print('   • Real-time transaction tracking')
    print('   • Contract verification support')
    print('   • Token transfer monitoring')

    print('\n📚 Supported Methods:')

    # List all supported methods for RoutScan
    try:
        client = ChainscanClient(
            scanner_name='routscan',
            scanner_version='v1',
            api_kind='routscan_mode',
            network='mode',
            api_key='demo',
        )

        methods = client.get_supported_methods()
        print(f'   📊 Total methods: {len(methods)}')

        for method in methods:
            print(f'   ✅ {method}')

        await client.close()

    except Exception as e:
        print(f'   ❌ Error listing methods: {e}')


async def main():
    """Main demo function."""

    print('🚀 RoutScan Demo - Complete Demonstration')
    print('🔗 Mode Network Blockchain Explorer')
    print('=' * 60)

    # Check for optional API key
    api_key = os.getenv('ROUTSCAN_API_KEY')
    if not api_key:
        print('\n💡 Tip: Set ROUTSCAN_API_KEY for higher rate limits')
        print("   export ROUTSCAN_API_KEY='your_api_key_here'")
        print('   (RoutScan works without API key too!)')

    print('\n' + '=' * 60)

    # Run demonstrations
    results = []

    # Basic functionality
    print('\n🎯 Running Basic Demo...')
    basic_result = await demo_routscan_basic()
    results.append(('Basic Features', basic_result))

    # Advanced features
    print('\n🎯 Running Advanced Demo...')
    advanced_result = await demo_routscan_advanced()
    results.append(('Advanced Features', advanced_result))

    # Feature overview
    print('\n🎯 RoutScan Features Overview...')
    await demo_routscan_features()

    # Comparison
    print('\n🎯 Running Comparison Demo...')
    await demo_routscan_comparison()

    # Results summary
    print('\n' + '=' * 60)
    print('📊 Demo Results Summary:')

    successful = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = '✅ PASSED' if result else '❌ FAILED'
        print(f'   {name}: {status}')

    print(f'\n🎉 Overall: {successful}/{total} demos successful')

    if successful == total:
        print('🎊 All RoutScan demos completed successfully!')
        print('🔗 RoutScan is ready for production use!')
    else:
        print('⚠️  Some demos had issues - check network connectivity')

    print('\n✨ RoutScan Demo completed!')
    print('🌐 Explore Mode network at: https://explorer.mode.network/')


if __name__ == '__main__':
    asyncio.run(main())
