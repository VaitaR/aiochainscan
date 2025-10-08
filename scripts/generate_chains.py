#!/usr/bin/env python3
"""
Chain configuration generator.

Automatically fetches supported chains from chainid.network and generates
the chains.py configuration file with Etherscan and Blockscout mappings.

Usage:
    python scripts/generate_chains.py
    python scripts/generate_chains.py --dry-run  # Preview without writing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.request import urlopen

# Etherscan API compatible domains (official Etherscan API v2 support)
ETHERSCAN_DOMAINS = {
    'etherscan.io': 'eth',
    'bscscan.com': 'bsc',
    'polygonscan.com': 'polygon',
    'ftmscan.com': 'fantom',
    'arbiscan.io': 'arbitrum',
    'snowscan.xyz': 'avalanche',
    'optimistic.etherscan.io': 'optimism',
    'basescan.org': 'base',
    'gnosisscan.io': 'gnosis',
    'lineascan.build': 'linea',
    'blastscan.io': 'blast',
    'scrollscan.com': 'scroll',
    'modescan.io': 'mode',
}

# Network name mappings for Etherscan API
ETHERSCAN_NETWORK_NAMES = {
    'mainnet': 'main',
    'testnet': 'test',
    'goerli': 'goerli',
    'sepolia': 'sepolia',
    'holesky': 'holesky',
    'mumbai': 'mumbai',
    'amoy': 'amoy',
    'fuji': 'fuji',
}


class ChainData:
    """Parsed chain data from chainid.network."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.chain_id: int = raw['chainId']
        self.name: str = raw['name']
        self.short_name: str = raw.get('shortName', '').lower()
        self.native_currency: str = raw.get('nativeCurrency', {}).get('symbol', 'ETH')
        self.explorers: list[dict[str, str]] = raw.get('explorers', [])

        # Provider-specific data
        self.etherscan_api_kind: str | None = None
        self.etherscan_network_name: str | None = None
        self.blockscout_instance: str | None = None
        self.moralis_chain_id: str | None = None

        self._parse_explorers()
        self._set_moralis_chain_id()

    def _parse_explorers(self) -> None:
        """Parse explorer URLs to extract provider information."""
        for explorer in self.explorers:
            url = explorer.get('url', '')
            clean_url = url.replace('https://', '').replace('http://', '')

            # Check for Etherscan API domains
            for domain, api_kind in ETHERSCAN_DOMAINS.items():
                if domain in clean_url:
                    self.etherscan_api_kind = api_kind
                    self.etherscan_network_name = self._extract_network_name(clean_url, domain)
                    break

            # Check for Blockscout
            if 'blockscout' in clean_url.lower():
                self.blockscout_instance = clean_url.rstrip('/')

    def _extract_network_name(self, url: str, domain: str) -> str:
        """Extract network name from Etherscan URL."""
        # Remove domain to get subdomain
        parts = url.replace(domain, '').split('.')
        if len(parts) > 1 and parts[0]:
            subdomain = parts[0].strip('-.')

            # Map known subdomains
            for known, mapped in ETHERSCAN_NETWORK_NAMES.items():
                if known in subdomain.lower():
                    return mapped

            return subdomain

        return 'main'

    def _set_moralis_chain_id(self) -> None:
        """Set Moralis chain ID (hex format)."""
        # Moralis supports major chains
        moralis_supported = {1, 10, 56, 137, 250, 8453, 42161, 43114, 59144, 11155111}
        if self.chain_id in moralis_supported:
            self.moralis_chain_id = hex(self.chain_id)

    @property
    def is_testnet(self) -> bool:
        """Determine if this is a testnet."""
        testnet_keywords = ['test', 'goerli', 'sepolia', 'holesky', 'mumbai', 'amoy', 'fuji']
        name_lower = self.name.lower()
        return any(keyword in name_lower for keyword in testnet_keywords)

    @property
    def canonical_name(self) -> str:
        """Generate canonical chain name (lowercase, hyphenated)."""
        # Use short_name if available, otherwise derive from name
        if self.short_name:
            return self.short_name.replace(' ', '-').lower()

        # Clean up display name
        name = self.name.lower()
        name = re.sub(r'\s+(mainnet|testnet|network|chain)$', '', name)
        name = name.replace(' ', '-')
        return name

    @property
    def display_name(self) -> str:
        """Clean display name."""
        return self.name

    def generate_aliases(self) -> frozenset[str]:
        """Generate name aliases for this chain."""
        aliases = {self.canonical_name}

        # Add short name
        if self.short_name:
            aliases.add(self.short_name)

        # Add common variations
        if self.chain_id == 1:
            aliases.update({'eth', 'ethereum', 'mainnet', 'eth-mainnet'})
        elif self.chain_id == 56:
            aliases.update({'bsc', 'binance', 'bnb', 'bnb-chain'})
        elif self.chain_id == 137:
            aliases.update({'polygon', 'matic', 'polygon-mainnet'})

        return frozenset(aliases)

    def has_provider_support(self) -> bool:
        """Check if chain has any provider support."""
        return bool(self.etherscan_api_kind or self.blockscout_instance or self.moralis_chain_id)


def fetch_chains() -> list[ChainData]:
    """Fetch chain data from chainid.network."""
    print('Fetching chains from chainid.network...', file=sys.stderr)
    with urlopen('https://chainid.network/chains.json', timeout=30) as response:
        raw_chains = json.loads(response.read())

    chains = [ChainData(raw) for raw in raw_chains]

    # Filter chains with provider support
    supported_chains = [c for c in chains if c.has_provider_support()]

    print(f'Found {len(supported_chains)} chains with provider support', file=sys.stderr)
    return supported_chains


def _generate_enum_name(chain: ChainData) -> str:
    """Generate a readable enum name for a chain."""
    # Custom mappings for well-known chains
    custom_names = {
        1: 'ETHEREUM',
        5: 'GOERLI',
        11155111: 'SEPOLIA',
        17000: 'HOLESKY',
        56: 'BSC',
        97: 'BSC_TESTNET',
        137: 'POLYGON',
        80001: 'POLYGON_MUMBAI',
        80002: 'POLYGON_AMOY',
        10: 'OPTIMISM',
        420: 'OPTIMISM_GOERLI',
        11155420: 'OPTIMISM_SEPOLIA',
        42161: 'ARBITRUM_ONE',
        42170: 'ARBITRUM_NOVA',
        421613: 'ARBITRUM_GOERLI',
        421614: 'ARBITRUM_SEPOLIA',
        8453: 'BASE',
        84531: 'BASE_GOERLI',
        84532: 'BASE_SEPOLIA',
        43114: 'AVALANCHE',
        43113: 'AVALANCHE_FUJI',
        250: 'FANTOM',
        4002: 'FANTOM_TESTNET',
        100: 'GNOSIS',
        10200: 'GNOSIS_CHIADO',
        81457: 'BLAST',
        168587773: 'BLAST_SEPOLIA',
        59144: 'LINEA',
        59140: 'LINEA_GOERLI',
        59141: 'LINEA_SEPOLIA',
        534352: 'SCROLL',
        534351: 'SCROLL_SEPOLIA',
        34443: 'MODE',
        1101: 'POLYGON_ZKEVM',
        2442: 'POLYGON_ZKEVM_CARDONA',
    }

    if chain.chain_id in custom_names:
        return custom_names[chain.chain_id]

    # Default: use canonical name
    return chain.canonical_name.upper().replace('-', '_')


def generate_chain_enum(chains: list[ChainData]) -> str:
    """Generate Chain enum code."""
    lines = [
        'class Chain(IntEnum):',
        '    """',
        '    Enum of supported blockchain networks for type-safe chain selection.',
        '',
        '    Values are EIP-155 chain IDs.',
        '    """',
        '',
    ]

    # Group chains by category
    ethereum_chains = [c for c in chains if c.chain_id in {1, 3, 4, 5, 11155111, 17000}]
    l2_chains = [
        c
        for c in chains
        if c.chain_id
        in {
            10,
            420,
            11155420,  # Optimism
            42161,
            42170,
            421611,
            421613,
            421614,  # Arbitrum
            8453,
            84531,
            84532,  # Base
            81457,
            168587773,  # Blast
            534352,
            534351,  # Scroll
            59144,
            59140,
            59141,  # Linea
            34443,
            919,  # Mode
            1101,
            2442,  # Polygon zkEVM
        }
    ]
    bsc_chains = [c for c in chains if c.chain_id in {56, 97, 5611, 204}]
    polygon_chains = [c for c in chains if c.chain_id in {137, 80001, 80002}]
    other_chains = [
        c
        for c in chains
        if c not in ethereum_chains
        and c not in l2_chains
        and c not in bsc_chains
        and c not in polygon_chains
    ]

    # Ethereum networks
    if ethereum_chains:
        lines.append('    # Ethereum networks')
        for chain in sorted(ethereum_chains, key=lambda x: x.chain_id):
            enum_name = _generate_enum_name(chain)
            lines.append(f'    {enum_name} = {chain.chain_id}')
        lines.append('')

    # Layer 2 networks
    if l2_chains:
        lines.append('    # Layer 2 networks')
        for chain in sorted(l2_chains, key=lambda x: x.chain_id):
            enum_name = _generate_enum_name(chain)
            lines.append(f'    {enum_name} = {chain.chain_id}')
        lines.append('')

    # BSC networks
    if bsc_chains:
        lines.append('    # BNB Smart Chain networks')
        for chain in sorted(bsc_chains, key=lambda x: x.chain_id):
            enum_name = _generate_enum_name(chain)
            lines.append(f'    {enum_name} = {chain.chain_id}')
        lines.append('')

    # Polygon networks
    if polygon_chains:
        lines.append('    # Polygon networks')
        for chain in sorted(polygon_chains, key=lambda x: x.chain_id):
            enum_name = _generate_enum_name(chain)
            lines.append(f'    {enum_name} = {chain.chain_id}')
        lines.append('')

    # Other EVM networks
    if other_chains:
        lines.append('    # Other EVM networks')
        for chain in sorted(other_chains, key=lambda x: x.chain_id):
            enum_name = _generate_enum_name(chain)
            lines.append(f'    {enum_name} = {chain.chain_id}')

    return '\n'.join(lines)


def generate_chains_dict(chains: list[ChainData]) -> str:
    """Generate CHAINS dictionary code."""
    lines = [
        '# Chain registry - single source of truth for all blockchain networks',
        'CHAINS: dict[int, ChainInfo] = {',
    ]

    for chain in sorted(chains, key=lambda x: x.chain_id):
        lines.append(f'    {chain.chain_id}: ChainInfo(')
        lines.append(f'        chain_id={chain.chain_id},')
        lines.append(f"        name='{chain.canonical_name}',")
        lines.append(f"        display_name='{chain.display_name}',")

        # Aliases
        aliases = chain.generate_aliases()
        aliases_str = ', '.join(f"'{a}'" for a in sorted(aliases))
        lines.append(f'        aliases=frozenset({{{aliases_str}}}),')

        lines.append(f"        native_currency='{chain.native_currency}',")

        if chain.is_testnet:
            lines.append('        testnet=True,')

        if chain.etherscan_network_name:
            lines.append(f"        etherscan_network_name='{chain.etherscan_network_name}',")
        if chain.etherscan_api_kind:
            lines.append(f"        etherscan_api_kind='{chain.etherscan_api_kind}',")
        if chain.blockscout_instance:
            lines.append(f"        blockscout_instance='{chain.blockscout_instance}',")
        if chain.moralis_chain_id:
            lines.append(f"        moralis_chain_id='{chain.moralis_chain_id}',")

        lines.append('    ),')

    lines.append('}')
    return '\n'.join(lines)


def generate_chains_file(chains: list[ChainData]) -> str:
    """Generate complete chains.py file content."""
    header = '''"""
Chain registry and provider factory for blockchain scanner APIs.

This module provides a unified interface for creating scanner clients across
different blockchain networks and API providers.

AUTOMATICALLY GENERATED by scripts/generate_chains.py
Do not edit manually. Run: python scripts/generate_chains.py
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path


def _load_env_file_if_exists() -> None:
    """
    Load environment variables from .env file if it exists.

    Searches for .env in:
    1. Current working directory
    2. Project root (where this file is located)
    """
    # Try current working directory first
    cwd_env = Path.cwd() / '.env'
    if cwd_env.exists():
        _load_env_file(cwd_env)
        return

    # Try project root (2 levels up from this file)
    project_root = Path(__file__).parent.parent
    project_env = project_root / '.env'
    if project_env.exists():
        _load_env_file(project_env)


def _load_env_file(env_file: Path) -> None:
    """Load variables from a specific .env file."""
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\\'')

                    # Only set if not already set in environment
                    if key not in os.environ:
                        os.environ[key] = value
    except Exception:
        # Silently ignore errors - .env is optional
        pass


# Load .env file on module import
_load_env_file_if_exists()


@dataclass(frozen=True)
class ChainInfo:
    """
    Canonical chain information.

    Stores all metadata about a blockchain network and provider-specific
    mappings for API access.
    """

    chain_id: int
    """EIP-155 chain ID"""

    name: str
    """Canonical chain name (lowercase, e.g., 'ethereum', 'bsc')"""

    display_name: str
    """Human-readable display name"""

    aliases: frozenset[str] = field(default_factory=frozenset)
    """Alternative names for this chain (eth, mainnet, etc.)"""

    native_currency: str = 'ETH'
    """Native currency symbol"""

    testnet: bool = False
    """Whether this is a testnet"""

    # Provider-specific mappings
    etherscan_network_name: str | None = None
    """Network name for Etherscan API (main, goerli, sepolia, etc.)"""

    blockscout_instance: str | None = None
    """BlockScout instance domain (e.g., 'eth.blockscout.com')"""

    moralis_chain_id: str | None = None
    """Moralis hex chain ID (e.g., '0x1')"""

    etherscan_api_kind: str | None = None
    """Legacy api_kind for UrlBuilder compatibility"""

    def __post_init__(self) -> None:
        """Validate chain info after initialization."""
        if not self.name:
            raise ValueError('Chain name cannot be empty')
        if self.chain_id <= 0:
            raise ValueError(f'Invalid chain ID: {self.chain_id}')


'''

    footer = '''

def resolve_chain(identifier: int | str | Chain) -> ChainInfo:
    """
    Resolve chain identifier to ChainInfo.

    Args:
        identifier: Chain ID (int), name (str), alias (str), or Chain enum

    Returns:
        ChainInfo for the requested chain

    Raises:
        ValueError: If chain is not found

    Examples:
        >>> resolve_chain(1)  # By chain ID
        ChainInfo(chain_id=1, name='ethereum', ...)

        >>> resolve_chain('ethereum')  # By canonical name
        ChainInfo(chain_id=1, name='ethereum', ...)

        >>> resolve_chain('eth')  # By alias
        ChainInfo(chain_id=1, name='ethereum', ...)

        >>> resolve_chain(Chain.ETHEREUM)  # By enum
        ChainInfo(chain_id=1, name='ethereum', ...)
    """
    # Handle Chain enum
    if isinstance(identifier, Chain):
        identifier = identifier.value

    # Handle chain ID
    if isinstance(identifier, int):
        if identifier not in CHAINS:
            available = ', '.join(f'{c.name} ({c.chain_id})' for c in CHAINS.values())
            raise ValueError(f'Unknown chain ID: {identifier}. Available chains: {available}')
        return CHAINS[identifier]

    # Handle string (name or alias)
    if isinstance(identifier, str):
        identifier_lower = identifier.lower().strip()

        # Try exact name match first
        for chain in CHAINS.values():
            if chain.name == identifier_lower:
                return chain

        # Try alias match
        for chain in CHAINS.values():
            if identifier_lower in chain.aliases:
                return chain

        # Build helpful error message
        available_names = sorted(set(c.name for c in CHAINS.values()))
        raise ValueError(
            f"Unknown chain: '{identifier}'. Available chains: {', '.join(available_names)}"
        )

    raise TypeError(
        f'Invalid chain identifier type: {type(identifier).__name__}. Expected int, str, or Chain enum'
    )


def list_chains(
    provider: str | None = None,
    testnet: bool | None = None,
) -> list[ChainInfo]:
    """
    List all supported chains, optionally filtered.

    Args:
        provider: Filter by provider ('etherscan', 'blockscout', 'moralis')
        testnet: Filter by testnet status (True=testnets only, False=mainnets only, None=all)

    Returns:
        List of ChainInfo objects matching filters

    Examples:
        >>> list_chains()  # All chains
        [ChainInfo(...), ...]

        >>> list_chains(provider='blockscout')  # Only chains with BlockScout
        [ChainInfo(...), ...]

        >>> list_chains(testnet=False)  # Only mainnets
        [ChainInfo(...), ...]
    """
    chains = list(CHAINS.values())

    # Filter by provider
    if provider:
        provider_lower = provider.lower()
        if provider_lower == 'etherscan':
            chains = [c for c in chains if c.etherscan_api_kind is not None]
        elif provider_lower == 'blockscout':
            chains = [c for c in chains if c.blockscout_instance is not None]
        elif provider_lower == 'moralis':
            chains = [c for c in chains if c.moralis_chain_id is not None]
        else:
            raise ValueError(
                f"Unknown provider: '{provider}'. Supported: etherscan, blockscout, moralis"
            )

    # Filter by testnet status
    if testnet is not None:
        chains = [c for c in chains if c.testnet == testnet]

    return sorted(chains, key=lambda c: c.chain_id)


def get_env_api_key(provider: str) -> str | None:
    """
    Get API key from environment variables for a provider.

    Args:
        provider: Provider name ('etherscan', 'moralis', etc.)

    Returns:
        API key or None if not found

    Examples:
        >>> get_env_api_key('etherscan')
        'YOUR_API_KEY' or None
    """
    provider_upper = provider.upper()

    # Try various environment variable patterns
    env_vars = [
        f'{provider_upper}_API_KEY',
        f'{provider_upper}_KEY',
        f'{provider_upper}SCAN_KEY',  # For etherscan, bscscan, etc.
    ]

    # Special case for Moralis
    if provider.lower() == 'moralis':
        env_vars.insert(0, 'MORALIS_API_KEY')

    for var in env_vars:
        value = os.getenv(var)
        if value:
            return value

    return None


__all__ = [
    'Chain',
    'ChainInfo',
    'CHAINS',
    'resolve_chain',
    'list_chains',
    'get_env_api_key',
]
'''

    return (
        header
        + '\n\n'
        + generate_chain_enum(chains)
        + '\n\n\n'
        + generate_chains_dict(chains)
        + footer
    )


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Generate chains.py configuration')
    parser.add_argument(
        '--dry-run', action='store_true', help='Preview output without writing file'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path(__file__).parent.parent / 'aiochainscan' / 'chains.py',
        help='Output file path',
    )
    args = parser.parse_args()

    try:
        # Fetch chain data
        chains = fetch_chains()

        # Generate file content
        content = generate_chains_file(chains)

        if args.dry_run:
            print('DRY RUN - Generated content:', file=sys.stderr)
            print(content)
        else:
            # Write to file
            args.output.write_text(content)
            print(f'Successfully generated {args.output}', file=sys.stderr)
            print(f'Total chains: {len(chains)}', file=sys.stderr)

            # Statistics
            etherscan_count = len([c for c in chains if c.etherscan_api_kind])
            blockscout_count = len([c for c in chains if c.blockscout_instance])
            moralis_count = len([c for c in chains if c.moralis_chain_id])

            print(f'  - Etherscan API: {etherscan_count}', file=sys.stderr)
            print(f'  - Blockscout: {blockscout_count}', file=sys.stderr)
            print(f'  - Moralis: {moralis_count}', file=sys.stderr)

    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
