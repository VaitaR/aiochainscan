"""Static registry data — the measured chain and scanner tables.

The shipped truth: ``STANDARD_CHAINS`` (canonical chains with aliases and
per-provider ids), the UrlBuilder chain-id table, the per-kind UrlBuilder
profiles and the ``SCANNER_RECORDS`` every derived view is built from, plus
the read accessors over the chain table. Pure data: this module imports
nothing from :mod:`aiochainscan.config` and nothing above it anywhere else.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

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


# ---------------------------------------------------------------------------
# Scanner records and per-kind UrlBuilder profiles — the topology source
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KindProfile:
    """UrlBuilder-facing facts for one ``api_kind``.

    Static explorer data (currency, domains) plus the config-manager facts the
    kind carries (its config-dialect networks, its credential family). The
    families whose profile output is *computed* — the Etherscan V2 unified
    endpoint (``v2_query_auth``) and the BlockScout instance hosts — stay
    computed in :func:`get_url_builder_profile`, and so does NodeReal's
    JSON-RPC dialect (its URLs and chain id derive from the network, not from
    data).
    """

    currency: str
    base_url: str | None = None
    api_url: str | None = None
    #: v1-style explorers with a separate testnet domain, served when the
    #: network name is ``'test'``/``'testnet'``. Declared as a pair.
    testnet_base_url: str | None = None
    testnet_api_url: str | None = None
    #: Routed through the unified ``api.etherscan.io/v2/api`` endpoint with
    #: query auth; every request carries the chain id.
    v2_query_auth: bool = False
    #: Config-dialect networks of the config-manager scanner id named like
    #: the kind, when one exists. ``None`` for kinds with no config id
    #: (wemix/chiliz/mode); 'eth' and 'nodereal' declare theirs on their
    #: scanner records instead.
    config_networks: frozenset[str] | None = None
    #: Config id whose credential is the fallback when this kind's own key is
    #: absent (the V2 family: one Etherscan account serves several chains).
    credential_family: str | None = None
    #: Configuration-manager presentation row for the config id named like the
    #: kind. Declared here so one scanner id is ONE row: a kind carrying a
    #: display name is a config-manager scanner, one without it (wemix/chiliz/
    #: mode) has no config entry at all, and the two cannot drift apart.
    display_name: str | None = None
    base_domain: str | None = None
    requires_api_key: bool = True
    special_config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.testnet_base_url is None) != (self.testnet_api_url is None):
            raise ValueError('KindProfile: testnet_base_url and testnet_api_url are a pair')
        if (self.display_name is None) != (self.base_domain is None):
            raise ValueError('KindProfile: display_name and base_domain are a pair')


_URL_KIND_PROFILES: dict[str, KindProfile] = {
    # Etherscan V2 family — one unified endpoint, chainid-routed, query auth.
    'eth': KindProfile(
        currency='ETH',
        v2_query_auth=True,
        display_name='Etherscan',
        base_domain='etherscan.io',
    ),
    'bsc': KindProfile(
        currency='BNB',
        v2_query_auth=True,
        config_networks=frozenset({'main', 'test'}),
        credential_family='eth',
        display_name='BscScan',
        base_domain='bscscan.com',
    ),
    'polygon': KindProfile(
        currency='MATIC',
        v2_query_auth=True,
        config_networks=frozenset({'main', 'mumbai', 'test'}),
        credential_family='eth',
        display_name='PolygonScan',
        base_domain='polygonscan.com',
    ),
    'optimism': KindProfile(
        currency='ETH',
        v2_query_auth=True,
        config_networks=frozenset({'main', 'goerli', 'test'}),
        credential_family='eth',
        display_name='Optimism Etherscan',
        base_domain='etherscan.io',
        special_config={'subdomain_pattern': 'optimistic'},
    ),
    'arbitrum': KindProfile(
        currency='ETH',
        v2_query_auth=True,
        config_networks=frozenset({'main', 'nova', 'goerli', 'test'}),
        credential_family='eth',
        display_name='Arbiscan',
        base_domain='arbiscan.io',
    ),
    'base': KindProfile(
        currency='BASE',
        v2_query_auth=True,
        config_networks=frozenset({'main', 'goerli', 'sepolia'}),
        credential_family='eth',
        display_name='Etherscan (Base)',
        base_domain='etherscan.io',
        special_config={'etherscan_v2': True},
    ),
    # v1-style per-explorer domains, query auth.
    'fantom': KindProfile(
        currency='FTM',
        base_url='https://ftmscan.com',
        api_url='https://api.ftmscan.com/api',
        testnet_base_url='https://testnet.ftmscan.com',
        testnet_api_url='https://api-testnet.ftmscan.com/api',
        config_networks=frozenset({'main', 'test'}),
        display_name='FtmScan',
        base_domain='ftmscan.com',
    ),
    'gnosis': KindProfile(
        currency='GNO',
        base_url='https://gnosisscan.io',
        api_url='https://api.gnosisscan.io/api',
        config_networks=frozenset({'main', 'chiado'}),
        display_name='GnosisScan',
        base_domain='gnosisscan.io',
    ),
    'flare': KindProfile(
        currency='FLR',
        base_url='https://flare.network',
        api_url='https://flare-explorer.flare.network/api',
        config_networks=frozenset({'main', 'test'}),
        display_name='Flare Explorer',
        base_domain='flare.network',
        requires_api_key=False,
        special_config={'subdomain_pattern': 'flare-explorer'},
    ),
    'wemix': KindProfile(
        currency='WEMIX',
        base_url='https://wemixscan.com',
        api_url='https://api.wemixscan.com/api',
    ),
    'chiliz': KindProfile(
        currency='CHZ',
        base_url='https://chiliz.com',
        api_url='https://scan.chiliz.com/api',
    ),
    'mode': KindProfile(
        currency='MODE',
        base_url='https://routescan.io/v2/network/mainnet/evm/34443/etherscan',
        api_url='https://routescan.io/v2/network/mainnet/evm/34443/etherscan/api',
    ),
    'linea': KindProfile(
        currency='LINEA',
        base_url='https://lineascan.build',
        api_url='https://api.lineascan.build/api',
        config_networks=frozenset({'main', 'test'}),
        display_name='LineaScan',
        base_domain='lineascan.build',
    ),
    'blast': KindProfile(
        currency='BLAST',
        base_url='https://blastscan.io',
        api_url='https://api.blastscan.io/api',
        config_networks=frozenset({'main', 'sepolia'}),
        display_name='BlastScan',
        base_domain='blastscan.io',
    ),
    # NodeReal: currency and config networks here; URLs/chain id are dialect
    # (computed in get_url_builder_profile).
    'nodereal': KindProfile(
        currency='BNB',
        config_networks=frozenset({'bsc', 'bsc-testnet'}),
        display_name='NodeReal',
        base_domain='nodereal.io',
        special_config={'mega_node': True},
    ),
}


@dataclass(frozen=True)
class ScannerRecord:
    """Every registry fact about one public scanner name, in one place.

    The lookup tables below (:data:`DEFAULT_SCANNER_VERSIONS`,
    :data:`SCANNER_CONFIG_IDS`, :data:`BLOCKSCOUT_CONFIG_IDS`,
    :data:`SCANNER_CONFIG_NETWORKS`, :data:`SCANNER_NETWORK_ALIASES`,
    :data:`SCANNER_API_KINDS`, :data:`CUSTOM_BASE_URL_SCANNERS`) derive from
    these records at import — adding or altering a scanner means editing one
    record, and consistency between the views is validated at import by
    :func:`_validate_scanner_topology` instead of being assumed.

    Fields:
        kind: Scanner family ('etherscan', 'blockscout', 'nodereal'). The
            two BlockScout public names share the family; the 'blockscout'
            record is its family owner and carries the per-instance
            topology (hosts, currencies, config ids, display names) that
            both legs serve.
        default_version: Version used when the caller passes none
            (everything else defaults to 'v1').
        config_id: Config-manager id for credential lookup; ``None`` means
            the scanner name itself (BlockScout v1 resolves per network via
            ``config_ids_by_network``).
        api_kind: UrlBuilder api_kind; ``None`` means the scanner name.
        network_aliases: Network-name aliases applied for configuration
            lookups only (the client-facing network name is preserved).
        supported_networks: Config-dialect networks of the scanner's own
            config id (``None`` for BlockScout, whose ids derive from the
            instance hosts).
        instance_hosts: BlockScout family only — network alias → public
            instance host.
        instance_currencies: BlockScout family only — UrlBuilder host id →
            native currency symbol.
        config_ids_by_network: BlockScout family only — network name →
            config-manager id.
        display_names: BlockScout family only — UrlBuilder host id →
            human-readable scanner name (consumed by the config manager).
        custom_base_url: Whether the transport can be pointed at a custom
            base URL (self-hosted BlockScout, Etherscan v2 proxy).
    """

    kind: str
    default_version: str = 'v1'
    config_id: str | None = None
    api_kind: str | None = None
    network_aliases: Mapping[str, str] = field(default_factory=dict)
    supported_networks: frozenset[str] | None = None
    instance_hosts: Mapping[str, str] = field(default_factory=dict)
    instance_currencies: Mapping[str, str] = field(default_factory=dict)
    config_ids_by_network: Mapping[str, str] = field(default_factory=dict)
    display_names: Mapping[str, str] = field(default_factory=dict)
    custom_base_url: bool = False


SCANNER_RECORDS: dict[str, ScannerRecord] = {
    'etherscan': ScannerRecord(
        kind='etherscan',
        default_version='v2',
        config_id='eth',
        api_kind='eth',
        network_aliases={
            # All EtherscanV2 networks route through the single unified endpoint
            # (api.etherscan.io/v2/api?chainid=...), so all map to 'main' for
            # config lookup
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
            'bsc-testnet': 'main',
            'gnosis': 'main',
            'megaeth': 'main',
            'plasma': 'main',
            'avalanche-fuji': 'main',
            'avalanche': 'main',
            'linea': 'main',
            'blast': 'main',
            'base-sepolia': 'main',
            'arbitrum-sepolia': 'main',
            'blast-sepolia': 'main',
            # Remaining chains from the v2 chainlist (2026-09-11); all route
            # through the same unified endpoint, so all collapse to 'main'.
            'xdc': 'main',
            'xdc-apothem-testnet': 'main',
            'unichain': 'main',
            'monad': 'main',
            'bittorrent-chain': 'main',
            'opbnb': 'main',
            'fraxtal': 'main',
            'world': 'main',
            'stable': 'main',
            'hyperevm': 'main',
            'bittorrent-chain-testnet': 'main',
            'unichain-sepolia': 'main',
            'sei-testnet': 'main',
            'sei': 'main',
            'stable-testnet': 'main',
            'fraxtal-hoodi': 'main',
            'abstract': 'main',
            'memecore': 'main',
            'world-sepolia': 'main',
            'mantle': 'main',
            'mantle-sepolia': 'main',
            'opbnb-testnet': 'main',
            'megaeth-testnet': 'main',
            'plasma-testnet': 'main',
            'monad-testnet': 'main',
            'abstract-sepolia': 'main',
            'sonic-testnet': 'main',
            'apechain-curtis-testnet': 'main',
            'apechain': 'main',
            'celo': 'main',
            'memecore-insectarium-testnet': 'main',
            'linea-sepolia': 'main',
            'polygon-amoy': 'main',
            'berachain-bepolia-testnet': 'main',
            'berachain': 'main',
            'taiko': 'main',
            'taiko-hoodi': 'main',
            'hoodi-testnet': 'main',
            'katana-bokuto': 'main',
            'katana': 'main',
            'celo-sepolia': 'main',
            'op-sepolia': 'main',
        },
        # Config-dialect networks the V2 endpoint actually serves. Every
        # mainnet alias above collapses to 'main'; the testnets keep their own
        # names. ('test' is absent because no chain resolves under it here.)
        supported_networks=frozenset({'main', 'sepolia'}),
        custom_base_url=True,
    ),
    'blockscout': ScannerRecord(
        kind='blockscout',
        # Family owner: the per-instance topology both BlockScout legs serve.
        network_aliases={'ethereum': 'eth', 'main': 'eth'},
        # Hosts are live-verified (2026-09-10: v1 `/api`, v2 `/api/v2` and
        # `/api/eth-rpc` on each). Gnosis, Optimism and Scroll serve their
        # BlockScout deployment under a chain-branded hostname and 301 the
        # `*.blockscout.com` alias there; the transport does not follow
        # redirects, so the branded host is the only working spelling.
        # Linea and BSC have no BlockScout instance at all (404) and are
        # therefore absent from the whole BlockScout topology.
        instance_hosts={
            'eth': 'eth.blockscout.com',
            'ethereum': 'eth.blockscout.com',
            'sepolia': 'eth-sepolia.blockscout.com',
            'gnosis': 'gnosisscan.io',
            'polygon': 'polygon.blockscout.com',
            'optimism': 'explorer.optimism.io',
            'arbitrum': 'arbitrum.blockscout.com',
            'base': 'base.blockscout.com',
            'scroll': 'scrollscan.com',
            'zksync': 'zksync.blockscout.com',
            'rootstock': 'rootstock.blockscout.com',
            'fuse': 'explorer.fuse.io',
            'hashkey': 'hsk.blockscout.com',
            'tac': 'explorer.tac.build',
            'astar': 'astar.blockscout.com',
            'matchain': 'matchscan.io',
            'flow': 'evm.flow.com',
            'worldmobile': 'explorer.worldmobile.io',
            'lyra': 'explorer.derive.xyz',
            'soneium': 'soneium.blockscout.com',
            'lightlink': 'phoenix.lightlink.io',
            'megaeth': 'megaeth.blockscout.com',
            'mizuhiki-awaji': 'awaji.blockscout.com',
            'zetachain': 'zetascan.com',
            'iota': 'explorer.evm.iota.org',
            'immutable': 'explorer.immutable.com',
            'zilliqa': 'zilliqa.blockscout.com',
            'mode': 'explorer.mode.network',
            'etherlink': 'explorer.etherlink.com',
            'pepe-unchained': 'pepuscan.com',
            'plume': 'explorer.plume.org',
            'plume-testnet': 'testnet-explorer.plume.org',
            'hpp': 'explorer.hpp.io',
            'mizuhiki': 'mizuhiki.blockscout.com',
            'numine': 'numine.blockscout.com',
            'mocachain': 'scan.mocachain.org',
            'stability': 'explorer.stabilityprotocol.com',
        },
        instance_currencies={
            'blockscout_eth': 'ETH',
            'blockscout_mizuhiki': 'MIZU',
            'blockscout_numine': 'NUMINE',
            'blockscout_mocachain': 'MOCA',
            'blockscout_stability': 'FREE',
            'blockscout_sepolia': 'ETH',
            'blockscout_gnosis': 'xDAI',
            'blockscout_polygon': 'MATIC',
            'blockscout_base': 'ETH',
            'blockscout_optimism': 'ETH',
            'blockscout_arbitrum': 'ETH',
            'blockscout_scroll': 'ETH',
            'blockscout_zksync': 'ETH',
            'blockscout_rootstock': 'RBTC',
            'blockscout_fuse': 'FUSE',
            'blockscout_hashkey': 'HSK',
            'blockscout_tac': 'TAC',
            'blockscout_astar': 'ASTR',
            'blockscout_matchain': 'BNB',
            'blockscout_flow': 'FLOW',
            'blockscout_worldmobile': 'WMTX',
            'blockscout_lyra': 'ETH',
            'blockscout_soneium': 'ETH',
            'blockscout_lightlink': 'ETH',
            'blockscout_megaeth': 'ETH',
            'blockscout_mizuhiki-awaji': 'MIZU',
            'blockscout_zetachain': 'ZETA',
            'blockscout_iota': 'IOTA',
            'blockscout_immutable': 'IMX',
            'blockscout_zilliqa': 'ZIL',
            'blockscout_mode': 'ETH',
            'blockscout_etherlink': 'XTZ',
            'blockscout_pepe-unchained': 'PEPU',
            'blockscout_plume': 'PLUME',
            'blockscout_plume-testnet': 'PLUME',
            'blockscout_hpp': 'ETH',
        },
        config_ids_by_network={
            'ethereum': 'blockscout_eth',
            'mizuhiki': 'blockscout_mizuhiki',
            'numine': 'blockscout_numine',
            'mocachain': 'blockscout_mocachain',
            'stability': 'blockscout_stability',
            'eth': 'blockscout_eth',
            'polygon': 'blockscout_polygon',
            'gnosis': 'blockscout_gnosis',
            'optimism': 'blockscout_optimism',
            'base': 'blockscout_base',
            'scroll': 'blockscout_scroll',
            'zksync': 'blockscout_zksync',
            'rootstock': 'blockscout_rootstock',
            'fuse': 'blockscout_fuse',
            'hashkey': 'blockscout_hashkey',
            'tac': 'blockscout_tac',
            'astar': 'blockscout_astar',
            'matchain': 'blockscout_matchain',
            'flow': 'blockscout_flow',
            'worldmobile': 'blockscout_worldmobile',
            'lyra': 'blockscout_lyra',
            'soneium': 'blockscout_soneium',
            'lightlink': 'blockscout_lightlink',
            'megaeth': 'blockscout_megaeth',
            'mizuhiki-awaji': 'blockscout_mizuhiki-awaji',
            'zetachain': 'blockscout_zetachain',
            'iota': 'blockscout_iota',
            'immutable': 'blockscout_immutable',
            'zilliqa': 'blockscout_zilliqa',
            'mode': 'blockscout_mode',
            'etherlink': 'blockscout_etherlink',
            'pepe-unchained': 'blockscout_pepe-unchained',
            'plume': 'blockscout_plume',
            'plume-testnet': 'blockscout_plume-testnet',
            'hpp': 'blockscout_hpp',
        },
        display_names={
            'blockscout_eth': 'BlockScout Ethereum',
            'blockscout_mizuhiki': 'BlockScout Mizuhiki',
            'blockscout_numine': 'BlockScout Numine',
            'blockscout_mocachain': 'BlockScout Moca Chain',
            'blockscout_stability': 'BlockScout Stability',
            'blockscout_sepolia': 'BlockScout Sepolia',
            'blockscout_gnosis': 'BlockScout Gnosis',
            'blockscout_polygon': 'BlockScout Polygon',
            'blockscout_base': 'BlockScout Base',
            'blockscout_optimism': 'BlockScout Optimism',
            'blockscout_arbitrum': 'BlockScout Arbitrum',
            'blockscout_scroll': 'BlockScout Scroll',
            'blockscout_zksync': 'BlockScout ZKsync Era',
            'blockscout_rootstock': 'BlockScout Rootstock Mainnet',
            'blockscout_fuse': 'BlockScout Fuse Mainnet',
            'blockscout_hashkey': 'BlockScout HSKChain',
            'blockscout_tac': 'BlockScout TAC Mainnet',
            'blockscout_astar': 'BlockScout Astar',
            'blockscout_matchain': 'BlockScout Matchain',
            'blockscout_flow': 'BlockScout Flow EVM Mainnet',
            'blockscout_worldmobile': 'BlockScout WorldMobileChain-Mainnet',
            'blockscout_lyra': 'BlockScout Lyra Chain',
            'blockscout_soneium': 'BlockScout Soneium',
            'blockscout_lightlink': 'BlockScout Lightlink Phoenix Mainnet',
            'blockscout_megaeth': 'BlockScout MegaETH Mainnet',
            'blockscout_mizuhiki-awaji': 'BlockScout MIZUHIKI Testnet Awaji',
            'blockscout_zetachain': 'BlockScout ZetaChain Mainnet',
            'blockscout_iota': 'BlockScout IOTA EVM',
            'blockscout_immutable': 'BlockScout Immutable zkEVM',
            'blockscout_zilliqa': 'BlockScout Zilliqa 2',
            'blockscout_mode': 'BlockScout Mode',
            'blockscout_etherlink': 'BlockScout Etherlink Mainnet',
            'blockscout_pepe-unchained': 'BlockScout Pepe Unchained V2',
            'blockscout_plume': 'BlockScout Plume Mainnet',
            'blockscout_plume-testnet': 'BlockScout Plume Testnet',
            'blockscout_hpp': 'BlockScout HPP Mainnet',
        },
        custom_base_url=True,
    ),
    'blockscout_v2': ScannerRecord(
        kind='blockscout',
        default_version='v2',
        api_kind='blockscout_eth',
        network_aliases={'main': 'ethereum'},
        custom_base_url=True,
    ),
    'nodereal': ScannerRecord(
        kind='nodereal',
        api_kind='nodereal',
        network_aliases={
            # NodeReal's config entry is keyed by canonical chain names; the
            # BSC aliases map onto 'bsc' for the configuration-manager lookup.
            'bnb': 'bsc',
            'binance': 'bsc',
        },
        supported_networks=frozenset({'bsc', 'bsc-testnet'}),
    ),
}

_blockscout_record = SCANNER_RECORDS['blockscout']


# Canonical chain ids with their aliases and per-provider mappings
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
        'moralis_hex': '0x66eee',
    },
    10: {
        'name': 'optimism',
        'aliases': ['optimism', 'op'],
        'blockscout_instance': 'explorer.optimism.io',
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
        'blockscout_instance': 'gnosisscan.io',
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
        'moralis_hex': '0xe708',
    },
    59140: {'name': 'linea-testnet', 'aliases': ['linea-testnet'], 'moralis_hex': '0xe704'},
    81457: {
        'name': 'blast',
        'aliases': ['blast'],
        'moralis_hex': '0x13e31',
    },
    168587773: {'name': 'blast-sepolia', 'aliases': ['blast-sepolia'], 'moralis_hex': '0xa0c71fd'},
    34443: {
        'name': 'mode',
        'aliases': ['mode'],
        'moralis_hex': '0x868b',
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
        'blockscout_instance': 'scrollscan.com',
        'moralis_hex': '0x82750',
    },
    534351: {'name': 'scroll-sepolia', 'aliases': ['scroll-sepolia'], 'moralis_hex': '0x8274f'},
    # Sonic
    146: {
        'name': 'sonic',
        'aliases': ['sonic'],
        'moralis_hex': '0x92',
    },
    # Plasma — no Blockscout instance and no Etherscan-family scanner; identity there comes
    # from Routescan, so this entry carries ids and aliases only.
    9745: {
        'name': 'plasma',
        'aliases': ['plasma', 'xpl'],
        'moralis_hex': '0x2611',
    },
    324: {
        'name': 'zksync',
        'aliases': ['zksync', 'zksync-era'],
        'blockscout_instance': 'zksync.blockscout.com',
        'moralis_hex': '0x144',
    },
    # BlockScout-served chains, hosts live-probed 2026-09-11 (REST /api,
    # v2 /api/v2 and /api/eth-rpc each answered, and eth_chainId matched
    # the id below). Currency symbols come from the canonical chain list,
    # not from the explorer.
    30: {
        'name': 'rootstock',
        'aliases': ['rootstock', 'rsk'],
        'blockscout_instance': 'rootstock.blockscout.com',
        'moralis_hex': '0x1e',
    },
    122: {
        'name': 'fuse',
        'aliases': ['fuse'],
        'blockscout_instance': 'explorer.fuse.io',
        'moralis_hex': '0x7a',
    },
    177: {
        'name': 'hashkey',
        'aliases': ['hashkey'],
        'blockscout_instance': 'hsk.blockscout.com',
        'moralis_hex': '0xb1',
    },
    239: {
        'name': 'tac',
        'aliases': ['tac'],
        'blockscout_instance': 'explorer.tac.build',
        'moralis_hex': '0xef',
    },
    592: {
        'name': 'astar',
        'aliases': ['astar'],
        'blockscout_instance': 'astar.blockscout.com',
        'moralis_hex': '0x250',
    },
    698: {
        'name': 'matchain',
        'aliases': ['matchain'],
        'blockscout_instance': 'matchscan.io',
        'moralis_hex': '0x2ba',
    },
    747: {
        'name': 'flow',
        'aliases': ['flow', 'flow-evm'],
        'blockscout_instance': 'evm.flow.com',
        'moralis_hex': '0x2eb',
    },
    869: {
        'name': 'worldmobile',
        'aliases': ['worldmobile'],
        'blockscout_instance': 'explorer.worldmobile.io',
        'moralis_hex': '0x365',
    },
    957: {
        'name': 'lyra',
        'aliases': ['lyra', 'derive'],
        'blockscout_instance': 'explorer.derive.xyz',
        'moralis_hex': '0x3bd',
    },
    1868: {
        'name': 'soneium',
        'aliases': ['soneium'],
        'blockscout_instance': 'soneium.blockscout.com',
        'moralis_hex': '0x74c',
    },
    1890: {
        'name': 'lightlink',
        'aliases': ['lightlink'],
        'blockscout_instance': 'phoenix.lightlink.io',
        'moralis_hex': '0x762',
    },
    4326: {
        'name': 'megaeth',
        'aliases': ['megaeth'],
        'blockscout_instance': 'megaeth.blockscout.com',
        'moralis_hex': '0x10e6',
    },
    6497: {
        'name': 'mizuhiki-awaji',
        'aliases': ['mizuhiki-awaji'],
        'blockscout_instance': 'awaji.blockscout.com',
        'moralis_hex': '0x1961',
    },
    7000: {
        'name': 'zetachain',
        'aliases': ['zetachain', 'zeta'],
        'blockscout_instance': 'zetascan.com',
        'moralis_hex': '0x1b58',
    },
    8822: {
        'name': 'iota',
        'aliases': ['iota'],
        'blockscout_instance': 'explorer.evm.iota.org',
        'moralis_hex': '0x2276',
    },
    13371: {
        'name': 'immutable',
        'aliases': ['immutable', 'imx'],
        'blockscout_instance': 'explorer.immutable.com',
        'moralis_hex': '0x343b',
    },
    32769: {
        'name': 'zilliqa',
        'aliases': ['zilliqa'],
        'blockscout_instance': 'zilliqa.blockscout.com',
        'moralis_hex': '0x8001',
    },
    42793: {
        'name': 'etherlink',
        'aliases': ['etherlink', 'xtz-evm'],
        'blockscout_instance': 'explorer.etherlink.com',
        'moralis_hex': '0xa729',
    },
    97741: {
        'name': 'pepe-unchained',
        'aliases': ['pepe-unchained'],
        'blockscout_instance': 'pepuscan.com',
        'moralis_hex': '0x17dcd',
    },
    98866: {
        'name': 'plume',
        'aliases': ['plume'],
        'blockscout_instance': 'explorer.plume.org',
        'moralis_hex': '0x18232',
    },
    98867: {
        'name': 'plume-testnet',
        'aliases': ['plume-testnet'],
        'blockscout_instance': 'testnet-explorer.plume.org',
        'moralis_hex': '0x18233',
    },
    190415: {
        'name': 'hpp',
        'aliases': ['hpp'],
        'blockscout_instance': 'explorer.hpp.io',
        'moralis_hex': '0x2e7cf',
    },
    # --- BlockScout official mainnet instances, live-probed 2026-09-11 ---
    6498: {
        'name': 'mizuhiki',
        'aliases': ['mizuhiki'],
        'blockscout_instance': 'mizuhiki.blockscout.com',
        'moralis_hex': '0x1962',
    },
    8021: {
        'name': 'numine',
        'aliases': ['numine'],
        'blockscout_instance': 'numine.blockscout.com',
        'moralis_hex': '0x1f55',
    },
    2288: {
        'name': 'mocachain',
        'aliases': ['mocachain'],
        'blockscout_instance': 'scan.mocachain.org',
        'moralis_hex': '0x8f0',
    },
    101010: {
        'name': 'stability',
        'aliases': ['stability'],
        'blockscout_instance': 'explorer.stabilityprotocol.com',
        'moralis_hex': '0x18a92',
    },
    # --- Etherscan v2 chainlist (GET /v2/chainlist, fetched 2026-09-11) ---
    # Every chain the unified endpoint routes. Free-tier availability is
    # per endpoint, not per chain: ABI/source serve everywhere, the rest on a
    # subset. See AGENTS.md for the measured split.
    50: {
        'name': 'xdc',
        'aliases': ['xdc'],
        'moralis_hex': '0x32',
    },
    51: {
        'name': 'xdc-apothem-testnet',
        'aliases': ['xdc-apothem-testnet'],
        'moralis_hex': '0x33',
    },
    130: {
        'name': 'unichain',
        'aliases': ['unichain'],
        'moralis_hex': '0x82',
    },
    143: {
        'name': 'monad',
        'aliases': ['monad'],
        'moralis_hex': '0x8f',
    },
    199: {
        'name': 'bittorrent-chain',
        'aliases': ['bittorrent-chain'],
        'moralis_hex': '0xc7',
    },
    204: {
        'name': 'opbnb',
        'aliases': ['opbnb'],
        'moralis_hex': '0xcc',
    },
    252: {
        'name': 'fraxtal',
        'aliases': ['fraxtal'],
        'moralis_hex': '0xfc',
    },
    480: {
        'name': 'world',
        'aliases': ['world'],
        'moralis_hex': '0x1e0',
    },
    988: {
        'name': 'stable',
        'aliases': ['stable'],
        'moralis_hex': '0x3dc',
    },
    999: {
        'name': 'hyperevm',
        'aliases': ['hyperevm'],
        'moralis_hex': '0x3e7',
    },
    1029: {
        'name': 'bittorrent-chain-testnet',
        'aliases': ['bittorrent-chain-testnet'],
        'moralis_hex': '0x405',
    },
    1301: {
        'name': 'unichain-sepolia',
        'aliases': ['unichain-sepolia'],
        'moralis_hex': '0x515',
    },
    1328: {
        'name': 'sei-testnet',
        'aliases': ['sei-testnet'],
        'moralis_hex': '0x530',
    },
    1329: {
        'name': 'sei',
        'aliases': ['sei'],
        'moralis_hex': '0x531',
    },
    2201: {
        'name': 'stable-testnet',
        'aliases': ['stable-testnet'],
        'moralis_hex': '0x899',
    },
    2523: {
        'name': 'fraxtal-hoodi',
        'aliases': ['fraxtal-hoodi'],
        'moralis_hex': '0x9db',
    },
    2741: {
        'name': 'abstract',
        'aliases': ['abstract'],
        'moralis_hex': '0xab5',
    },
    4352: {
        'name': 'memecore',
        'aliases': ['memecore'],
        'moralis_hex': '0x1100',
    },
    4801: {
        'name': 'world-sepolia',
        'aliases': ['world-sepolia'],
        'moralis_hex': '0x12c1',
    },
    5000: {
        'name': 'mantle',
        'aliases': ['mantle'],
        'moralis_hex': '0x1388',
    },
    5003: {
        'name': 'mantle-sepolia',
        'aliases': ['mantle-sepolia'],
        'moralis_hex': '0x138b',
    },
    5611: {
        'name': 'opbnb-testnet',
        'aliases': ['opbnb-testnet'],
        'moralis_hex': '0x15eb',
    },
    6343: {
        'name': 'megaeth-testnet',
        'aliases': ['megaeth-testnet'],
        'moralis_hex': '0x18c7',
    },
    9746: {
        'name': 'plasma-testnet',
        'aliases': ['plasma-testnet'],
        'moralis_hex': '0x2612',
    },
    10143: {
        'name': 'monad-testnet',
        'aliases': ['monad-testnet'],
        'moralis_hex': '0x279f',
    },
    11124: {
        'name': 'abstract-sepolia',
        'aliases': ['abstract-sepolia'],
        'moralis_hex': '0x2b74',
    },
    14601: {
        'name': 'sonic-testnet',
        'aliases': ['sonic-testnet'],
        'moralis_hex': '0x3909',
    },
    33111: {
        'name': 'apechain-curtis-testnet',
        'aliases': ['apechain-curtis-testnet'],
        'moralis_hex': '0x8157',
    },
    33139: {
        'name': 'apechain',
        'aliases': ['apechain'],
        'moralis_hex': '0x8173',
    },
    42220: {
        'name': 'celo',
        'aliases': ['celo'],
        'moralis_hex': '0xa4ec',
    },
    43522: {
        'name': 'memecore-insectarium-testnet',
        'aliases': ['memecore-insectarium-testnet'],
        'moralis_hex': '0xaa02',
    },
    59141: {
        'name': 'linea-sepolia',
        'aliases': ['linea-sepolia'],
        'moralis_hex': '0xe705',
    },
    80002: {
        'name': 'polygon-amoy',
        'aliases': ['polygon-amoy'],
        'moralis_hex': '0x13882',
    },
    80069: {
        'name': 'berachain-bepolia-testnet',
        'aliases': ['berachain-bepolia-testnet'],
        'moralis_hex': '0x138c5',
    },
    80094: {
        'name': 'berachain',
        'aliases': ['berachain'],
        'moralis_hex': '0x138de',
    },
    167000: {
        'name': 'taiko',
        'aliases': ['taiko'],
        'moralis_hex': '0x28c58',
    },
    167013: {
        'name': 'taiko-hoodi',
        'aliases': ['taiko-hoodi'],
        'moralis_hex': '0x28c65',
    },
    560048: {
        'name': 'hoodi-testnet',
        'aliases': ['hoodi-testnet'],
        'moralis_hex': '0x88bb0',
    },
    737373: {
        'name': 'katana-bokuto',
        'aliases': ['katana-bokuto'],
        'moralis_hex': '0xb405d',
    },
    747474: {
        'name': 'katana',
        'aliases': ['katana'],
        'moralis_hex': '0xb67d2',
    },
    11142220: {
        'name': 'celo-sepolia',
        'aliases': ['celo-sepolia'],
        'moralis_hex': '0xaa044c',
    },
    11155420: {
        'name': 'op-sepolia',
        'aliases': ['op-sepolia'],
        'moralis_hex': '0xaa37dc',
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
