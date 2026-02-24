"""
Simple ENS Reverse Lookup Demo

This example demonstrates ENS reverse lookup (address → name) using
BlockScout V2's built-in ENS support. No API key required!

Note: Forward resolution (name → address) requires Etherscan with API key
because it needs eth_call to query ENS contracts.

Usage:
    python examples/ens_simple_demo.py
"""

import asyncio

from aiochainscan import ChainscanClient


async def main():
    print('=' * 70)
    print('ENS Reverse Lookup Demo (BlockScout V2)')
    print('=' * 70)

    # Create client - no API key needed for BlockScout V2
    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Well-known addresses with ENS names
    addresses = {
        '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045': 'Vitalik Buterin',
        '0xb8c2C29ee19D8307cb7255e1Cd9CbDE883A267d5': 'Nick Johnson (ENS founder)',
        '0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72': 'ENS Public Resolver',
    }

    print('\n🔍 Looking up ENS names for well-known addresses...\n')

    for address, description in addresses.items():
        name = await client.lookup_address(address)
        if name:
            print(f'✅ {description}')
            print(f'   Address: {address}')
            print(f'   ENS Name: {name}\n')
        else:
            print(f'❌ {description}')
            print(f'   Address: {address}')
            print('   No ENS name found\n')

    # Batch lookup
    print('=' * 70)
    print('Batch Reverse Lookup (parallel)')
    print('=' * 70)

    addr_list = list(addresses.keys())
    result = await client.lookup_addresses(addr_list)

    print(f'\n✅ Found ENS names for {len(result)}/{len(addr_list)} addresses:')
    for addr, name in result.items():
        print(f'   {name:30} → {addr}')

    # Demonstrate caching
    print('\n' + '=' * 70)
    print('Caching Performance')
    print('=' * 70)

    import time

    test_addr = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    # Clear cache first
    await client.ens.clear_cache()

    # First lookup (cache miss)
    start = time.time()
    name1 = await client.lookup_address(test_addr)
    time1 = time.time() - start

    # Second lookup (cache hit)
    start = time.time()
    name2 = await client.lookup_address(test_addr)
    time2 = time.time() - start

    print('\n📊 Performance comparison:')
    print(f'   First lookup (cache miss):  {time1:.4f}s → {name1}')
    print(f'   Second lookup (cache hit):  {time2:.4f}s → {name2}')
    if time2 > 0:
        print(f'   Speedup: {time1/time2:.0f}x faster with cache')

    await client.close()

    print('\n' + '=' * 70)
    print('✅ Demo completed!')
    print('=' * 70)


if __name__ == '__main__':
    asyncio.run(main())
