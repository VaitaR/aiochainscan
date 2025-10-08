"""
Chain Discovery Demo

Demonstrates the auto-generated chain configuration with 128+ supported chains.
Shows how to discover available chains and providers.
"""

from aiochainscan import ChainProvider


def main() -> None:
    """Demonstrate chain discovery and provider capabilities."""
    print('=' * 70)
    print('aiochainscan - Auto-Generated Chain Configuration Demo')
    print('=' * 70)
    print()

    # Show total chains
    all_chains = ChainProvider.list_chains()
    print(f'📊 Total supported chains: {len(all_chains)}')
    print()

    # Show chains by provider
    print('🔍 Chains by Provider:')
    print('-' * 70)

    etherscan_chains = ChainProvider.list_chains(provider='etherscan')
    print(f'  Etherscan API v2: {len(etherscan_chains)} chains')
    print(f'    Examples: {", ".join(c.name for c in etherscan_chains[:5])}...')
    print()

    blockscout_chains = ChainProvider.list_chains(provider='blockscout')
    print(f'  Blockscout: {len(blockscout_chains)} chains')
    print(f'    Examples: {", ".join(c.name for c in blockscout_chains[:5])}...')
    print()

    moralis_chains = ChainProvider.list_chains(provider='moralis')
    print(f'  Moralis Web3 API: {len(moralis_chains)} chains')
    print(f'    Examples: {", ".join(c.name for c in moralis_chains[:5])}...')
    print()

    # Show mainnets vs testnets
    print('🌐 Network Types:')
    print('-' * 70)

    mainnets = ChainProvider.list_chains(testnet=False)
    testnets = ChainProvider.list_chains(testnet=True)

    print(f'  Mainnets: {len(mainnets)}')
    print(f'  Testnets: {len(testnets)}')
    print()

    # Show detailed info for popular chains
    print('💎 Popular Chains:')
    print('-' * 70)

    popular_chain_ids = [1, 56, 137, 42161, 10, 8453, 43114, 250, 100]

    for chain_id in popular_chain_ids:
        info = ChainProvider.get_chain_info(chain_id)

        # Provider support indicators
        providers = []
        if info.etherscan_api_kind:
            providers.append('Etherscan')
        if info.blockscout_instance:
            providers.append('Blockscout')
        if info.moralis_chain_id:
            providers.append('Moralis')

        print(f'  {info.display_name:25s} (ID: {info.chain_id:6d})')
        print(f'    Currency: {info.native_currency:10s} Providers: {", ".join(providers)}')
        print()

    # Show how to create clients
    print('🔧 Creating Clients:')
    print('-' * 70)
    print()

    print('  # By chain ID (most explicit):')
    print('  client = ChainProvider.etherscan(chain_id=1)')
    print()

    print('  # By chain name:')
    print('  client = ChainProvider.etherscan(chain="ethereum")')
    print()

    print('  # By Chain enum (IDE autocomplete):')
    print('  from aiochainscan import Chain')
    print('  client = ChainProvider.etherscan(chain=Chain.ETHEREUM)')
    print()

    print('  # Different providers:')
    print('  client = ChainProvider.blockscout(chain_id=1)  # No API key needed')
    print('  client = ChainProvider.moralis(chain="bsc")')
    print()

    # Show chain resolution examples
    print('🔎 Chain Resolution Examples:')
    print('-' * 70)

    examples = [
        (1, 'By chain ID'),
        ('ethereum', 'By canonical name'),
        ('eth', 'By alias'),
        ('mainnet', 'By common alias'),
    ]

    for identifier, description in examples:
        try:
            info = ChainProvider.get_chain_info(identifier)
            print(f'  {description:25s} → {info.display_name}')
        except ValueError as e:
            print(f'  {description:25s} → Error: {e}')

    print()
    print('=' * 70)
    print('✨ Chain configuration auto-generated from chainid.network')
    print('   Run: python scripts/generate_chains.py to update')
    print('=' * 70)


if __name__ == '__main__':
    main()
