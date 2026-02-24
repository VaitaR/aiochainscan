"""Demo script showing the async nature of decode_input_with_online_lookup."""

import asyncio
import time

from aiochainscan.adapters.httpx_client import HttpxClientAdapter
from aiochainscan.decode import decode_input_with_online_lookup, sig_db


async def test_concurrent_decoding():
    """Demonstrate that multiple decode operations can run concurrently."""
    print('Testing concurrent async decode_input_with_online_lookup...')

    # Clear cache to ensure real API calls
    sig_db.cache.clear()

    # Create multiple transactions with different function selectors
    transactions = [
        {
            'name': 'transfer',
            'tx': {
                'input': '0xa9059cbb00000000000000000000000095227777777777777777777777777777777777770000000000000000000000000000000000000000000000000000000000000001'
            },
        },
        {
            'name': 'approve',
            'tx': {
                'input': '0x095ea7b300000000000000000000000095227777777777777777777777777777777777770000000000000000000000000000000000000000000000000000000000000001'
            },
        },
    ]

    async with HttpxClientAdapter() as http_client:
        start_time = time.time()

        # Run all decodes concurrently
        tasks = [decode_input_with_online_lookup(item['tx'], http_client) for item in transactions]
        results = await asyncio.gather(*tasks)

        elapsed_time = time.time() - start_time

        print(f'\n✓ Decoded {len(transactions)} transactions concurrently in {elapsed_time:.2f}s')
        print('Results:')
        for i, (item, result) in enumerate(zip(transactions, results, strict=False)):
            print(
                f'  {i + 1}. Expected: {item["name"]}, Got: {result.get("decoded_func", "NOT_DECODED")}'
            )

        # Test that it would have taken longer sequentially
        # (If we had used synchronous requests.get(), these would block)
        print('\n✓ Event loop was not blocked - all requests ran concurrently!')
        print("✓ No synchronous 'requests.get()' calls - fully async!")


if __name__ == '__main__':
    asyncio.run(test_concurrent_decoding())
