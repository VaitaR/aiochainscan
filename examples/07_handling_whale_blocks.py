"""
Example: Handling Whale Block Pagination Errors

This example demonstrates how to handle PaginationDataLossError when encountering
blocks with more transactions than the API's pagination limit.
"""

import asyncio

from aiochainscan import ChainscanClient
from aiochainscan.core.method import Method
from aiochainscan.exceptions import PaginationDataLossError


async def fetch_transactions_with_whale_handling():
    """Fetch transactions with proper whale block error handling."""

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    try:
        # Attempt to fetch all transactions for an address
        transactions = await client.call(
            Method.ACCOUNT_TRANSACTIONS,
            address='0x1234567890123456789012345678901234567890',
            start_block=0,
            end_block=99999999,
        )

        print(f'Successfully fetched {len(transactions)} transactions')

    except PaginationDataLossError as e:
        # This exception is raised when a single block has too many transactions
        print('⚠️  Whale block detected!')
        print(f'   Block: {e.block_number}')
        print(f'   Items fetched: {e.items_fetched}')
        print(f'   API limit: {e.api_limit}')
        print(f'   Suggestion: {e.suggested_action}')

        # Strategy 1: Apply filters to reduce result set
        print('\n🔧 Attempting filtered fetch...')
        try:
            # Fetch with specific event topics or address filters
            filtered_txs = await client.call(
                Method.GET_LOGS,
                address='0x1234567890123456789012345678901234567890',
                topics=[
                    '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
                ],  # Transfer event
                start_block=e.block_number,
                end_block=e.block_number,
            )
            print(f'✅ Filtered fetch successful: {len(filtered_txs)} items')
        except Exception as filter_error:
            print(f'❌ Filtered fetch failed: {filter_error}')

        # Strategy 2: Fetch the specific block separately
        print('\n🔧 Fetching block separately...')
        try:
            block = await client.call(
                Method.GET_BLOCK_BY_NUMBER,
                block_number=e.block_number,
            )
            print(f"✅ Block fetch successful: {len(block.get('transactions', []))} transactions")
        except Exception as block_error:
            print(f'❌ Block fetch failed: {block_error}')

        # Strategy 3: Skip the problematic block and continue
        print('\n🔧 Continuing from next block...')
        try:
            remaining_txs = await client.call(
                Method.ACCOUNT_TRANSACTIONS,
                address='0x1234567890123456789012345678901234567890',
                start_block=e.block_number + 1,
                end_block=99999999,
            )
            print(f'✅ Fetched {len(remaining_txs)} transactions after whale block')
            print(
                f'⚠️  Note: {e.items_fetched} transactions from block {e.block_number} were skipped'
            )
        except Exception as continue_error:
            print(f'❌ Continue fetch failed: {continue_error}')

    finally:
        await client.close()


async def fetch_with_progressive_range():
    """Fetch in smaller block ranges to avoid whale blocks."""

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    all_transactions = []
    block_range_size = 10000  # Process 10k blocks at a time

    try:
        current_block = 0
        end_block = 20000000

        while current_block < end_block:
            range_end = min(current_block + block_range_size, end_block)

            try:
                print(f'Fetching blocks {current_block} to {range_end}...')
                txs = await client.call(
                    Method.ACCOUNT_TRANSACTIONS,
                    address='0x1234567890123456789012345678901234567890',
                    start_block=current_block,
                    end_block=range_end,
                )
                all_transactions.extend(txs)
                print(f'  ✅ Got {len(txs)} transactions')

                # Move to next range
                current_block = range_end + 1

            except PaginationDataLossError as e:
                print(f'  ⚠️  Whale block {e.block_number} in range {current_block}-{range_end}')

                # Skip the whale block and continue from next block
                current_block = e.block_number + 1
                print(f'  ⏭️  Skipping to block {current_block}')

                # Optionally log the whale block for manual processing later
                with open('whale_blocks.log', 'a') as f:
                    f.write(f'{e.block_number},{e.items_fetched}\n')

        print(f'\n✅ Total transactions fetched: {len(all_transactions)}')
        print('⚠️  Check whale_blocks.log for skipped blocks')

    finally:
        await client.close()


async def main():
    """Run examples."""
    print('=' * 70)
    print('Example 1: Handling Whale Block Errors')
    print('=' * 70)
    # Uncomment to run (requires valid API configuration)
    # await fetch_transactions_with_whale_handling()

    print('\n' + '=' * 70)
    print('Example 2: Progressive Range Fetching')
    print('=' * 70)
    # Uncomment to run (requires valid API configuration)
    # await fetch_with_progressive_range()

    print('\n💡 Tips for handling whale blocks:')
    print('  1. Use topic filters to reduce result set')
    print('  2. Fetch problematic blocks separately')
    print('  3. Use GraphQL API if available (BlockScout)')
    print('  4. Process in smaller block ranges')
    print('  5. Log whale blocks for manual processing')


if __name__ == '__main__':
    # Note: These examples are for demonstration only
    # Uncomment the asyncio.run() calls in main() to execute
    asyncio.run(main())
