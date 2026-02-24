#!/usr/bin/env python3
"""
smart_contract_demo.py - High-level SmartContract API

Demonstrates the new SmartContract abstraction that automatically:
- Fetches contract ABI
- Resolves Proxy contracts
- Decodes events and transactions

Perfect for analyzing smart contracts without manual ABI management!
"""

import asyncio

from aiochainscan.core.client import ChainscanClient


async def demo_usdt_proxy_contract():
    """
    Example 1: USDT - A Proxy Contract

    USDT uses a proxy pattern. The SmartContract API automatically
    detects this and fetches the implementation contract's ABI.
    """
    print('=' * 80)
    print('Example 1: USDT Contract (Proxy Pattern)')
    print('=' * 80)

    # USDT contract address on Ethereum
    usdt_address = '0xdac17f958d2ee523a2206206994597c13d831ec7'

    # Create client (using Etherscan for better rate limits with API key)
    client = ChainscanClient.from_config('etherscan', 'ethereum')

    try:
        # Get contract - automatically fetches ABI and resolves proxy
        print(f'\n🔍 Loading contract {usdt_address}...')
        usdt = await client.get_contract(usdt_address)

        print('✅ Contract loaded!')
        print(f'   Address: {usdt.address}')
        print(f'   Is Proxy: {usdt.is_proxy}')
        if usdt.is_proxy:
            print(f'   Implementation: {usdt.implementation_address}')

        # Check available events and functions
        print('\n📋 Available Events:')
        for event_name in list(usdt._event_map.keys())[:5]:
            print(f'   - {event_name}')

        print('\n📋 Available Functions:')
        for func_name in list(usdt._function_map.keys())[:5]:
            print(f'   - {func_name}')

        # Iterate through Transfer events
        print('\n💸 Recent Transfer Events (last 5):')
        count = 0
        async for event in usdt.iter_events('Transfer', limit=5):
            count += 1
            from_addr = event.args.get('from', '???')[:10]
            to_addr = event.args.get('to', '???')[:10]
            value = event.args.get('value', 0)

            # USDT has 6 decimals
            value_usdt = value / 1e6 if isinstance(value, int) else 0

            print(
                f'   {count}. Block {event.block_number}: {from_addr}... → {to_addr}... | ${value_usdt:,.2f}'
            )
            print(f'      Tx: {event.tx_hash[:20]}...')

        print(f'\n✅ Processed {count} Transfer events')

    finally:
        await client.close()


async def demo_uniswap_v2_router():
    """
    Example 2: Uniswap V2 Router - Regular Contract

    Demonstrates transaction iteration and function call decoding.
    """
    print('\n' + '=' * 80)
    print('Example 2: Uniswap V2 Router (Regular Contract)')
    print('=' * 80)

    # Uniswap V2 Router address
    router_address = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'

    client = ChainscanClient.from_config('etherscan', 'ethereum')

    try:
        # Get contract
        print(f'\n🔍 Loading contract {router_address}...')
        router = await client.get_contract(router_address)

        print('✅ Contract loaded!')
        print(f'   Address: {router.address}')
        print(f'   Is Proxy: {router.is_proxy}')

        # Show some available functions
        print('\n📋 Sample Functions:')
        for func_name in list(router._function_map.keys())[:8]:
            print(f'   - {func_name}')

        # Iterate through recent transactions
        print('\n📝 Recent Transactions (last 5):')
        count = 0
        async for tx in router.iter_transactions(limit=5):
            count += 1
            from_addr = tx.from_address[:10]
            value_eth = tx.value_wei / 1e18

            print(f'   {count}. {tx.function_name}()')
            print(f'      From: {from_addr}... | Value: {value_eth:.4f} ETH')
            print(f'      Block: {tx.block_number} | Tx: {tx.tx_hash[:20]}...')

            # Show decoded arguments (first 2 only to keep output clean)
            if tx.args:
                print('      Args:')
                for _i, (key, value) in enumerate(list(tx.args.items())[:2]):
                    value_str = str(value)[:50]
                    print(f'        - {key}: {value_str}')

        print(f'\n✅ Processed {count} transactions')

    finally:
        await client.close()


async def demo_custom_event_filtering():
    """
    Example 3: Advanced Event Filtering

    Shows how to filter events by block range and process them efficiently.
    """
    print('\n' + '=' * 80)
    print('Example 3: Advanced Event Filtering')
    print('=' * 80)

    # DAI contract (another popular ERC20)
    dai_address = '0x6B175474E89094C44Da98b954EedeAC495271d0F'

    client = ChainscanClient.from_config('etherscan', 'ethereum')

    try:
        print('\n🔍 Loading DAI contract...')
        dai = await client.get_contract(dai_address)

        print('✅ DAI contract loaded!')

        # Get Transfer events from a specific block range
        from_block = 19000000  # Recent block
        to_block = 19000100  # 100 blocks later

        print(f'\n🔎 Fetching Transfer events from blocks {from_block:,} to {to_block:,}...')

        total_transferred = 0
        event_count = 0

        async for event in dai.iter_events(
            event_name='Transfer', from_block=from_block, to_block=to_block, limit=50
        ):
            event_count += 1
            value = event.args.get('value', 0)

            if isinstance(value, int):
                # DAI has 18 decimals
                total_transferred += value / 1e18

        print('\n📊 Results:')
        print(f'   Events found: {event_count}')
        print(f'   Total DAI transferred: {total_transferred:,.2f} DAI')

    finally:
        await client.close()


async def demo_error_handling():
    """
    Example 4: Error Handling

    Shows how to handle common errors gracefully.
    """
    print('\n' + '=' * 80)
    print('Example 4: Error Handling')
    print('=' * 80)

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    try:
        # Try to load a contract with no verified source
        print('\n❌ Attempting to load unverified contract...')
        try:
            unverified = await client.get_contract('0x0000000000000000000000000000000000000000')
            print(f'   Unexpected success: {unverified}')
        except ValueError as e:
            print(f'   ✅ Expected error: {e}')

        # Try to iterate non-existent event
        print('\n❌ Attempting to iterate non-existent event...')
        try:
            usdt = await client.get_contract('0xdac17f958d2ee523a2206206994597c13d831ec7')
            async for event in usdt.iter_events('NonExistentEvent', limit=1):
                print(f'   Unexpected event: {event}')
        except ValueError as e:
            print(f'   ✅ Expected error: {e}')

    finally:
        await client.close()


async def main():
    """Run all demos."""
    print('\n' + '🚀 ' * 20)
    print('SmartContract API Demo - aiochainscan v0.4.0')
    print('🚀 ' * 20)

    # Example 1: USDT Proxy Contract
    await demo_usdt_proxy_contract()

    # Example 2: Uniswap V2 Router
    await demo_uniswap_v2_router()

    # Example 3: Advanced Event Filtering
    await demo_custom_event_filtering()

    # Example 4: Error Handling
    await demo_error_handling()

    print('\n' + '✅ ' * 20)
    print('All demos completed!')
    print('✅ ' * 20 + '\n')


if __name__ == '__main__':
    # Run the demo
    # NOTE: This requires an Etherscan API key in your config
    # or use BlockScout V2 which doesn't require an API key
    asyncio.run(main())
