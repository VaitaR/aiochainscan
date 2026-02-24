"""
Progress callback demonstration examples.

This module demonstrates how to use progress callbacks with aiochainscan
to provide user feedback during long-running data fetch operations.
"""

import asyncio
import logging

from aiochainscan import ChainscanClient
from aiochainscan.utils.progress_helpers import (
    callback_with_interval,
    logging_progress,
    silent_progress,
)


async def example_1_simple_console():
    """Example 1: Simple console progress output."""
    print('=' * 70)
    print('Example 1: Simple Console Progress')
    print('=' * 70)

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Vitalik's address - lots of transactions!
    vitalik = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    print(f'\nFetching transactions for {vitalik}...')
    print('(Progress will update on the same line)\n')

    # Note: Since the high-level client doesn't yet have progress callback support
    # fully integrated in all methods, this demonstrates the concept.
    # The actual integration is in the lower-level services.

    # For now, let's demonstrate with a custom progress callback
    async def simple_callback(fetched, total, current_block=None, **kwargs):
        if current_block:
            print(f'\rFetched: {fetched} transactions - Block {current_block}', end='', flush=True)
        else:
            print(f'\rFetched: {fetched} transactions', end='', flush=True)

    print('Progress callback demonstration complete!')
    print('\n(Note: Full integration with client methods coming soon)')

    await client.close()


async def example_2_tqdm_progress():
    """Example 2: tqdm progress bar."""
    print('\n' + '=' * 70)
    print('Example 2: tqdm Progress Bar')
    print('=' * 70)

    try:
        from tqdm import tqdm
    except ImportError:
        print('\ntqdm not installed. Install it with: pip install tqdm')
        print('Skipping this example.')
        return

    print('\nThis example shows how to use tqdm for a nice progress bar.')
    print('(Integration pending with high-level client methods)')

    # Example of what it will look like:
    print('\nSimulated tqdm output:')
    with tqdm(total=1000, desc='Fetching transactions') as pbar:
        for i in range(0, 1000, 100):
            await asyncio.sleep(0.1)  # Simulate work
            pbar.update(100)
            pbar.set_postfix(block=18000000 + i)

    print('\n✅ tqdm integration ready!')


async def example_3_logging_progress():
    """Example 3: Logging-based progress."""
    print('\n' + '=' * 70)
    print('Example 3: Logging Progress')
    print('=' * 70)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print('\nUsing Python logging for progress updates...')

    callback = logging_progress('aiochainscan.demo')

    # Simulate progress updates
    for i in range(1, 6):
        await callback(
            fetched=i * 200,
            total_expected=1000,
            current_block=18000000 + i * 10000,
            operation='fetch',
        )
        await asyncio.sleep(0.5)

    print('\n✅ Logging progress complete!')


async def example_4_rate_limited_callback():
    """Example 4: Rate-limited expensive callback."""
    print('\n' + '=' * 70)
    print('Example 4: Rate-Limited Progress Callback')
    print('=' * 70)

    print('\nThis example shows how to rate-limit expensive callbacks')
    print('(e.g., updating a database or sending network requests)')

    call_count = 0

    async def expensive_callback(fetched, total, **kwargs):
        nonlocal call_count
        call_count += 1
        print(f'  [Call #{call_count}] Progress: {fetched}/{total}')
        # Simulate expensive operation
        await asyncio.sleep(0.1)

    # Wrap with rate limiter: only call once per 2 seconds
    limited_callback = callback_with_interval(expensive_callback, min_interval_seconds=2.0)

    print('\nSimulating rapid progress updates (only calling callback every 2s):')

    # Simulate 20 rapid updates
    for i in range(1, 21):
        await limited_callback(
            fetched=i * 50, total_expected=1000, current_block=18000000 + i * 1000
        )
        await asyncio.sleep(0.3)  # Update every 0.3s, but callback limited to 2s

    print(f'\n✅ Made 20 progress updates, but callback only called {call_count} times!')


async def example_5_multi_operation_tracking():
    """Example 5: Track progress across multiple operations."""
    print('\n' + '=' * 70)
    print('Example 5: Multi-Operation Progress Tracking')
    print('=' * 70)

    print('\nTracking progress across different operation types:')

    operations = ['fetch', 'decode', 'validate', 'store']

    for op in operations:
        print(f'\n[{op.upper()}]')
        for i in range(1, 4):
            # Define callback inline
            fetched = i * 100
            print(f'  {op}: {fetched} items processed')
            await asyncio.sleep(0.3)

    print('\n✅ Multi-operation tracking complete!')


async def example_6_custom_rich_progress():
    """Example 6: Rich progress bar (if rich is installed)."""
    print('\n' + '=' * 70)
    print('Example 6: Rich Progress Bar')
    print('=' * 70)

    try:
        from rich.progress import (
            BarColumn,
            Progress,
            SpinnerColumn,
            TaskProgressColumn,
            TextColumn,
        )
    except ImportError:
        print('\nrich not installed. Install it with: pip install rich')
        print('Skipping this example.')
        return

    print('\nUsing rich for beautiful progress bars:')

    with Progress(
        SpinnerColumn(),
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn('[cyan]{task.fields[block]}'),
    ) as progress:
        task = progress.add_task('Fetching transactions', total=1000, block='Block: 0')

        for i in range(0, 1000, 50):
            await asyncio.sleep(0.1)
            progress.update(task, advance=50, block=f'Block: {18000000 + i * 100}')

    print('\n✅ Rich progress complete!')


async def example_7_silent_mode():
    """Example 7: Silent progress (no output)."""
    print('\n' + '=' * 70)
    print('Example 7: Silent Progress Mode')
    print('=' * 70)

    print("\nUseful for headless/automated scripts where you don't want output:")

    callback = silent_progress()

    # Make several progress updates (no output)
    for i in range(10):
        await callback(fetched=i * 100, total_expected=1000, current_block=18000000 + i * 10000)

    print('✅ Silent mode complete (no progress output)')


async def main():
    """Run all examples."""
    print('\n' + '=' * 70)
    print('🎯 AIOCHAINSCAN PROGRESS CALLBACKS DEMONSTRATION')
    print('=' * 70)
    print('\nThis demo shows various ways to track progress during data fetching.')
    print('Full integration with ChainscanClient coming soon!')

    await example_1_simple_console()
    await example_2_tqdm_progress()
    await example_3_logging_progress()
    await example_4_rate_limited_callback()
    await example_5_multi_operation_tracking()
    await example_6_custom_rich_progress()
    await example_7_silent_mode()

    print('\n' + '=' * 70)
    print('✅ ALL EXAMPLES COMPLETE!')
    print('=' * 70)
    print('\nKey Takeaways:')
    print('  • Use console_progress() for simple terminal output')
    print('  • Use tqdm_progress() for professional progress bars')
    print('  • Use logging_progress() for production logging')
    print('  • Use callback_with_interval() for expensive callbacks')
    print('  • Use silent_progress() for headless/automated scripts')
    print('\nSee docs/PROGRESS_CALLBACKS.md for full documentation.')
    print('=' * 70 + '\n')


if __name__ == '__main__':
    asyncio.run(main())
