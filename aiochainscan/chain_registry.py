"""
Chain Registry - unified chain information and provider mappings.
"""

import warnings
from dataclasses import dataclass
from typing import Any

from .base_url import is_url_like, validate_base_url
from .config import get_config_manager

# ---------------------------------------------------------------------------
# UrlBuilder registry-backed topology
# ---------------------------------------------------------------------------

URL_BUILDER_CHAIN_IDS: dict[tuple[str, str], str] = {
    ('eth', 'main'): '1',
    ('eth', 'goerli'): '5',
    ('eth', 'sepolia'): '11155111',
    ('eth', 'holesky'): '17000',
    ('eth', 'test'): '5',
    ('eth', 'ropsten'): '3',
    ('eth', 'rinkeby'): '4',
    ('eth', 'kovan'): '42',
    ('optimism', 'main'): '10',
    ('optimism', 'goerli'): '420',
    ('optimism', 'test'): '420',
    ('bsc', 'main'): '56',
    ('bsc', 'test'): '97',
    ('bsc', 'testnet'): '97',
    ('polygon', 'main'): '137',
    ('polygon', 'mumbai'): '80001',
    ('polygon', 'test'): '80001',
    ('polygon', 'testnet'): '80001',
    ('arbitrum', 'main'): '42161',
    ('arbitrum', 'nova'): '42170',
    ('arbitrum', 'goerli'): '421613',
    ('arbitrum', 'test'): '421613',
    ('base', 'main'): '8453',
    ('base', 'goerli'): '84531',
    ('base', 'sepolia'): '84532',
    ('linea', 'main'): '59144',
    ('linea', 'test'): '59140',
    ('gnosis', 'main'): '100',
    ('gnosis', 'chiado'): '10200',
    ('fantom', 'main'): '250',
    ('fantom', 'test'): '4002',
    ('fantom', 'testnet'): '4002',
    ('mode', 'main'): '34443',
    ('blast', 'main'): '81457',
    ('blast', 'sepolia'): '168587773',
}


URL_BUILDER_CURRENCIES: dict[str, str] = {
    'eth': 'ETH',
    'bsc': 'BNB',
    'polygon': 'MATIC',
    'optimism': 'ETH',
    'arbitrum': 'ETH',
    'fantom': 'FTM',
    'gnosis': 'GNO',
    'flare': 'FLR',
    'wemix': 'WEMIX',
    'chiliz': 'CHZ',
    'mode': 'MODE',
    'linea': 'LINEA',
    'blast': 'BLAST',
    'base': 'BASE',
    'blockscout_eth': 'ETH',
    'blockscout_sepolia': 'ETH',
    'blockscout_gnosis': 'xDAI',
    'blockscout_polygon': 'MATIC',
    'blockscout_base': 'ETH',
    'blockscout_bsc': 'BNB',
    'nodereal': 'BNB',
    'blockscout_optimism': 'ETH',
    'blockscout_arbitrum': 'ETH',
    'blockscout_scroll': 'ETH',
    'blockscout_linea': 'ETH',
}


BLOCKSCOUT_HOSTS: dict[str, str] = {
    'blockscout_eth': 'eth.blockscout.com',
    'blockscout_sepolia': 'eth-sepolia.blockscout.com',
    'blockscout_gnosis': 'gnosis.blockscout.com',
    'blockscout_polygon': 'polygon.blockscout.com',
    'blockscout_base': 'base.blockscout.com',
    'blockscout_bsc': 'bsc.blockscout.com',
    'blockscout_optimism': 'optimism.blockscout.com',
    'blockscout_arbitrum': 'arbitrum.blockscout.com',
    'blockscout_scroll': 'scroll.blockscout.com',
    'blockscout_linea': 'linea.blockscout.com',
}


V2_QUERY_AUTH_API_KINDS: set[str] = {'eth', 'optimism', 'arbitrum', 'bsc', 'polygon', 'base'}


def get_url_builder_profile(api_kind: str, network: str) -> dict[str, str | None]:
    """Resolve URL builder profile for ``(api_kind, network)``.

    Returns keys:
    - ``base_url``
    - ``api_url``
    - ``currency``
    - ``auth_mode``: ``header`` or ``query``
    - ``chainid``: optional
    """

    kind = api_kind.lower().strip()
    net = network.lower().strip()

    if kind not in URL_BUILDER_CURRENCIES:
        supported = ', '.join(sorted(URL_BUILDER_CURRENCIES))
        raise ValueError(f'Incorrect api_kind {kind!r}, supported only: {supported}')

    currency = URL_BUILDER_CURRENCIES[kind]
    chainid = URL_BUILDER_CHAIN_IDS.get((kind, net))

    if kind in V2_QUERY_AUTH_API_KINDS:
        return {
            'base_url': 'https://etherscan.io',
            'api_url': 'https://api.etherscan.io/v2/api',
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    if kind in BLOCKSCOUT_HOSTS:
        host = BLOCKSCOUT_HOSTS[kind]
        return {
            'base_url': f'https://{host}',
            'api_url': f'https://{host}/api',
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    if kind == 'nodereal':
        # NodeReal builds its own JSON-RPC/REST URLs in the scanner; this
        # profile only satisfies the UrlBuilder the client constructs.
        rpc_base = (
            'https://bsc-testnet.nodereal.io/v1'
            if net in {'test', 'testnet', 'bsc-testnet'}
            else 'https://bsc-mainnet.nodereal.io/v1'
        )
        return {
            'base_url': 'https://nodereal.io',
            'api_url': rpc_base,
            'currency': currency,
            'auth_mode': 'header',
            'chainid': URL_BUILDER_CHAIN_IDS.get(
                ('bsc', 'main' if 'testnet' not in net else 'test')
            ),
        }

    if kind == 'fantom':
        net = 'testnet' if net in {'test', 'testnet'} else 'main'
        if net == 'main':
            base_url = 'https://ftmscan.com'
            api_url = 'https://api.ftmscan.com/api'
        else:
            base_url = 'https://testnet.ftmscan.com'
            api_url = 'https://api-testnet.ftmscan.com/api'
        return {
            'base_url': base_url,
            'api_url': api_url,
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    if kind == 'gnosis':
        return {
            'base_url': 'https://gnosisscan.io',
            'api_url': 'https://api.gnosisscan.io/api',
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    if kind == 'flare':
        return {
            'base_url': 'https://flare.network',
            'api_url': 'https://flare-explorer.flare.network/api',
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    if kind == 'linea':
        return {
            'base_url': 'https://lineascan.build',
            'api_url': 'https://api.lineascan.build/api',
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    if kind == 'blast':
        return {
            'base_url': 'https://blastscan.io',
            'api_url': 'https://api.blastscan.io/api',
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    if kind == 'wemix':
        return {
            'base_url': 'https://wemixscan.com',
            'api_url': 'https://api.wemixscan.com/api',
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    if kind == 'chiliz':
        return {
            'base_url': 'https://chiliz.com',
            'api_url': 'https://scan.chiliz.com/api',
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    if kind == 'mode':
        base = 'https://routescan.io/v2/network/mainnet/evm/34443/etherscan'
        return {
            'base_url': base,
            'api_url': f'{base}/api',
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    raise ValueError(f'Unsupported api_kind for url profile: {kind!r}')


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
    # Sonic
    146: {
        'name': 'sonic',
        'aliases': ['sonic'],
        'moralis_hex': '0x92',
    },
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


# ---------------------------------------------------------------------------
# Scanner target resolution — the single resolution point behind
# ChainscanClient.from_config
# ---------------------------------------------------------------------------

# Default scanner version when none is provided (everything else defaults to v1)
DEFAULT_SCANNER_VERSIONS: dict[str, str] = {
    'etherscan': 'v2',
    'blockscout_v2': 'v2',
}

# Configuration-manager scanner ids for non-BlockScout scanners (api key lookup).
# There is deliberately no entry for 'moralis'/'routscan': no such scanner exists,
# unknown names fall through as-is and the config manager raises its honest
# 'Unknown scanner' error for them.
SCANNER_CONFIG_IDS: dict[str, str] = {
    'etherscan': 'eth',
}

# BlockScout configuration ids keyed by canonical network name
BLOCKSCOUT_CONFIG_IDS: dict[str, str] = {
    'ethereum': 'blockscout_eth',
    'eth': 'blockscout_eth',
    'polygon': 'blockscout_polygon',
    'gnosis': 'blockscout_gnosis',
    'optimism': 'blockscout_optimism',
    'base': 'blockscout_base',
    'bsc': 'blockscout_bsc',
    'bnb': 'blockscout_bsc',
    'scroll': 'blockscout_scroll',
    'linea': 'blockscout_linea',
}

# Per-scanner network-name aliases, used for configuration-manager lookups only
SCANNER_NETWORK_ALIASES: dict[str, dict[str, str]] = {
    'etherscan': {
        # All EtherscanV2 networks route through the single unified endpoint
        # (api.etherscan.io/v2/api?chainid=...), so all map to 'main' for config lookup
        'ethereum': 'main',
        'eth': 'main',
        'base': 'main',
        'bsc': 'main',
        'bnb': 'main',
        'binance': 'main',
        'polygon': 'main',
        'matic': 'main',
        'arbitrum': 'main',
        'arb': 'main',
        'optimism': 'main',
        'op': 'main',
        'sonic': 'main',
    },
    'blockscout': {'ethereum': 'eth', 'main': 'eth'},
    'blockscout_v2': {'main': 'ethereum'},
    # NodeReal's config entry is keyed by canonical chain names; the BSC
    # aliases map onto 'bsc' for the configuration-manager lookup.
    'nodereal': {'bnb': 'bsc', 'binance': 'bsc'},
}

# UrlBuilder api_kind per scanner name (BlockScout v1 uses its network-specific id)
SCANNER_API_KINDS: dict[str, str] = {
    'etherscan': 'eth',
    'blockscout_v2': 'blockscout_eth',
    'nodereal': 'nodereal',
}

# Scanners whose transport can be pointed at a custom base URL
# (self-hosted BlockScout, Etherscan v2 proxy). Everything else rejects
# URL-shaped networks with an honest error.
CUSTOM_BASE_URL_SCANNERS: frozenset[str] = frozenset({'etherscan', 'blockscout', 'blockscout_v2'})

# Network label used for custom base_url configurations: the chain is served
# by a user-provided instance, not by a registry deployment.
CUSTOM_NETWORK_LABEL = 'custom'


@dataclass(frozen=True)
class ScannerTarget:
    """Fully resolved construction target for ``ChainscanClient``.

    Carries exactly the values the scanner stack consumes: ``scanner_name`` /
    ``scanner_version`` select the ``Scanner`` class, ``api_kind`` selects the
    UrlBuilder profile, ``network`` is the canonical network name, ``api_key``
    the resolved credential (``''`` when the scanner needs none), ``chain_id``
    the numeric chain identifier (``None`` for custom base URLs without an
    ``expected_chain_id`` — unknown until the instance is probed) and
    ``base_url`` an optional custom instance root overriding the registry.
    """

    scanner_name: str
    scanner_version: str
    network: str
    api_kind: str
    api_key: str
    chain_id: int | None
    base_url: str | None = None


def resolve_scanner_target(
    scanner: str,
    network: str | int,
    api_key: str | None = None,
    scanner_version: str | None = None,
    expected_chain_id: int | None = None,
    allow_http: bool = False,
) -> ScannerTarget:
    """Resolve ``(scanner, network, api_key)`` into a :class:`ScannerTarget`.

    Single resolution point for client construction: version defaulting, the
    ``blockscout_v2`` → ``('blockscout', 'v2')`` rename, canonical network
    normalization, UrlBuilder ``api_kind`` mapping and the api-key default
    from the configuration manager (env vars / .env / config files).

    URL-vs-alias heuristic: when ``network`` is a string carrying a
    ``scheme://`` prefix it is treated as a custom base URL (self-hosted
    BlockScout instance or an Etherscan v2 proxy) — validated/normalized via
    :func:`aiochainscan.base_url.validate_base_url` — and the registry
    network mappings are bypassed. Chain aliases never contain ``://``, so
    alias resolution is unchanged (backward compatible).

    Args:
        scanner: Scanner implementation name (e.g. 'etherscan', 'blockscout',
            'blockscout_v2'). Unknown names raise ``ValueError`` once they
            reach the configuration manager or the scanner registry.
        network: Chain name/alias, chain ID (e.g. 'ethereum', 'eth', 8453),
            or a base URL (``https://my-blockscout.internal``).
        api_key: Explicit API key. When ``None`` (default), the key is looked
            up via the configuration manager; when provided, credential
            lookup is skipped (existence of the scanner is still enforced).
        scanner_version: Explicit scanner version override. When ``None``,
            defaults to 'v2' for etherscan/blockscout_v2, 'v1' otherwise.
        expected_chain_id: Chain id the custom instance is expected to serve.
            Required for URL-shaped networks on etherscan (V2 routes every
            request by ``chainid``); optional for BlockScout (``None`` keeps
            the chain unknown until ``get_chain_info()``/``validate_chain()``
            probes it). Passed through to the client, which validates lazily
            on the first request.
        allow_http: Permit cleartext ``http://`` base URLs (default False).
            Emitting an API key over cleartext additionally raises a
            ``RuntimeWarning``.

    Returns:
        Frozen :class:`ScannerTarget` ready for client construction.

    Raises:
        ValueError: Unknown chain/network, unknown scanner, network not
            supported by the scanner, missing required API key, an invalid
            base URL, or a scanner that cannot honor a custom base URL.
    """
    # URL-shaped networks select the custom-instance branch (see heuristic
    # in the docstring); everything else stays on the registry path.
    if isinstance(network, str) and is_url_like(network):
        return _resolve_custom_base_url_target(
            scanner,
            network,
            api_key=api_key,
            scanner_version=scanner_version,
            expected_chain_id=expected_chain_id,
            allow_http=allow_http,
        )

    # Default scanner version if not provided
    if scanner_version is None:
        scanner_version = DEFAULT_SCANNER_VERSIONS.get(scanner, 'v1')

    # 'blockscout_v2' is a public alias for ('blockscout', 'v2')
    actual_scanner_name = scanner
    if scanner == 'blockscout_v2':
        actual_scanner_name = 'blockscout'
        scanner_version = 'v2'

    # Canonical chain resolution — raises ValueError for unknown chains
    chain_id = resolve_chain_id(network)

    # Canonical network name: ints resolve via the registry, strings are preserved
    network_str = get_chain_name(chain_id) if isinstance(network, int) else str(network)

    # Normalize network aliases for configuration lookup only
    config_network = network_str  # Preserve original for the client property
    aliases = SCANNER_NETWORK_ALIASES.get(scanner)
    if aliases is not None:
        config_network = aliases.get(network_str, network_str)

    # Configuration-manager scanner id (BlockScout's id depends on the
    # normalized network, so aliases must be resolved first).
    if scanner == 'blockscout':
        scanner_id = BLOCKSCOUT_CONFIG_IDS.get(config_network, f'blockscout_{config_network}')
    else:
        scanner_id = SCANNER_CONFIG_IDS.get(scanner, scanner)

    # Resolve the API key
    if scanner == 'blockscout_v2':
        resolved_api_key = ''  # BlockScout V2 doesn't require API key
    elif api_key is not None:
        resolved_api_key = api_key
    else:
        resolved_api_key = get_config_manager().create_client_config(scanner_id, config_network)[
            'api_key'
        ]

    # UrlBuilder api_kind (BlockScout v1 uses the network-specific scanner id)
    api_kind = scanner_id if scanner == 'blockscout' else SCANNER_API_KINDS.get(scanner, scanner)

    return ScannerTarget(
        scanner_name=actual_scanner_name,
        scanner_version=scanner_version,
        network=network_str,
        api_kind=api_kind,
        api_key=resolved_api_key,
        chain_id=chain_id,
    )


def _resolve_custom_base_url_target(
    scanner: str,
    url: str,
    api_key: str | None,
    scanner_version: str | None,
    expected_chain_id: int | None,
    allow_http: bool,
) -> ScannerTarget:
    """Resolve a URL-shaped ``network`` into a custom-instance target.

    The registry is bypassed entirely: BlockScout flavors run keyless against
    the given instance root, etherscan runs against it as a V2 proxy with the
    usual API-key requirement plus a mandatory ``expected_chain_id`` (the V2
    protocol routes every request by ``chainid``).
    """
    base_url = validate_base_url(url, allow_http=allow_http)

    if scanner not in CUSTOM_BASE_URL_SCANNERS:
        supported = ', '.join(sorted(CUSTOM_BASE_URL_SCANNERS))
        raise ValueError(
            f'{scanner!r} does not support a custom base_url; supported scanners: {supported}'
        )

    if scanner_version is None:
        scanner_version = DEFAULT_SCANNER_VERSIONS.get(scanner, 'v1')

    # 'blockscout_v2' is a public alias for ('blockscout', 'v2')
    actual_scanner_name = scanner
    if scanner == 'blockscout_v2':
        actual_scanner_name = 'blockscout'
        scanner_version = 'v2'

    resolved_api_key = ''
    if actual_scanner_name == 'etherscan':
        if expected_chain_id is None:
            raise ValueError(
                'expected_chain_id is required for etherscan with a custom base_url: '
                'the V2 multichain API routes every request by chainid'
            )
        if api_key is not None:
            resolved_api_key = api_key
        else:
            resolved_api_key = get_config_manager().create_client_config('eth', 'main')['api_key']

    if resolved_api_key and base_url.startswith('http://'):
        warnings.warn(
            'API key will be sent over cleartext http — credentials are visible on the wire. '
            'Prefer https or remove the API key from this configuration.',
            RuntimeWarning,
            stacklevel=3,
        )

    return ScannerTarget(
        scanner_name=actual_scanner_name,
        scanner_version=scanner_version,
        network=CUSTOM_NETWORK_LABEL,
        # Custom instances use the neutral Ethereum profile of each family;
        # every request URL is built from base_url, not from this mapping.
        api_kind='eth' if actual_scanner_name == 'etherscan' else 'blockscout_eth',
        api_key=resolved_api_key,
        chain_id=expected_chain_id,
        base_url=base_url,
    )


def get_scanner_network_name(scanner_name: str, scanner_version: str, network: str) -> str:
    """Map the unified network name to the scanner-specific network name.

    Different scanners use different naming conventions for the same networks:
    BlockScout v1 uses 'eth' for Ethereum mainnet, BlockScout v2 uses
    'ethereum', and Etherscan uses 'main'. Other networks pass through
    unchanged.

    Args:
        scanner_name: Name of the scanner (e.g. 'etherscan', 'blockscout')
        scanner_version: Version of the scanner (e.g. 'v1', 'v2')
        network: Unified network name (e.g. 'ethereum', 'polygon')

    Returns:
        Scanner-specific network name
    """
    if scanner_name == 'blockscout' and scanner_version == 'v1':
        # v1 uses 'eth' for Ethereum mainnet
        if network in ('ethereum', 'main'):
            return 'eth'
    elif scanner_name == 'blockscout' and scanner_version == 'v2':
        # v2 uses 'ethereum' for Ethereum mainnet
        if network == 'main':
            return 'ethereum'
    elif scanner_name == 'etherscan' and network == 'ethereum':
        # Etherscan uses 'main' for Ethereum mainnet
        return 'main'

    # For other cases, use the network name as-is
    return network
