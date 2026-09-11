"""
Chain Registry - unified chain information and provider mappings.
"""

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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

# UrlBuilder api_kind → currency, derived from the per-kind profiles plus the
# BlockScout per-instance currencies (the record is the single place a new
# instance registers a currency).
URL_BUILDER_CURRENCIES: dict[str, str] = {
    **{kind: profile.currency for kind, profile in _URL_KIND_PROFILES.items()},
    **dict(_blockscout_record.instance_currencies),
}

#: Network alias → public BlockScout instance host. The ONE host table for
#: both BlockScout scanners (v1 ``NETWORK_INSTANCES``, v2 ``BASE_URLS``);
#: ``BLOCKSCOUT_HOSTS`` below re-keys the same hosts by UrlBuilder api_kind.
#: Derived from the 'blockscout' scanner record.
BLOCKSCOUT_INSTANCE_HOSTS: dict[str, str] = dict(_blockscout_record.instance_hosts)


BLOCKSCOUT_HOSTS: dict[str, str] = {
    f'blockscout_{alias}': host
    for alias, host in BLOCKSCOUT_INSTANCE_HOSTS.items()
    if f'blockscout_{alias}' in URL_BUILDER_CURRENCIES
}


BLOCKSCOUT_CONFIG_IDS: dict[str, str] = dict(_blockscout_record.config_ids_by_network)

#: UrlBuilder host id → display name (config-manager presentation data whose
#: home is the record; the configuration manager reads this table directly).
BLOCKSCOUT_DISPLAY_NAMES: dict[str, str] = dict(_blockscout_record.display_names)

V2_QUERY_AUTH_API_KINDS: frozenset[str] = frozenset(
    kind for kind, profile in _URL_KIND_PROFILES.items() if profile.v2_query_auth
)

# Default scanner version when none is provided (everything else defaults to
# v1) — the records whose default differs from the global fallback.
DEFAULT_SCANNER_VERSIONS: dict[str, str] = {
    name: record.default_version
    for name, record in SCANNER_RECORDS.items()
    if record.default_version != 'v1'
}

# Configuration-manager scanner ids for non-BlockScout scanners (api key lookup).
# There is deliberately no entry for 'moralis'/'routscan': no such scanner exists,
# unknown names fall through as-is and the config manager raises its honest
# 'Unknown scanner' error for them.
SCANNER_CONFIG_IDS: dict[str, str] = {
    name: record.config_id
    for name, record in SCANNER_RECORDS.items()
    if record.config_id is not None
}

# Networks each configuration-manager scanner id serves, in the config
# lookup dialect ('main'/'test'-style names, not registry chain names).
# Single source of the network-validity oracle for client construction
# (:func:`resolve_scanner_target`); the configuration manager derives its
# builtin ``supported_networks`` from this table instead of mirroring it.
# Derived from three views: the per-kind profiles (Etherscan-family config
# ids), the scanner records ('eth'/'nodereal' own their networks) and the
# BlockScout host ids (each serves exactly its host suffix, so a new
# instance registers once for both).
SCANNER_CONFIG_NETWORKS: dict[str, frozenset[str]] = {
    **{
        kind: networks
        for kind, profile in _URL_KIND_PROFILES.items()
        if (networks := profile.config_networks) is not None
    },
    **{
        (record.config_id if record.config_id is not None else name): record.supported_networks
        for name, record in SCANNER_RECORDS.items()
        if record.supported_networks is not None
    },
    **{
        scanner_id: frozenset({scanner_id.removeprefix('blockscout_')})
        for scanner_id in BLOCKSCOUT_HOSTS
    },
}

# Per-scanner network-name aliases, used for configuration-manager lookups only
SCANNER_NETWORK_ALIASES: dict[str, dict[str, str]] = {
    name: dict(record.network_aliases)
    for name, record in SCANNER_RECORDS.items()
    if record.network_aliases
}

# UrlBuilder api_kind per scanner name (BlockScout v1 uses its network-specific id)
SCANNER_API_KINDS: dict[str, str] = {
    name: record.api_kind
    for name, record in SCANNER_RECORDS.items()
    if record.api_kind is not None
}

# Scanners whose transport can be pointed at a custom base URL
# (self-hosted BlockScout, Etherscan v2 proxy). Everything else rejects
# URL-shaped networks with an honest error.
CUSTOM_BASE_URL_SCANNERS: frozenset[str] = frozenset(
    name for name, record in SCANNER_RECORDS.items() if record.custom_base_url
)

#: Config-manager scanner id → the family config id whose credential is the
#: fallback when the scanner's own key is absent (the Etherscan V2 family:
#: one account, several chains). Read by the configuration manager's builtin
#: definitions; the registry owns family membership, config owns credentials.
CONFIG_CREDENTIAL_FAMILY: dict[str, str] = {
    kind: profile.credential_family
    for kind, profile in _URL_KIND_PROFILES.items()
    if profile.credential_family is not None
}

#: BlockScout instance aliases that intentionally do NOT surface as UrlBuilder
#: host ids. Today: 'zksync' — listed as an instance host but with no
#: ``blockscout_zksync`` currency entry, so no config-manager scanner exists
#: for it. Declared here (not silent); making it live would change the public
#: surface.
DROPPED_INSTANCE_ALIASES: frozenset[str] = frozenset()


def _validate_scanner_topology(
    instance_hosts: Mapping[str, str],
    hosts: Mapping[str, str],
    display_names: Mapping[str, str],
    dropped_aliases: frozenset[str],
) -> None:
    """Import-time proof that the derived scanner tables agree.

    Replaces the two silent failure modes of the formerly hand-maintained
    tables: an instance alias that never becomes a UrlBuilder host id
    (zksync used to disappear without a trace) and a derived host id without
    a display name (the configuration manager used to die on a bare
    ``KeyError``). Raises ``ValueError`` on any drift.
    """
    for alias, host in instance_hosts.items():
        if f'blockscout_{alias}' in hosts:
            continue
        if host in hosts.values():
            # Same instance under another alias (e.g. 'ethereum' → the 'eth'
            # host); nothing is lost.
            continue
        if alias in dropped_aliases:
            continue
        raise ValueError(
            f'BlockScout instance alias {alias!r} ({host}) is neither derived '
            f'into BLOCKSCOUT_HOSTS nor declared in DROPPED_INSTANCE_ALIASES'
        )

    stale_drops = sorted(
        alias
        for alias in dropped_aliases
        if f'blockscout_{alias}' in hosts or instance_hosts.get(alias) in hosts.values()
    )
    if stale_drops:
        raise ValueError(
            f'DROPPED_INSTANCE_ALIASES lists {stale_drops}, but those aliases '
            f'resolve to derived host ids — remove them from the dropped set'
        )

    unknown_drops = sorted(alias for alias in dropped_aliases if alias not in instance_hosts)
    if unknown_drops:
        raise ValueError(
            f'DROPPED_INSTANCE_ALIASES lists {unknown_drops}, which are not '
            f'BLOCKSCOUT_INSTANCE_HOSTS aliases'
        )

    unnamed = sorted(set(hosts) - set(display_names))
    if unnamed:
        raise ValueError(
            f'BlockScout host ids without a display name: {unnamed} — the '
            f'configuration manager would raise a bare KeyError on them'
        )

    stale_names = sorted(set(display_names) - set(hosts))
    if stale_names:
        raise ValueError(f'Display names declared for non-derived host ids: {stale_names}')


_validate_scanner_topology(
    BLOCKSCOUT_INSTANCE_HOSTS,
    BLOCKSCOUT_HOSTS,
    BLOCKSCOUT_DISPLAY_NAMES,
    DROPPED_INSTANCE_ALIASES,
)


@dataclass(frozen=True)
class ConfigDefinition:
    """Everything the configuration manager declares about one scanner id.

    One row per scanner id, in the module that owns scanner topology: the
    manager builds its ``ScannerConfig`` objects from these and adds only
    credential resolution. A scanner id therefore exists in both places or in
    neither — it can no longer be half-present.
    """

    name: str
    base_domain: str
    currency: str
    supported_networks: frozenset[str]
    requires_api_key: bool
    special_config: Mapping[str, Any]
    credential_family: str | None


def _build_config_definitions() -> dict[str, ConfigDefinition]:
    """Presentation rows joined with the network/currency/family views."""
    definitions: dict[str, ConfigDefinition] = {}
    for kind, profile in _URL_KIND_PROFILES.items():
        if profile.display_name is None or profile.base_domain is None:
            # A kind with no presentation row is not a config-manager scanner
            # (wemix/chiliz/mode: UrlBuilder-only).
            continue
        definitions[kind] = ConfigDefinition(
            name=profile.display_name,
            base_domain=profile.base_domain,
            currency=URL_BUILDER_CURRENCIES[kind],
            supported_networks=SCANNER_CONFIG_NETWORKS[kind],
            requires_api_key=profile.requires_api_key,
            special_config=dict(profile.special_config),
            credential_family=CONFIG_CREDENTIAL_FAMILY.get(kind),
        )

    # BlockScout instances: host, currency, served network and display name
    # all derive from the registry record, so a new instance registers once.
    for scanner_id, host in BLOCKSCOUT_HOSTS.items():
        definitions[scanner_id] = ConfigDefinition(
            name=BLOCKSCOUT_DISPLAY_NAMES[scanner_id],
            base_domain=host,
            currency=URL_BUILDER_CURRENCIES[scanner_id],
            supported_networks=SCANNER_CONFIG_NETWORKS[scanner_id],
            requires_api_key=False,
            special_config={'public_api': True},
            credential_family=CONFIG_CREDENTIAL_FAMILY.get(scanner_id),
        )
    return definitions


#: Config-manager scanner id → its one declared row. Read by
#: ``ConfigurationManager._init_builtin_scanners``.
SCANNER_CONFIG_DEFINITIONS: dict[str, ConfigDefinition] = _build_config_definitions()

#: Network names both BlockScout scanners declare as supported: the host table
#: minus the aliases deliberately not wired into UrlBuilder host ids. One
#: derivation for both legs, so a new instance registers for both at once and
#: neither leg can declare a network it cannot resolve to an instance. Both
#: dialect spellings of Ethereum mainnet ('eth' for v1, 'ethereum' for v2) are
#: in it — see :func:`_scanner_network_name`.
BLOCKSCOUT_SCANNER_NETWORKS: frozenset[str] = (
    frozenset(BLOCKSCOUT_INSTANCE_HOSTS) - DROPPED_INSTANCE_ALIASES
)


#: Network names the Etherscan v2 scanner declares. Derived from the record's
#: alias table so the scanner cannot advertise a name ``resolve_chain_id``
#: would not answer; every entry is a chain the keyless ``GET /v2/chainlist``
#: registry listed on 2026-09-11 (goerli and holesky are not in it — the live
#: endpoint answers them "Missing or unsupported chainid parameter").
#:
#: Mutable, and the scanner class binds this very object rather than a copy:
#: :func:`register_etherscan_chain` adds to it so an opt-in registry sync
#: (:mod:`aiochainscan.registry_sync`) reaches a scanner class that was already
#: imported. Nothing else may mutate it.
ETHERSCAN_SCANNER_NETWORKS: set[str] = set(SCANNER_RECORDS['etherscan'].network_aliases) | set(
    SCANNER_RECORDS['etherscan'].supported_networks or ()
)


def register_etherscan_chain(chain_id: int, name: str, *, aliases: Sequence[str] = ()) -> bool:
    """Register a chain the Etherscan v2 endpoint serves, at runtime.

    The static tables are the shipped truth; this is the seam an opt-in
    registry sync writes through so a chain Etherscan added after the last
    release becomes constructible without one. Registration is additive and
    idempotent: a ``chain_id`` already known keeps its declared spelling, and a
    ``name`` already taken by a different chain is refused rather than
    silently repointed — a caller that resolved that alias must not start
    getting another chain's data.

    Returns:
        ``True`` when this call added the chain, ``False`` when it was already
        known (either id or name).
    """
    if chain_id in STANDARD_CHAINS:
        return False
    spellings = [name, *aliases]
    known = {alias for info in STANDARD_CHAINS.values() for alias in info['aliases']}
    if known.intersection(spellings):
        return False

    STANDARD_CHAINS[chain_id] = {
        'name': name,
        'aliases': list(dict.fromkeys(spellings)),
        'moralis_hex': hex(chain_id),
    }
    # Every v2 chain routes through the one unified endpoint, so each spelling
    # collapses to the 'main' config network exactly like the static entries.
    for spelling in spellings:
        SCANNER_NETWORK_ALIASES['etherscan'][spelling] = 'main'
        ETHERSCAN_SCANNER_NETWORKS.add(spelling)
    return True


def get_url_builder_profile(api_kind: str, network: str) -> dict[str, str | None]:
    """Resolve URL builder profile for ``(api_kind, network)``.

    Returns keys:
    - ``base_url``
    - ``api_url``
    - ``currency``
    - ``auth_mode``: ``header`` or ``query``
    - ``chainid``: optional

    Static per-kind data comes from :data:`_URL_KIND_PROFILES`. Three outputs
    stay computed because they are derived from the network, not from data:
    the Etherscan V2 unified endpoint (one pair of URLs for the whole
    family), the BlockScout instance hosts, and NodeReal's JSON-RPC dialect
    (testnet/main RPC base and a chain id read off the 'bsc' row).
    """

    kind = api_kind.lower().strip()
    net = network.lower().strip()

    if kind not in URL_BUILDER_CURRENCIES:
        supported = ', '.join(sorted(URL_BUILDER_CURRENCIES))
        raise ValueError(f'Incorrect api_kind {kind!r}, supported only: {supported}')

    currency = URL_BUILDER_CURRENCIES[kind]
    chainid = URL_BUILDER_CHAIN_IDS.get((kind, net))

    profile = _URL_KIND_PROFILES.get(kind)

    # Etherscan V2 family: one unified endpoint, every request routed by
    # chainid (kind membership declared per profile row).
    if profile is not None and profile.v2_query_auth:
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

    # Remaining v1-style explorers: static per-kind domains, query auth.
    if profile is not None and profile.base_url is not None:
        base_url, api_url = profile.base_url, profile.api_url
        if profile.testnet_base_url is not None and net in {'test', 'testnet'}:
            base_url, api_url = profile.testnet_base_url, profile.testnet_api_url
        return {
            'base_url': base_url,
            'api_url': api_url,
            'currency': currency,
            'auth_mode': 'query',
            'chainid': chainid,
        }

    raise ValueError(f'Unsupported api_kind for url profile: {kind!r}')


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


# ---------------------------------------------------------------------------
# Scanner target resolution — the single resolution point behind
# ChainscanClient.from_config
# ---------------------------------------------------------------------------
# The scanner lookup tables this section reads (DEFAULT_SCANNER_VERSIONS,
# SCANNER_CONFIG_IDS, BLOCKSCOUT_CONFIG_IDS, SCANNER_CONFIG_NETWORKS,
# SCANNER_NETWORK_ALIASES, SCANNER_API_KINDS, CUSTOM_BASE_URL_SCANNERS) are
# derived from SCANNER_RECORDS at the top of this module.

# Network label used for custom base_url configurations: the chain is served
# by a user-provided instance, not by a registry deployment.
CUSTOM_NETWORK_LABEL = 'custom'


def _resolve_scanner_identity(scanner: str, scanner_version: str | None) -> tuple[str, str]:
    """Apply version defaulting and the ``blockscout_v2`` public alias.

    'blockscout_v2' is a public alias for the ``('blockscout', 'v2')`` pair —
    an explicit version never downgrades it (a single v2 entry point). Every
    other scanner name passes through with its defaulted version ('v2' for
    the registry-declared default family, 'v1' otherwise). Shared by both
    resolution branches (alias and custom base URL) — the rename/default
    logic lives exactly once.
    """
    version = (
        scanner_version
        if scanner_version is not None
        else DEFAULT_SCANNER_VERSIONS.get(scanner, 'v1')
    )
    if scanner == 'blockscout_v2':
        return 'blockscout', 'v2'
    return scanner, version


def _validate_config_network(scanner_id: str, config_network: str) -> None:
    """Apply the registry's network-validity oracle for ``scanner_id``.

    Runs for every construction, whatever the key source: an explicit
    ``api_key`` skips the credential lookup, never the oracle. Ids unknown to
    :data:`SCANNER_CONFIG_NETWORKS` — dynamically registered scanners — have no
    oracle here and are left to the scanner class.
    """
    supported = SCANNER_CONFIG_NETWORKS.get(scanner_id)
    if supported is not None and config_network not in supported:
        display_name = get_config_manager().get_scanner_config(scanner_id).name
        raise ValueError(
            f'Network "{config_network}" not supported by {display_name}. '
            f'Available networks: {", ".join(sorted(supported))}'
        )


def _lookup_api_key(scanner_id: str) -> str:
    """Resolve the credential for ``scanner_id`` from the configuration manager.

    The configuration manager owns credentials only (env vars / ``.env`` /
    config files); network validity is :func:`_validate_config_network`.
    """
    return get_config_manager().get_api_key(scanner_id)


@dataclass(frozen=True)
class ScannerTarget:
    """Fully resolved construction target for ``ChainscanClient``.

    Carries exactly the values the scanner stack consumes: ``scanner_name`` /
    ``scanner_version`` select the ``Scanner`` class, ``api_kind`` +
    ``url_network`` select the UrlBuilder profile (``url_network`` is the
    profile-dialect network name — ``'main'`` for Ethereum mainnet, the
    canonical registry chain name otherwise), ``scanner_network`` is the
    scanner-dialect network name the ``Scanner`` instance is constructed
    with (BlockScout v1 says ``'eth'`` for Ethereum mainnet, Etherscan says
    ``'main'``), ``network`` is the canonical network name, ``api_key`` the
    resolved credential (``''`` when the scanner needs none), ``chain_id``
    the numeric chain identifier (``None`` for custom base URLs without an
    ``expected_chain_id`` — unknown until the instance is probed),
    ``expected_chain_id`` the caller's chain expectation (validated lazily
    before the first request), and ``base_url`` an optional custom instance
    root overriding the registry.

    Resolution ownership: :func:`resolve_scanner_target` is the single owner
    of chain-id, UrlBuilder-network and scanner-network resolution.
    ``ChainscanClient`` and :class:`~aiochainscan.scanners.base.Scanner` trust
    this object and never re-derive any of them (the Scanner's registry
    fallback serves direct scanner construction only, never the client path).
    """

    scanner_name: str
    scanner_version: str
    network: str
    api_kind: str
    api_key: str
    chain_id: int | None
    url_network: str
    scanner_network: str
    base_url: str | None = None
    expected_chain_id: int | None = None


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
    normalization, UrlBuilder ``api_kind`` mapping, scanner-dialect network
    naming (``ScannerTarget.scanner_network``) and the api-key default
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

    # Version defaulting + the blockscout_v2 alias (single helper, both branches)
    actual_scanner_name, scanner_version = _resolve_scanner_identity(scanner, scanner_version)

    # Canonical chain resolution — raises ValueError for unknown chains
    chain_id = resolve_chain_id(network)

    # Canonical network name: ints resolve via the registry, strings are preserved
    canonical_name = get_chain_name(chain_id)
    network_str = canonical_name if isinstance(network, int) else str(network)

    # Normalize network aliases for configuration lookup only.
    # The alias table is keyed by canonical chain names, so the lookup runs on
    # the canonical name: one chain must resolve to one target however the
    # caller spells it ('bnb', 'binance' and 'bsc' are the same chain for the
    # same scanner — the raw-spelling lookup used to let 'bsc' construct while
    # 'bnb' died at scanner construction). Dynamically registered scanners
    # have no registry dialect; their spelling passes through untouched.
    config_network = network_str  # Preserve original for the client property
    aliases = SCANNER_NETWORK_ALIASES.get(scanner)
    if aliases is not None:
        config_network = aliases.get(canonical_name, canonical_name)

    # Configuration-manager scanner id (BlockScout's id depends on the
    # normalized network, so aliases must be resolved first).
    if scanner == 'blockscout':
        scanner_id = BLOCKSCOUT_CONFIG_IDS.get(config_network, f'blockscout_{config_network}')
    else:
        scanner_id = SCANNER_CONFIG_IDS.get(scanner, scanner)

    # Network validity is a registry fact, so it is checked before the key is
    # resolved and regardless of where the key comes from; the configuration
    # manager is a credential store, not a network oracle.
    _validate_config_network(scanner_id, config_network)

    if scanner == 'blockscout_v2':
        resolved_api_key = ''  # BlockScout V2 doesn't require API key
    elif api_key is not None:
        resolved_api_key = api_key
    else:
        resolved_api_key = _lookup_api_key(scanner_id)

    # UrlBuilder api_kind (BlockScout v1 uses the network-specific scanner id;
    # the v2 leg shares that per-network mapping so its UrlBuilder profile —
    # and with it ``client.currency`` — reflects the served chain instead of
    # the family's Ethereum default; requests are unaffected because V2 builds
    # every URL from the scanner's own base URL, never from the profile).
    if scanner == 'blockscout':
        api_kind = scanner_id
    elif scanner == 'blockscout_v2':
        candidate = BLOCKSCOUT_CONFIG_IDS.get(config_network, f'blockscout_{config_network}')
        api_kind = candidate if candidate in URL_BUILDER_CURRENCIES else 'blockscout_eth'
    else:
        api_kind = SCANNER_API_KINDS.get(scanner, scanner)

    # UrlBuilder network name, resolved exactly once on the whole
    # construction path — THIS resolver owns it (the client and the Scanner
    # trust the target): the canonical registry chain name, except Ethereum
    # mainnet, whose UrlBuilder dialect name is 'main'.
    url_network = 'main' if canonical_name == 'ethereum' else canonical_name

    # Scanner-dialect network name for the Scanner instance — same ownership
    # (the client used to re-derive this from the target; the target now
    # carries it as a field). Derived from the canonical chain name, not the
    # caller's spelling: the dialect name is a fact about the chain, so every
    # declared alias of a constructible chain constructs ('bnb' used to reach
    # etherscan v2 un-normalized and fail its supported-networks check while
    # 'bsc' constructed).
    scanner_network = _scanner_network_name(actual_scanner_name, scanner_version, canonical_name)

    return ScannerTarget(
        scanner_name=actual_scanner_name,
        scanner_version=scanner_version,
        network=network_str,
        api_kind=api_kind,
        api_key=resolved_api_key,
        chain_id=chain_id,
        url_network=url_network,
        scanner_network=scanner_network,
        expected_chain_id=expected_chain_id,
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

    # Version defaulting + the blockscout_v2 alias (single helper, both branches)
    actual_scanner_name, scanner_version = _resolve_scanner_identity(scanner, scanner_version)

    resolved_api_key = ''
    if actual_scanner_name == 'etherscan':
        if expected_chain_id is None:
            raise ValueError(
                'expected_chain_id is required for etherscan with a custom base_url: '
                'the V2 multichain API routes every request by chainid'
            )
        # Credential lookup for the unified Etherscan endpoint
        resolved_api_key = api_key if api_key is not None else _lookup_api_key('eth')

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
        url_network=CUSTOM_NETWORK_LABEL,
        scanner_network=CUSTOM_NETWORK_LABEL,
        expected_chain_id=expected_chain_id,
        base_url=base_url,
    )


def _scanner_network_name(scanner_name: str, scanner_version: str, network: str) -> str:
    """Map the unified network name to the scanner-specific network name.

    Resolution-private: :func:`resolve_scanner_target` computes this once and
    carries the result on ``ScannerTarget.scanner_network`` — the client and
    the Scanner trust the target and never re-derive it.

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
