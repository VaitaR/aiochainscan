"""
Chain Registry - unified chain information and provider mappings.
"""

from typing import Any

# Стандартизированные chain_id с алиасами и provider mappings
STANDARD_CHAINS = {
    # Ethereum ecosystem
    1: {
        'name': 'ethereum',
        'aliases': ['eth', 'ethereum', 'main'],  # 'main' kept for scanner compatibility
        'blockscout_instance': 'eth.blockscout.com',
        'moralis_hex': '0x1',
    },
    5: {
        'name': 'goerli',
        'aliases': ['goerli'],
        'blockscout_instance': 'eth-goerli.blockscout.com',
        'moralis_hex': '0x5',
    },
    11155111: {
        'name': 'sepolia',
        'aliases': ['sepolia'],
        'blockscout_instance': 'eth-sepolia.blockscout.com',
        'moralis_hex': '0xaa36a7',
    },
    17000: {'name': 'holesky', 'aliases': ['holesky'], 'moralis_hex': '0x4268'},
    # Layer 2 networks
    42161: {
        'name': 'arbitrum',
        'aliases': ['arbitrum', 'arb'],
        'blockscout_instance': 'arbitrum.blockscout.com',
        'moralis_hex': '0xa4b1',
    },
    421613: {
        'name': 'arbitrum-goerli',
        'aliases': ['arbitrum-goerli', 'arb-goerli'],
        'moralis_hex': '0x66eed',
    },
    421614: {
        'name': 'arbitrum-sepolia',
        'aliases': ['arbitrum-sepolia', 'arb-sepolia'],
        'moralis_hex': '0xaa37a7',
    },
    10: {
        'name': 'optimism',
        'aliases': ['optimism', 'op'],
        'blockscout_instance': 'optimism.blockscout.com',
        'moralis_hex': '0xa',
    },
    420: {
        'name': 'optimism-goerli',
        'aliases': ['optimism-goerli', 'op-goerli'],
        'moralis_hex': '0x1a4',
    },
    8453: {
        'name': 'base',
        'aliases': ['base'],
        'blockscout_instance': 'base.blockscout.com',
        'moralis_hex': '0x2105',
    },
    84531: {'name': 'base-goerli', 'aliases': ['base-goerli'], 'moralis_hex': '0x14a33'},
    84532: {'name': 'base-sepolia', 'aliases': ['base-sepolia'], 'moralis_hex': '0x14a34'},
    # Other networks
    56: {
        'name': 'bsc',
        'aliases': ['bsc', 'binance', 'bnb'],
        'blockscout_instance': 'bsc.blockscout.com',
        'moralis_hex': '0x38',
    },
    97: {'name': 'bsc-testnet', 'aliases': ['bsc-testnet', 'bnb-testnet'], 'moralis_hex': '0x61'},
    137: {
        'name': 'polygon',
        'aliases': ['polygon', 'matic'],
        'blockscout_instance': 'polygon.blockscout.com',
        'moralis_hex': '0x89',
    },
    80001: {
        'name': 'polygon-mumbai',
        'aliases': ['polygon-mumbai', 'matic-mumbai'],
        'moralis_hex': '0x13881',
    },
    250: {
        'name': 'fantom',
        'aliases': ['fantom', 'ftm'],
        'blockscout_instance': 'ftm.blockscout.com',
        'moralis_hex': '0xfa',
    },
    4002: {
        'name': 'fantom-testnet',
        'aliases': ['fantom-testnet', 'ftm-testnet'],
        'moralis_hex': '0xfa2',
    },
    100: {
        'name': 'gnosis',
        'aliases': ['gnosis', 'xdai'],
        'blockscout_instance': 'gnosis.blockscout.com',
        'moralis_hex': '0x64',
    },
    10200: {
        'name': 'gnosis-chiado',
        'aliases': ['gnosis-chiado', 'xdai-chiado'],
        'moralis_hex': '0x27d8',
    },
    43114: {'name': 'avalanche', 'aliases': ['avalanche', 'avax'], 'moralis_hex': '0xa86a'},
    43113: {
        'name': 'avalanche-fuji',
        'aliases': ['avalanche-fuji', 'avax-fuji'],
        'moralis_hex': '0xa869',
    },
    59144: {
        'name': 'linea',
        'aliases': ['linea'],
        'blockscout_instance': 'linea.blockscout.com',
        'moralis_hex': '0xe708',
    },
    59140: {'name': 'linea-testnet', 'aliases': ['linea-testnet'], 'moralis_hex': '0xe704'},
    81457: {
        'name': 'blast',
        'aliases': ['blast'],
        'blockscout_instance': 'blast.blockscout.com',
        'moralis_hex': '0x13e31',
    },
    168587773: {'name': 'blast-sepolia', 'aliases': ['blast-sepolia'], 'moralis_hex': '0xa0c71fd'},
    34443: {
        'name': 'mode',
        'aliases': ['mode'],
        'blockscout_instance': 'mode.blockscout.com',
        'moralis_hex': '0x868c',
    },
    1284: {'name': 'moonbeam', 'aliases': ['moonbeam', 'glmr'], 'moralis_hex': '0x504'},
    1285: {'name': 'moonriver', 'aliases': ['moonriver', 'movr'], 'moralis_hex': '0x505'},
    1287: {
        'name': 'moonbase-alpha',
        'aliases': ['moonbase-alpha', 'movr-alpha'],
        'moralis_hex': '0x507',
    },
    9001: {'name': 'evmos', 'aliases': ['evmos'], 'moralis_hex': '0x2329'},
    9000: {'name': 'evmos-testnet', 'aliases': ['evmos-testnet'], 'moralis_hex': '0x2328'},
    534352: {
        'name': 'scroll',
        'aliases': ['scroll'],
        'blockscout_instance': 'scroll.blockscout.com',
        'moralis_hex': '0x82750',
    },
    534351: {'name': 'scroll-sepolia', 'aliases': ['scroll-sepolia'], 'moralis_hex': '0x8274f'},
}


def resolve_chain_id(chain: str | int) -> int:
    """Resolve chain name/alias to chain_id."""
    if isinstance(chain, int):
        if chain in STANDARD_CHAINS:
            return chain
        raise ValueError(f'Unknown chain_id: {chain}')

    # Search by name or alias
    chain_lower = chain.lower()
    for chain_id, info in STANDARD_CHAINS.items():
        if info['name'] == chain_lower or chain_lower in info['aliases']:
            return chain_id

    raise ValueError(f'Unknown chain: {chain}')


def get_chain_info(chain_id: int) -> dict[str, Any]:
    """Get chain information by ID."""
    if chain_id not in STANDARD_CHAINS:
        raise ValueError(f'Unknown chain ID: {chain_id}')
    return STANDARD_CHAINS[chain_id]


def list_supported_chains() -> dict[int, dict[str, Any]]:
    """List all supported chains with their information."""
    return {chain_id: info.copy() for chain_id, info in STANDARD_CHAINS.items()}


def get_chain_name(chain_id: int) -> str:
    """Get chain name by ID."""
    name = get_chain_info(chain_id)['name']
    assert isinstance(name, str)
    return name


def get_chain_aliases(chain_id: int) -> list[str]:
    """Get chain aliases by ID."""
    aliases = get_chain_info(chain_id)['aliases']
    assert isinstance(aliases, list)
    return aliases


def get_blockscout_instance(chain_id: int) -> str:
    """Get BlockScout instance URL for chain."""
    info = get_chain_info(chain_id)
    if 'blockscout_instance' not in info:
        raise ValueError(f'BlockScout not available for chain {chain_id}')
    instance = info['blockscout_instance']
    assert isinstance(instance, str)
    return instance


def get_moralis_hex(chain_id: int) -> str:
    """Get Moralis hex chain ID."""
    info = get_chain_info(chain_id)
    if 'moralis_hex' not in info:
        raise ValueError(f'Moralis not available for chain {chain_id}')
    moralis_hex = info['moralis_hex']
    assert isinstance(moralis_hex, str)
    return moralis_hex
