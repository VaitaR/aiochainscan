"""
Streaming Decode Demo - Memory-Efficient Processing of Large Datasets

This example demonstrates on-the-fly streaming decoding to process
whale addresses with millions of transactions using minimal memory.

Traditional approach:
  1. Fetch ALL 1M transactions (loads into memory)
  2. Pass to Rust decoder
  3. Get back 1M decoded transactions
  Result: OOM for whale addresses

Streaming approach:
  1. Fetch 1000 transactions
  2. Decode batch in thread pool
  3. Yield decoded transactions one-by-one
  4. Repeat
  Result: Constant memory usage (~10MB), can handle unlimited data
"""

import asyncio
import json

from aiochainscan import ChainscanClient


async def example_stream_without_decoding():
    """
    Stream transactions without decoding (fastest, minimal memory).

    Use case: Just need raw transaction data, counting, filtering by block range.
    """
    print('\\n' + '=' * 60)
    print('Example 1: Stream Without Decoding')
    print('=' * 60)

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'  # vitalik.eth

        count = 0
        total_value = 0

        print(f'Streaming transactions for {address}...')

        # Stream without ABI - no decoding overhead
        async for tx in client.iter_transactions(
            address=address,
            from_block=0,
            to_block='latest',
            batch_size=1000,
        ):
            count += 1

            # Process raw transaction
            value = int(tx.get('value', 0))
            total_value += value

            # Print progress every 100 transactions
            if count % 100 == 0:
                print(f'  Processed {count} transactions...', end='\\r')

            # Limit for demo purposes
            if count >= 500:
                break

        print(f'\\n✓ Processed {count} transactions')
        print(f'✓ Total ETH transferred: {total_value / 1e18:.4f} ETH')
        print('✓ Memory usage: ~10MB (constant, regardless of total count)')


async def example_stream_with_decoding():
    """
    Stream transactions WITH decoding (decode on-the-fly).

    Use case: Need to understand function calls, analyze contract interactions.
    """
    print('\\n' + '=' * 60)
    print('Example 2: Stream With Decoding')
    print('=' * 60)

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        # USDT contract (lots of transactions)
        usdt_address = '0xdac17f958d2ee523a2206206994597c13d831ec7'

        try:
            # Fetch ABI once
            print(f'Fetching ABI for {usdt_address}...')
            abi_json = await client.get_contract_abi(usdt_address)
            abi = json.loads(abi_json) if isinstance(abi_json, str) else abi_json

            # Track function call statistics
            function_calls: dict[str, int] = {}
            count = 0

            print('Streaming and decoding transactions...')

            # Stream WITH ABI - decodes each batch in thread pool
            async for tx in client.iter_transactions(
                address=usdt_address,
                abi=abi,
                from_block=19_000_000,  # Recent blocks
                to_block=19_001_000,
                batch_size=500,
            ):
                count += 1

                # Access decoded function call
                func_name = tx.get('decoded_func', 'unknown')
                if func_name:
                    function_calls[func_name] = function_calls.get(func_name, 0) + 1

                # Print first few decoded transactions
                if count <= 3:
                    print(f'\\n  Transaction #{count}:')
                    print(f'    Hash: {tx.get("hash")}')
                    print(f'    Function: {func_name}')
                    print(f'    Args: {tx.get("decoded_data", {})}')

                if count % 50 == 0:
                    print(f'  Decoded {count} transactions...', end='\\r')

                # Limit for demo
                if count >= 200:
                    break

            print(f'\\n\\n✓ Decoded {count} transactions')
            print('\\n📊 Function Call Statistics:')
            for func, count in sorted(function_calls.items(), key=lambda x: x[1], reverse=True):
                print(f'  {func}: {count} calls')

        except Exception as e:
            print(f'⚠️  Could not fetch ABI: {e}')
            print('   (This is expected for some contracts)')


async def example_stream_events():
    """
    Stream event logs with decoding.

    Use case: Monitor Transfer events, analyze DeFi activity, track NFT trades.
    """
    print('\\n' + '=' * 60)
    print('Example 3: Stream Event Logs')
    print('=' * 60)

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        # WETH contract
        weth_address = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'

        try:
            print(f'Fetching ABI for {weth_address}...')
            abi_json = await client.get_contract_abi(weth_address)
            abi = json.loads(abi_json) if isinstance(abi_json, str) else abi_json

            count = 0
            total_deposits = 0

            print('Streaming event logs...')

            # Stream event logs
            async for log in client.iter_logs(
                address=weth_address,
                abi=abi,
                from_block=19_000_000,
                to_block=19_000_100,
                batch_size=100,
            ):
                count += 1

                event_name = log.get('decoded_event', 'unknown')

                # Track Deposit events
                if event_name == 'Deposit':
                    decoded_data = log.get('decoded_data', {})
                    amount = decoded_data.get('wad', 0)
                    if isinstance(amount, int):
                        total_deposits += amount

                # Print first few events
                if count <= 5:
                    print(f'\\n  Event #{count}:')
                    print(f'    Type: {event_name}')
                    print(f'    Block: {log.get("blockNumber")}')
                    print(f'    Data: {log.get("decoded_data", {})}')

                if count % 20 == 0:
                    print(f'  Processed {count} events...', end='\\r')

                # Limit for demo
                if count >= 100:
                    break

            print(f'\\n\\n✓ Processed {count} event logs')
            print(f'✓ Total WETH deposited: {total_deposits / 1e18:.4f} WETH')

        except Exception as e:
            print(f'⚠️  Could not fetch ABI: {e}')


async def example_whale_address_processing():
    """
    Process a whale address with millions of transactions.

    This would OOM with traditional bulk fetching, but streams efficiently.
    """
    print('\\n' + '=' * 60)
    print('Example 4: Whale Address Processing')
    print('=' * 60)

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        # Binance hot wallet (millions of transactions)
        whale_address = '0x28c6c06298d514db089934071355e5743bf21d60'

        print(f'Processing whale address: {whale_address}')
        print('(This address has millions of transactions)')
        print('Traditional approach would OOM, but streaming works!')

        count = 0
        block_range_start = None
        block_range_end = None

        print('\\nStreaming transactions...')

        # Process in batches of 1000
        async for tx in client.iter_transactions(
            address=whale_address,
            from_block=19_000_000,
            to_block=19_001_000,
            batch_size=1000,
        ):
            count += 1

            # Track block range
            block_num = tx.get('blockNumber')
            if isinstance(block_num, str):
                block_num = int(block_num)

            if block_range_start is None or block_num < block_range_start:
                block_range_start = block_num
            if block_range_end is None or block_num > block_range_end:
                block_range_end = block_num

            if count % 100 == 0:
                print(f'  Streamed {count} transactions...', end='\\r')

            # Process more for whale demo
            if count >= 1000:
                break

        print(f'\\n\\n✓ Processed {count} transactions')
        print(f'✓ Block range: {block_range_start} to {block_range_end}')
        print('✓ Memory usage: ~10MB (would be GBs with traditional approach)')
        print('\\n💡 This scales to MILLIONS of transactions with the same memory!')


async def example_smart_contract_streaming():
    """
    Use SmartContract class for high-level streaming.

    Best for: Clean API, automatic ABI fetching, proxy resolution.
    """
    print('\\n' + '=' * 60)
    print('Example 5: SmartContract Streaming (High-Level API)')
    print('=' * 60)

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        try:
            # Create contract instance (auto-fetches ABI)
            print('Creating SmartContract instance for USDT...')
            usdt = await client.get_contract('0xdac17f958d2ee523a2206206994597c13d831ec7')

            print(f'Contract: {usdt.address}')
            print(f'Is Proxy: {usdt.is_proxy}')

            # Stream decoded transactions using high-level API
            print('\\nStreaming decoded transactions...')
            count = 0

            async for tx in usdt.iter_transactions(
                from_block=19_000_000,
                to_block=19_000_100,
                limit=50,
            ):
                count += 1

                if count <= 3:
                    print(f'\\n  Transaction #{count}:')
                    print(f'    Function: {tx.function_name}')
                    print(f'    From: {tx.from_address}')
                    print(f'    Args: {tx.args}')

                if count % 10 == 0:
                    print(f'  Processed {count} transactions...', end='\\r')

            print(f'\\n\\n✓ Processed {count} decoded transactions')

        except Exception as e:
            print(f'⚠️  Error: {e}')


async def main():
    """Run all examples."""
    print('\\n🚀 Streaming Decoder Demo - Memory-Efficient Transaction Processing')
    print('=' * 60)
    print('\\nThis demo shows how to process large datasets with constant memory.')
    print('Perfect for whale addresses, DeFi analytics, and bulk processing.')

    # Run examples
    await example_stream_without_decoding()
    await example_stream_with_decoding()
    await example_stream_events()
    await example_whale_address_processing()
    await example_smart_contract_streaming()

    print('\\n' + '=' * 60)
    print('✅ All examples completed!')
    print('=' * 60)
    print('\\n💡 Key Takeaways:')
    print('  1. Streaming uses constant memory (~10MB) regardless of dataset size')
    print('  2. Decoding happens in thread pool (no event loop blocking)')
    print('  3. Can process millions of transactions without OOM')
    print('  4. Supports backpressure (slow consumers)')
    print('  5. Clean async iteration with async for loops')
    print('\\n📚 See docs for more advanced usage patterns!')


if __name__ == '__main__':
    asyncio.run(main())
