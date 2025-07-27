#!/usr/bin/env python3
"""
Test Moralis Web3 Data API integration.

This test demonstrates the integration of Moralis API into the aiochainscan
unified architecture. Run with a valid Moralis API key.
"""

import asyncio
import os

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method


async def test_moralis_scanner():
    """Test basic Moralis scanner functionality."""

    print('🧪 Testing Moralis Scanner Integration\n')

    # Check for API key
    api_key = os.getenv('MORALIS_KEY')
    if not api_key:
        print('❌ MORALIS_API_KEY environment variable not set')
        print("   Set it with: export MORALIS_API_KEY='your_api_key_here'")
        return

    # Test 1: Scanner Registration
    print('1️⃣ Testing Scanner Registration...')
    try:
        client = ChainscanClient(
            scanner_name='moralis',
            scanner_version='v1',
            api_kind='moralis',  # This will need to be added to UrlBuilder
            network='eth',
            api_key=api_key,
        )
        print(f'   ✅ Successfully created client: {client}')
        print(f'   📊 Supported methods: {len(client.get_supported_methods())}')

    except Exception as e:
        print(f'   ❌ Failed to create client: {e}')
        return

    # Test 2: Account Balance
    print('\n2️⃣ Testing Account Balance...')
    test_address = '0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97'  # Known address with balance

    try:
        balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)
        print(f'   ✅ Balance: {balance} wei')
        print(f'   💰 Balance: {int(balance) / 10**18:.6f} ETH')

    except Exception as e:
        print(f'   ⚠️  Balance call failed: {e}')

    # Test 3: Account Transactions
    print('\n3️⃣ Testing Account Transactions...')

    try:
        txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address=test_address)
        print(f'   ✅ Received {len(txs) if isinstance(txs, list) else "N/A"} transactions')
        if isinstance(txs, list) and txs:
            print(f'   📄 First tx hash: {txs[0].get("hash", "N/A")}')

    except Exception as e:
        print(f'   ⚠️  Transactions call failed: {e}')

    # Test 4: Token Balance
    print('\n4️⃣ Testing Token Balance...')

    try:
        tokens = await client.call(Method.TOKEN_BALANCE, address=test_address)
        print('   ✅ Token query successful')
        if isinstance(tokens, list):
            print(f'   🪙 Found {len(tokens)} tokens')

    except Exception as e:
        print(f'   ⚠️  Token balance call failed: {e}')

    # Test 5: Transaction by Hash
    print('\n5️⃣ Testing Transaction by Hash...')
    test_tx = '0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3'  # Replace with real tx hash

    try:
        tx = await client.call(Method.TX_BY_HASH, txhash=test_tx)
        print(f'   ✅ Transaction query successful: {tx.get("hash", "N/A")}')

    except Exception as e:
        print(f'   ⚠️  Transaction call failed: {e}')

    await client.close()
    print('\n✨ Moralis integration test completed!')


async def test_multi_chain_support():
    """Test multi-chain functionality."""

    print('\n🌐 Testing Multi-Chain Support\n')

    api_key = os.getenv('MORALIS_KEY')
    if not api_key:
        print('❌ MORALIS_API_KEY not set')
        return

    # Test different chains
    chains = ['eth', 'bsc', 'polygon', 'arbitrum', 'base']
    test_address = '0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3'

    for chain in chains:
        print(f'🔗 Testing {chain.upper()}...')

        try:
            client = ChainscanClient(
                scanner_name='moralis',
                scanner_version='v1',
                api_kind='moralis',
                network=chain,
                api_key=api_key,
            )

            balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)
            print(f'   ✅ {chain}: Balance = {balance} wei')

            await client.close()

        except Exception as e:
            print(f'   ❌ {chain}: {e}')


async def main():
    """Run all tests."""
    await test_moralis_scanner()
    await test_multi_chain_support()


if __name__ == '__main__':
    asyncio.run(main())
