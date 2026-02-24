"""
ENS (Ethereum Name Service) Integration Demo

This example demonstrates how to use aiochainscan's ENS integration to:
1. Resolve ENS names to addresses (forward resolution)
2. Lookup addresses to find their ENS names (reverse lookup)
3. Perform batch operations efficiently
4. Integrate ENS with other features like SmartContract API

Requirements:
    - aiochainscan installed
    - Internet connection (uses BlockScout V2 public API)
    - Ethereum mainnet network

Usage:
    python examples/ens_demo.py
"""

import asyncio

from aiochainscan import ChainscanClient


async def demo_forward_resolution():
    """Demo: Resolve ENS names to addresses."""
    print('\n' + '=' * 70)
    print('DEMO 1: Forward Resolution (name → address)')
    print('=' * 70)

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Resolve well-known ENS names
    names = [
        'vitalik.eth',
        'nick.eth',
        'uniswap.eth',
        'ens.eth',
    ]

    for name in names:
        try:
            address = await client.resolve_name(name)
            if address:
                print(f'✓ {name:20} → {address}')
            else:
                print(f'✗ {name:20} → Not found')
        except ValueError as e:
            print(f'✗ {name:20} → Error: {e}')


async def demo_reverse_lookup():
    """Demo: Reverse lookup addresses to ENS names."""
    print('\n' + '=' * 70)
    print('DEMO 2: Reverse Lookup (address → name)')
    print('=' * 70)

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Known addresses with ENS names
    addresses = [
        '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',  # vitalik.eth
        '0xb8c2C29ee19D8307cb7255e1Cd9CbDE883A267d5',  # nick.eth
        '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',  # uniswap.eth (UNI token)
        '0x0000000000000000000000000000000000000000',  # zero address (no ENS)
    ]

    for address in addresses:
        try:
            name = await client.lookup_address(address)
            if name:
                print(f'✓ {address} → {name}')
            else:
                print(f'✗ {address} → No ENS name')
        except ValueError as e:
            print(f'✗ {address} → Error: {e}')


async def demo_batch_operations():
    """Demo: Batch resolution and lookup."""
    print('\n' + '=' * 70)
    print('DEMO 3: Batch Operations (parallel resolution)')
    print('=' * 70)

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Batch resolve multiple names
    print('\n📦 Batch resolving names...')
    names = ['vitalik.eth', 'nick.eth', 'uniswap.eth', 'invalid.eth']
    result = await client.resolve_names(names)

    print(f'\nResolved {len(result)}/{len(names)} names:')
    for name, address in result.items():
        print(f'  {name:20} → {address}')

    # Batch reverse lookup
    print('\n📦 Batch reverse lookup...')
    addresses = [
        '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        '0xb8c2C29ee19D8307cb7255e1Cd9CbDE883A267d5',
        '0x0000000000000000000000000000000000000000',
    ]
    result = await client.lookup_addresses(addresses)

    print(f'\nFound {len(result)}/{len(addresses)} names:')
    for address, name in result.items():
        print(f'  {address} → {name}')


async def demo_caching():
    """Demo: Caching behavior."""
    print('\n' + '=' * 70)
    print('DEMO 4: Caching (performance improvement)')
    print('=' * 70)

    import time

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Clear cache first
    await client.ens.clear_cache()

    # First resolution (cache miss)
    print('\n⏱️  First resolution (cache miss)...')
    start = time.time()
    address = await client.resolve_name('vitalik.eth')
    first_time = time.time() - start
    print(f'   Result: {address}')
    print(f'   Time: {first_time:.3f} seconds')

    # Second resolution (cache hit)
    print('\n⚡ Second resolution (cache hit)...')
    start = time.time()
    address = await client.resolve_name('vitalik.eth')
    cached_time = time.time() - start
    print(f'   Result: {address}')
    print(f'   Time: {cached_time:.3f} seconds')

    speedup = first_time / cached_time if cached_time > 0 else float('inf')
    print(f'\n📊 Speedup: {speedup:.0f}x faster with cache')


async def demo_ens_with_smart_contracts():
    """Demo: Combine ENS with SmartContract API."""
    print('\n' + '=' * 70)
    print('DEMO 5: ENS + SmartContract API Integration')
    print('=' * 70)

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Resolve ENS name to get contract address
    print("\n🔍 Resolving 'uniswap.eth' to contract address...")
    contract_address = await client.resolve_name('uniswap.eth')

    if contract_address:
        print(f'   Contract address: {contract_address}')

        # Get contract instance
        print('\n📄 Fetching contract information...')
        try:
            contract = await client.get_contract(contract_address)
            print(f'   Contract loaded: {contract.address}')
            print(f'   Is proxy: {contract.is_proxy}')

            # Get some events (limited to 5 for demo)
            print('\n📋 Recent Transfer events:')
            count = 0
            async for event in contract.iter_events('Transfer', limit=5):
                count += 1
                from_addr = event.args.get('from', 'N/A')[:10]
                to_addr = event.args.get('to', 'N/A')[:10]
                value = event.args.get('value', 'N/A')
                print(f'   {count}. {from_addr}... → {to_addr}... (value: {value})')

        except Exception as e:
            print(f'   ⚠️  Could not load contract: {e}')
    else:
        print('   ✗ Could not resolve uniswap.eth')


async def demo_error_handling():
    """Demo: Error handling and edge cases."""
    print('\n' + '=' * 70)
    print('DEMO 6: Error Handling')
    print('=' * 70)

    # Try ENS on wrong network
    print('\n⚠️  Attempting ENS on Polygon (should fail)...')
    try:
        client = ChainscanClient.from_config('blockscout_v2', 'polygon')
        await client.resolve_name('vitalik.eth')
        print('   ✗ Should have raised ValueError!')
    except ValueError as e:
        print(f'   ✓ Correctly raised error: {str(e)[:60]}...')

    # Test invalid inputs
    print('\n⚠️  Testing invalid inputs...')
    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    invalid_cases = [
        ('', 'empty string'),
        ('not-ens', 'no .eth suffix'),
        ('invalid.com', 'wrong TLD'),
        (None, 'None value'),
    ]

    for invalid_input, description in invalid_cases:
        try:
            result = await client.resolve_name(invalid_input) if invalid_input else None
            if result is None:
                print(f'   ✓ {description:20} → None (correctly handled)')
            else:
                print(f'   ✗ {description:20} → Got unexpected result: {result}')
        except Exception as e:
            print(f'   ✗ {description:20} → Raised {type(e).__name__}: {e}')


async def demo_ens_property():
    """Demo: Using the ENS property for advanced usage."""
    print('\n' + '=' * 70)
    print('DEMO 7: Advanced ENS Resolver Access')
    print('=' * 70)

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Access ENS resolver directly
    print('\n🔧 Accessing ENS resolver property...')
    resolver = client.ens
    print(f'   Resolver: {resolver}')
    print(f'   Cache enabled: {resolver.enable_cache}')
    print(f'   Cache TTL: {resolver.cache_ttl} seconds')

    # Custom resolver with different settings
    print('\n🔧 Creating custom resolver (no cache)...')
    from aiochainscan.services.ens_resolver import ENSResolver

    custom_resolver = ENSResolver(client, enable_cache=False, cache_ttl=7200)
    print(f'   Custom resolver: {custom_resolver}')

    # Use custom resolver
    address = await custom_resolver.resolve_name('vitalik.eth')
    print(f'   Resolved: vitalik.eth → {address}')


async def main():
    """Run all demos."""
    print('\n' + '=' * 70)
    print('🌐 ENS Integration Demo for aiochainscan')
    print('=' * 70)
    print('\nThis demo shows ENS (Ethereum Name Service) integration features:')
    print('  • Forward resolution (name → address)')
    print('  • Reverse lookup (address → name)')
    print('  • Batch operations')
    print('  • Caching for performance')
    print('  • Integration with SmartContract API')

    try:
        await demo_forward_resolution()
        await demo_reverse_lookup()
        await demo_batch_operations()
        await demo_caching()
        await demo_ens_with_smart_contracts()
        await demo_error_handling()
        await demo_ens_property()

        print('\n' + '=' * 70)
        print('✅ All demos completed successfully!')
        print('=' * 70)

    except Exception as e:
        print(f'\n❌ Demo failed: {e}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
