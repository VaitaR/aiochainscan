"""Scanner target resolution — the registry's resolution engine.

:func:`resolve_scanner_target` is the single resolution point behind
``ChainscanClient.from_config``: it turns ``(scanner, network, api_key)`` into
a frozen :class:`ScannerTarget`, owning version defaulting, the
``blockscout_v2`` rename, canonical network resolution, UrlBuilder profiles
and the api-key default. Unlike the views module, this one imports
:mod:`aiochainscan.config` (for :func:`get_config_manager`) — safe, because
config only imports the views module, never back.
"""

import warnings
from dataclasses import dataclass

from ..base_url import is_url_like, validate_base_url
from ..config import get_config_manager
from .data import _URL_KIND_PROFILES, URL_BUILDER_CHAIN_IDS, get_chain_name, resolve_chain_id
from .views import (
    BLOCKSCOUT_CONFIG_IDS,
    BLOCKSCOUT_HOSTS,
    CUSTOM_BASE_URL_SCANNERS,
    DEFAULT_SCANNER_VERSIONS,
    SCANNER_API_KINDS,
    SCANNER_CONFIG_IDS,
    SCANNER_CONFIG_NETWORKS,
    SCANNER_NETWORK_ALIASES,
    URL_BUILDER_CURRENCIES,
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


# ---------------------------------------------------------------------------
# Scanner target resolution — the single resolution point behind
# ChainscanClient.from_config
# ---------------------------------------------------------------------------
# The scanner lookup tables this section reads (DEFAULT_SCANNER_VERSIONS,
# SCANNER_CONFIG_IDS, BLOCKSCOUT_CONFIG_IDS, SCANNER_CONFIG_NETWORKS,
# SCANNER_NETWORK_ALIASES, SCANNER_API_KINDS, CUSTOM_BASE_URL_SCANNERS) are
# derived from SCANNER_RECORDS and imported here from the views module.

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
    scanner-dialect network name the ``Scanner`` instance is constructed with
    (asked of the scanner class — ``Scanner.dialect_network``; BlockScout v1
    says ``'eth'`` for Ethereum mainnet, Etherscan says ``'main'``),
    ``network`` is the canonical network name, ``api_key`` the
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
    # caller's spelling — the dialect name is a fact about the chain — and
    # ASKED of the scanner class rather than hardcoded here: the class that
    # validates the spelling (:meth:`Scanner.dialect_network` beside the
    # ``supported_networks`` check) is the one that declares it, so a name
    # cannot resolve in the registry and die at scanner construction.
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
    """Delegate the scanner-dialect question to the scanner class.

    Resolution-private: :func:`resolve_scanner_target` computes this once and
    carries the result on ``ScannerTarget.scanner_network`` — the client and
    the Scanner trust the target and never re-derive it.

    The dialect spelling is a fact about the scanner, declared on the scanner
    class (:meth:`Scanner.dialect_network` / ``NETWORK_NAME_DIALECT``) right
    beside the ``supported_networks`` check that validates it — the registry
    asks instead of owning an if-ladder per scanner, so the two answers can no
    longer drift (a name that resolved here but died in ``Scanner.__init__``).

    The scanners package is imported lazily, inside the call: the scanner
    modules import ``aiochainscan.chain_registry`` at module level (the
    chain-id fallback), so a module-level edge from this module back to
    ``aiochainscan.scanners`` would close a genuine import cycle. At call time
    both sides are fully loaded.

    A ``(name, version)`` pair no registered scanner class answers (unknown
    scanner names, explicit versions of no registered class) has no class to
    ask: the canonical name passes through unchanged, as the fall-through of
    the deleted registry-side ladder did.

    Args:
        scanner_name: Name of the scanner (e.g. 'etherscan', 'blockscout')
        scanner_version: Version of the scanner (e.g. 'v1', 'v2')
        network: Canonical network name (e.g. 'ethereum', 'polygon')

    Returns:
        Scanner-specific network name
    """
    from ..scanners import get_scanner_class

    try:
        scanner_cls = get_scanner_class(scanner_name, scanner_version)
    except ValueError:
        return network
    return scanner_cls.dialect_network(network)
