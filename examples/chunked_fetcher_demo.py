#!/usr/bin/env python3
"""
Chunked Block Fetcher Demo - Avoiding Database Timeouts

This example demonstrates how to use the chunked strategy to fetch logs
across very large block ranges without hitting database timeout errors
on blockchain explorers.

When to use chunked strategy:
- Querying popular contracts from block 0 to latest
- Block ranges > 1 million blocks
- When you get gateway timeout (502, 503, 504) errors
- When you need ALL historical data, not just recent

When to use other strategies:
- fast: Best for most use cases, recent blocks, moderate ranges
- basic: Conservative, single-threaded, for unreliable networks
"""

import asyncio

from aiochainscan.core.client import ChainscanClient
from aiochainscan.services.fetch_all import fetch_all


async def demo_chunked_logs_fetching():
    """
    Example 1: Fetch all USDT Transfer events using chunked strategy

    USDT is one of the most active contracts on Ethereum. Trying to fetch
    all Transfer events from block 0 to latest with a normal query would
    timeout on most explorers.

    The chunked strategy splits the range into manageable chunks.
    """
    print('=' * 80)
    print('Example 1: Chunked Logs - USDT Transfer Events')
    print('=' * 80)

    # USDT contract on Ethereum
    usdt_address = '0xdac17f958d2ee523a2206206994597c13d831ec7'

    # Transfer event signature
    transfer_topic = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

    client = ChainscanClient.from_config('etherscan', 'ethereum')

    try:
        print('\n🔍 Fetching Transfer events for USDT from block 4_634_748 to 5_000_000...')
        print('   Strategy: chunked')
        print('   Chunk size: 50,000 blocks')
        print('   This splits ~365k blocks into ~8 chunks\n')

        # Progress tracking
        def on_progress(chunk_num: int, total_chunks: int, items: int):
            print(f'   ✓ Chunk {chunk_num}/{total_chunks} complete: {items} events')

        # Use unified fetch_all with chunked strategy
        # Note: We use a smaller range for demo purposes
        logs = await fetch_all(
            data_type='logs',
            address=usdt_address,
            start_block=4_634_748,  # USDT deployment block
            end_block=5_000_000,  # ~365k blocks
            api_kind='eth',
            network='ethereum',
            api_key=client.api_key,
            http=client._network._http,
            endpoint_builder=client._network._url_builder,
            rate_limiter=client._rate_limiter,
            retry=client._retry_policy,
            strategy='chunked',
            max_offset=50_000,  # Chunk size
            max_concurrent=3,  # Max parallel chunks
            topics=[transfer_topic],
        )

        print(f'\n✅ Fetched {len(logs):,} Transfer events')
        if logs:
            print('\n📊 Sample events:')
            for log in logs[:3]:
                block = log.get('blockNumber', 'N/A')
                tx = log.get('transactionHash', 'N/A')
                print(f'   Block {block}: {tx}')

    finally:
        await client.close()


async def demo_comparison_with_other_strategies():
    """
    Example 2: Compare chunked vs fast strategy

    Shows when each strategy is appropriate.
    """
    print('\n' + '=' * 80)
    print('Example 2: Strategy Comparison')
    print('=' * 80)

    # Popular Uniswap V2 Router contract
    uniswap_router = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'

    client = ChainscanClient.from_config('etherscan', 'ethereum')

    try:
        print('\n📍 Scenario A: Recent blocks (small range)')
        print("   Recommended: 'fast' strategy")

        # Recent 10,000 blocks - fast strategy is perfect
        start_block = 19_000_000
        end_block = 19_010_000

        import time

        start_time = time.time()

        logs_fast = await fetch_all(
            data_type='logs',
            address=uniswap_router,
            start_block=start_block,
            end_block=end_block,
            api_kind='eth',
            network='ethereum',
            api_key=client.api_key,
            http=client._network._http,
            endpoint_builder=client._network._url_builder,
            strategy='fast',
        )

        fast_time = time.time() - start_time
        print(f'   ✓ Fast strategy: {len(logs_fast):,} events in {fast_time:.2f}s')

        print('\n📍 Scenario B: Large historical range (1M+ blocks)')
        print("   Recommended: 'chunked' strategy")
        print('   (Skipping actual fetch - would take too long for demo)')
        print('   Range: block 10,000,000 to 20,000,000 (10M blocks)')
        print('   Chunked: ~100 chunks of 100k blocks each')
        print('   Fast: Would likely timeout on popular contracts')

    finally:
        await client.close()


async def demo_chunked_with_custom_chunk_size():
    """
    Example 3: Adjusting chunk size based on contract activity

    For very active contracts, use smaller chunks.
    For less active contracts, use larger chunks.
    """
    print('\n' + '=' * 80)
    print('Example 3: Custom Chunk Sizes')
    print('=' * 80)

    client = ChainscanClient.from_config('etherscan', 'ethereum')

    try:
        # Example: Less active contract can use larger chunks
        less_active_contract = '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984'  # UNI token

        print('\n🔍 Strategy for less active contract:')
        print('   Chunk size: 200,000 blocks (larger chunks)')
        print('   Reason: Fewer events per block = larger chunks are safe')

        logs = await fetch_all(
            data_type='logs',
            address=less_active_contract,
            start_block=10_861_674,  # UNI deployment
            end_block=11_000_000,
            api_kind='eth',
            network='ethereum',
            api_key=client.api_key,
            http=client._network._http,
            endpoint_builder=client._network._url_builder,
            strategy='chunked',
            max_offset=200_000,  # Larger chunk size
            max_concurrent=4,
        )

        print(f'   ✓ Fetched {len(logs):,} events')

        # Very active contract needs smaller chunks
        print('\n🔍 Strategy for very active contract (USDT):')
        print('   Chunk size: 25,000 blocks (smaller chunks)')
        print('   Reason: Many events per block = need smaller chunks')
        print('   (Skipping actual fetch for demo)')

    finally:
        await client.close()


async def demo_direct_chunked_fetcher():
    """
    Example 4: Using ChunkedBlockFetcher directly

    For advanced use cases where you need more control.
    """
    print('\n' + '=' * 80)
    print('Example 4: Direct ChunkedBlockFetcher Usage')
    print('=' * 80)

    from aiochainscan.services.chunked_fetcher import ChunkedBlockFetcher

    client = ChainscanClient.from_config('etherscan', 'ethereum')

    try:
        # Create fetcher with custom settings
        fetcher = ChunkedBlockFetcher(
            http=client._network._http,
            endpoint_builder=client._network._url_builder,
            chunk_size=10_000,
            rate_limiter=client._rate_limiter,
            retry=client._retry_policy,
            max_concurrent_chunks=2,
        )

        print('\n🔧 Direct fetcher configuration:')
        print(f'   Chunk size: {fetcher.chunk_size:,} blocks')
        print(f'   Max concurrent chunks: {fetcher.max_concurrent_chunks}')

        # Track progress
        progress_log = []

        def track_progress(chunk_num: int, total: int, items: int):
            progress_log.append(f'Chunk {chunk_num}/{total}: {items} items')

        # Fetch logs directly
        logs = await fetcher.fetch_logs(
            address='0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',  # UNI
            from_block=10_861_674,
            to_block=10_900_000,
            api_kind='eth',
            network='ethereum',
            api_key=client.api_key,
            on_chunk_complete=track_progress,
        )

        print('\n📊 Progress log:')
        for entry in progress_log:
            print(f'   {entry}')

        print(f'\n✅ Total events: {len(logs):,}')

    finally:
        await client.close()


async def demo_chunked_transactions():
    """
    Example 5: Chunked strategy for account transactions

    Works for transaction lists too, not just logs.
    """
    print('\n' + '=' * 80)
    print('Example 5: Chunked Transaction Fetching')
    print('=' * 80)

    client = ChainscanClient.from_config('etherscan', 'ethereum')

    try:
        # Example: Fetch all transactions for a busy address
        vitalik_address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

        print("\n🔍 Fetching transactions for Vitalik's address")
        print(f'   Address: {vitalik_address}')
        print('   Strategy: chunked')
        print('   (Using small range for demo)')

        txs = await fetch_all(
            data_type='transactions',
            address=vitalik_address,
            start_block=0,
            end_block=1_000_000,
            api_kind='eth',
            network='ethereum',
            api_key=client.api_key,
            http=client._network._http,
            endpoint_builder=client._network._url_builder,
            strategy='chunked',
            max_offset=100_000,  # 100k block chunks
            max_concurrent=3,
        )

        print(f'\n✅ Fetched {len(txs):,} transactions')
        if txs:
            print('\n📊 Sample transactions:')
            for tx in txs[:3]:
                block = tx.get('blockNumber', 'N/A')
                hash_val = tx.get('hash', 'N/A')
                print(f'   Block {block}: {hash_val}')

    finally:
        await client.close()


async def main():
    """Run all examples."""
    print('\n' + '=' * 80)
    print('CHUNKED BLOCK FETCHER DEMONSTRATION')
    print('=' * 80)
    print('\nThis demo shows how to use the chunked strategy to avoid')
    print('database timeouts when fetching large block ranges.\n')

    # Run examples
    await demo_chunked_logs_fetching()
    await demo_comparison_with_other_strategies()
    await demo_chunked_with_custom_chunk_size()
    await demo_direct_chunked_fetcher()
    await demo_chunked_transactions()

    print('\n' + '=' * 80)
    print('SUMMARY')
    print('=' * 80)
    print("\n✅ Use 'chunked' strategy when:")
    print('   - Block range > 500k blocks')
    print('   - Querying popular contracts with lots of activity')
    print('   - Getting gateway timeout errors (502, 503, 504)')
    print('   - Need complete historical data from block 0')

    print("\n✅ Use 'fast' strategy when:")
    print('   - Recent blocks (last few thousand)')
    print('   - Moderate block ranges (< 500k blocks)')
    print('   - Less active contracts')

    print("\n✅ Use 'basic' strategy when:")
    print('   - Network is unreliable')
    print('   - Conservative, single-threaded fetching needed')
    print('   - Debugging pagination issues')

    print('\n' + '=' * 80)


if __name__ == '__main__':
    asyncio.run(main())
