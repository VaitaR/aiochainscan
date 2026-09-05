"""
Chain Registry - unified chain information and provider mappings.
"""

import warnings
from collections.abc import Mapping
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

    def __post_init__(self) -> None:
        if (self.testnet_base_url is None) != (self.testnet_api_url is None):
            raise ValueError('KindProfile: testnet_base_url and testnet_api_url are a pair')


_URL_KIND_PROFILES: dict[str, KindProfile] = {
    # Etherscan V2 family — one unified endpoint, chainid-routed, query auth.
    'eth': KindProfile(currency='ETH', v2_query_auth=True),
    'bsc': KindProfile(
        currency='BNB',
        v2_query_auth=True,
        config_networks=frozenset({'main', 'test'}),
        credential_family='eth',
    ),
    'polygon': KindProfile(
        currency='MATIC',
        v2_query_auth=True,
        config_networks=frozenset({'main', 'mumbai', 'test'}),
        credential_family='eth',
    ),
    'optimism': KindProfile(
        currency='ETH',
        v2_query_auth=True,
        config_networks=frozenset({'main', 'goerli', 'test'}),
        credential_family='eth',
    ),
    'arbitrum': KindProfile(
        currency='ETH',
        v2_query_auth=True,
        config_networks=frozenset({'main', 'nova', 'goerli', 'test'}),
        credential_family='eth',
    ),
    'base': KindProfile(
        currency='BASE',
        v2_query_auth=True,
        config_networks=frozenset({'main', 'goerli', 'sepolia'}),
        credential_family='eth',
    ),
    # v1-style per-explorer domains, query auth.
    'fantom': KindProfile(
        currency='FTM',
        base_url='https://ftmscan.com',
        api_url='https://api.ftmscan.com/api',
        testnet_base_url='https://testnet.ftmscan.com',
        testnet_api_url='https://api-testnet.ftmscan.com/api',
        config_networks=frozenset({'main', 'test'}),
    ),
    'gnosis': KindProfile(
        currency='GNO',
        base_url='https://gnosisscan.io',
        api_url='https://api.gnosisscan.io/api',
        config_networks=frozenset({'main', 'chiado'}),
    ),
    'flare': KindProfile(
        currency='FLR',
        base_url='https://flare.network',
        api_url='https://flare-explorer.flare.network/api',
        config_networks=frozenset({'main', 'test'}),
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
    ),
    'blast': KindProfile(
        currency='BLAST',
        base_url='https://blastscan.io',
        api_url='https://api.blastscan.io/api',
        config_networks=frozenset({'main', 'sepolia'}),
    ),
    # NodeReal: currency and config networks here; URLs/chain id are dialect
    # (computed in get_url_builder_profile).
    'nodereal': KindProfile(
        currency='BNB',
        config_networks=frozenset({'bsc', 'bsc-testnet'}),
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
        },
        # Config-dialect networks the V2 endpoint actually serves. Every
        # mainnet alias above collapses to 'main'; the testnets keep their own
        # names. ('test' is absent because no chain resolves under it here.)
        supported_networks=frozenset({'main', 'goerli', 'sepolia', 'holesky'}),
        custom_base_url=True,
    ),
    'blockscout': ScannerRecord(
        kind='blockscout',
        # Family owner: the per-instance topology both BlockScout legs serve.
        network_aliases={'ethereum': 'eth', 'main': 'eth'},
        instance_hosts={
            'eth': 'eth.blockscout.com',
            'ethereum': 'eth.blockscout.com',
            'sepolia': 'eth-sepolia.blockscout.com',
            'gnosis': 'gnosis.blockscout.com',
            'polygon': 'polygon.blockscout.com',
            'optimism': 'optimism.blockscout.com',
            'arbitrum': 'arbitrum.blockscout.com',
            'base': 'base.blockscout.com',
            'scroll': 'scroll.blockscout.com',
            'linea': 'linea.blockscout.com',
            'bsc': 'bsc.blockscout.com',
            'zksync': 'zksync.blockscout.com',
        },
        instance_currencies={
            'blockscout_eth': 'ETH',
            'blockscout_sepolia': 'ETH',
            'blockscout_gnosis': 'xDAI',
            'blockscout_polygon': 'MATIC',
            'blockscout_base': 'ETH',
            'blockscout_bsc': 'BNB',
            'blockscout_optimism': 'ETH',
            'blockscout_arbitrum': 'ETH',
            'blockscout_scroll': 'ETH',
            'blockscout_linea': 'ETH',
        },
        config_ids_by_network={
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
        },
        display_names={
            'blockscout_eth': 'BlockScout Ethereum',
            'blockscout_sepolia': 'BlockScout Sepolia',
            'blockscout_gnosis': 'BlockScout Gnosis',
            'blockscout_polygon': 'BlockScout Polygon',
            'blockscout_base': 'BlockScout Base',
            'blockscout_bsc': 'BlockScout BSC',
            'blockscout_optimism': 'BlockScout Optimism',
            'blockscout_arbitrum': 'BlockScout Arbitrum',
            'blockscout_scroll': 'BlockScout Scroll',
            'blockscout_linea': 'BlockScout Linea',
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
DROPPED_INSTANCE_ALIASES: frozenset[str] = frozenset({'zksync'})


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

#: Network names both BlockScout scanners declare as supported: the host table
#: minus the aliases deliberately not wired into UrlBuilder host ids. One
#: derivation for both legs, so a new instance registers for both at once and
#: neither leg can declare a network it cannot resolve to an instance. Both
#: dialect spellings of Ethereum mainnet ('eth' for v1, 'ethereum' for v2) are
#: in it — see :func:`_scanner_network_name`.
BLOCKSCOUT_SCANNER_NETWORKS: frozenset[str] = (
    frozenset(BLOCKSCOUT_INSTANCE_HOSTS) - DROPPED_INSTANCE_ALIASES
)


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

    # UrlBuilder api_kind (BlockScout v1 uses the network-specific scanner id)
    api_kind = scanner_id if scanner == 'blockscout' else SCANNER_API_KINDS.get(scanner, scanner)

    # UrlBuilder network name, resolved exactly once on the whole
    # construction path — THIS resolver owns it (the client and the Scanner
    # trust the target): the canonical registry chain name, except Ethereum
    # mainnet, whose UrlBuilder dialect name is 'main'.
    url_network = 'main' if canonical_name == 'ethereum' else canonical_name

    # Scanner-dialect network name for the Scanner instance — same ownership
    # (the client used to re-derive this from the target; the target now
    # carries it as a field).
    scanner_network = _scanner_network_name(actual_scanner_name, scanner_version, network_str)

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
