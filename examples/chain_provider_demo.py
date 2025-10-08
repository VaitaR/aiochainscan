#!/usr/bin/env python3
"""
ChainProvider Demo - Showcase the new provider-first API.

This demo showcases OPTION 1: Provider-first approach for creating scanner clients.
"""

import asyncio
import os
import sys
from pathlib import Path

# Allow running directly from the repo without installation
_REPO_ROOT = Path(__file__).resolve().parents[1]
if (_REPO_ROOT / 'aiochainscan').exists():
    sys.path.insert(0, str(_REPO_ROOT))

from aiochainscan import Chain, ChainProvider  # noqa: E402


async def main():
    """Demonstrate the new ChainProvider API."""
    print('=' * 80)
    print('ChainProvider Demo - New Provider-First API')
    print('=' * 80)

    # Test address (Vitalik's address)
    test_address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    # Check API keys
    etherscan_key = os.getenv('ETHERSCAN_KEY')
    moralis_key = os.getenv('MORALIS_API_KEY')

    print('\n🔑 API Keys:')
    print(f'   ETHERSCAN_KEY: {"✓ Available" if etherscan_key else "✗ Missing"}')
    if etherscan_key:
        print(
            '   Note: Etherscan V2 API requires API key registration at https://etherscan.io/apis'
        )
    print(f'   MORALIS_API_KEY: {"✓ Available" if moralis_key else "✗ Missing"}')

    # ========================================================================
    # METHOD 1: By Chain ID (most explicit)
    # ========================================================================
    print('\n' + '=' * 80)
    print('METHOD 1: By Chain ID (Recommended for production)')
    print('=' * 80)

    if etherscan_key:
        print('\n📊 Ethereum Mainnet via Etherscan (chain_id=1):')
        try:
            client = ChainProvider.etherscan(chain_id=1)
            print(f'   Client: {client}')
            print(f'   Chain: {client.chain_name} (ID: {client.chain_id})')
            print(f'   Currency: {client.currency}')

            # Make API call
            from aiochainscan.core.method import Method

            balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)
            balance_eth = int(balance) / 10**18
            print(f'   ✓ Balance: {balance_eth:.6f} ETH')
            await client.close()
        except Exception as e:
            print(f'   ✗ Error: {e}')

    # ========================================================================
    # METHOD 2: By Chain Name (convenient)
    # ========================================================================
    print('\n' + '=' * 80)
    print('METHOD 2: By Chain Name (Convenient for scripting)')
    print('=' * 80)

    print('\n📊 BSC via Etherscan (chain="bsc"):')
    if etherscan_key:
        try:
            client = ChainProvider.etherscan(chain='bsc')
            print(f'   Client: {client}')
            print(f'   Chain: {client.chain_name} (ID: {client.chain_id})')
            print(f'   Currency: {client.currency}')

            from aiochainscan.core.method import Method

            balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)
            balance_bnb = int(balance) / 10**18
            print(f'   ✓ Balance: {balance_bnb:.6f} BNB')
            await client.close()
        except Exception as e:
            print(f'   ✗ Error: {e}')
    else:
        print('   ⊘ Skipped (no ETHERSCAN_KEY)')

    # ========================================================================
    # METHOD 3: By Chain Enum (type-safe)
    # ========================================================================
    print('\n' + '=' * 80)
    print('METHOD 3: By Chain Enum (Type-safe for IDEs)')
    print('=' * 80)

    print('\n📊 Polygon via Etherscan (Chain.POLYGON):')
    if etherscan_key:
        try:
            client = ChainProvider.etherscan(chain=Chain.POLYGON)
            print(f'   Client: {client}')
            print(f'   Chain: {client.chain_name} (ID: {client.chain_id})')
            print(f'   Currency: {client.currency}')

            from aiochainscan.core.method import Method

            balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)
            balance_matic = int(balance) / 10**18
            print(f'   ✓ Balance: {balance_matic:.6f} MATIC')
            await client.close()
        except Exception as e:
            print(f'   ✗ Error: {e}')
    else:
        print('   ⊘ Skipped (no ETHERSCAN_KEY)')

    # ========================================================================
    # METHOD 4: Different Providers (BlockScout)
    # ========================================================================
    print('\n' + '=' * 80)
    print('METHOD 4: BlockScout Provider (Free, no API key)')
    print('=' * 80)

    print('\n📊 Ethereum via BlockScout (chain_id=1):')
    try:
        client = ChainProvider.blockscout(chain_id=1)
        print(f'   Client: {client}')
        print(f'   Chain: {client.chain_name} (ID: {client.chain_id})')
        print(f'   Currency: {client.currency}')

        from aiochainscan.core.method import Method

        balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)
        balance_eth = int(balance) / 10**18
        print(f'   ✓ Balance: {balance_eth:.6f} ETH (from BlockScout)')
        await client.close()
    except Exception as e:
        print(f'   ✗ Error: {e}')

    # ========================================================================
    # METHOD 5: Moralis Provider
    # ========================================================================
    print('\n' + '=' * 80)
    print('METHOD 5: Moralis Provider (Rich metadata)')
    print('=' * 80)

    if moralis_key:
        print('\n📊 Ethereum via Moralis (chain="ethereum"):')
        try:
            client = ChainProvider.moralis(chain='ethereum')
            print(f'   Client: {client}')
            print(f'   Chain: {client.chain_name} (ID: {client.chain_id})')
            print(f'   Currency: {client.currency}')

            from aiochainscan.core.method import Method

            balance = await client.call(Method.ACCOUNT_BALANCE, address=test_address)
            balance_eth = int(balance) / 10**18
            print(f'   ✓ Balance: {balance_eth:.6f} ETH (from Moralis)')
            await client.close()
        except Exception as e:
            print(f'   ✗ Error: {e}')
    else:
        print('   ⊘ Skipped (no MORALIS_API_KEY)')

    # ========================================================================
    # Discovery APIs
    # ========================================================================
    print('\n' + '=' * 80)
    print('DISCOVERY APIs')
    print('=' * 80)

    print('\n📋 List all available providers:')
    providers = ChainProvider.list_providers()
    print(f'   {", ".join(providers)}')

    print('\n📋 List all supported chains:')
    all_chains = ChainProvider.list_chains()
    print(f'   Total: {len(all_chains)} chains')
    for chain in all_chains[:5]:  # Show first 5
        testnet_marker = ' [TESTNET]' if chain.testnet else ''
        print(f'   - {chain.display_name} (ID: {chain.chain_id}){testnet_marker}')
    if len(all_chains) > 5:
        print(f'   ... and {len(all_chains) - 5} more')

    print('\n📋 List chains with BlockScout support:')
    blockscout_chains = ChainProvider.list_chains(provider='blockscout')
    print(f'   Total: {len(blockscout_chains)} chains')
    for chain in blockscout_chains:
        print(f'   - {chain.display_name} → {chain.blockscout_instance}')

    print('\n📋 List mainnets only:')
    mainnets = ChainProvider.list_chains(testnet=False)
    print(f'   Total: {len(mainnets)} mainnets')

    # ========================================================================
    # Chain info lookup
    # ========================================================================
    print('\n' + '=' * 80)
    print('CHAIN INFO LOOKUP')
    print('=' * 80)

    print('\n🔍 Get detailed chain info:')
    chain_info = ChainProvider.get_chain_info(1)
    print(f'   Name: {chain_info.name}')
    print(f'   Display: {chain_info.display_name}')
    print(f'   Chain ID: {chain_info.chain_id}')
    print(f'   Currency: {chain_info.native_currency}')
    print(f'   Aliases: {", ".join(chain_info.aliases)}')
    print(f'   Etherscan: {"✓" if chain_info.etherscan_api_kind else "✗"}')
    print(f'   BlockScout: {"✓" if chain_info.blockscout_instance else "✗"}')
    print(f'   Moralis: {"✓" if chain_info.moralis_chain_id else "✗"}')

    print('\n' + '=' * 80)
    print('✓ Demo Complete!')
    print('=' * 80)

    # Summary
    print('\n📝 Key Benefits of New API:')
    print('   ✓ Clear separation: Provider vs Chain')
    print('   ✓ Support for chain IDs (aligns with Etherscan V2)')
    print('   ✓ Flexible: chain_id, name, or enum')
    print('   ✓ Type-safe with IDE autocomplete')
    print('   ✓ Discoverable with list_chains()')
    print('   ✓ Same interface across all providers')

    print('\n💡 Quick Reference:')
    print('   ChainProvider.etherscan(chain_id=1)')
    print('   ChainProvider.blockscout(chain="sepolia")')
    print('   ChainProvider.moralis(chain=Chain.BSC)')


if __name__ == '__main__':
    asyncio.run(main())
