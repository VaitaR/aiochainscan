"""Derived registry views — the per-scanner tables built from the records.

Everything here is derived at import time from
:mod:`aiochainscan.registry.data` and proven mutually consistent by
:func:`_validate_scanner_topology`. This module also owns the ONE runtime
mutation seam (:func:`register_etherscan_chain`) and the configuration
manager's presentation rows (``ConfigDefinition`` /
``SCANNER_CONFIG_DEFINITIONS``). It must never import
:mod:`aiochainscan.config`: the configuration manager imports
``SCANNER_CONFIG_DEFINITIONS`` from here at module level, and keeping this
edge one-way is what structurally killed the old registry/config circular
import.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .data import _URL_KIND_PROFILES, SCANNER_RECORDS, STANDARD_CHAINS, _blockscout_record

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

#: Config dialects the Etherscan v2 endpoint serves — the etherscan record's
#: alias-table targets. The alias table is the ONE declared source of the
#: scanner's network surface: its keys are the served spellings, its values
#: the dialects they collapse to, and everything else about the surface
#: (this set and :data:`ETHERSCAN_SCANNER_NETWORKS`) derives from it, the
#: static counterpart of what :func:`register_etherscan_chain` writes at
#: runtime.
ETHERSCAN_CONFIG_NETWORKS: frozenset[str] = frozenset(
    SCANNER_RECORDS['etherscan'].network_aliases.values()
)

# Networks each configuration-manager scanner id serves, in the config
# lookup dialect ('main'/'test'-style names, not registry chain names).
# Single source of the network-validity oracle for client construction
# (:func:`resolve_scanner_target`); the configuration manager derives its
# builtin ``supported_networks`` from this table instead of mirroring it.
# Derived from three views: the per-kind profiles (Etherscan-family config
# ids), the scanner records ('nodereal' owns its networks; the Etherscan
# dialects derive from its alias table, see ETHERSCAN_CONFIG_NETWORKS) and
# the BlockScout host ids (each serves exactly its host suffix, so a new
# instance registers once for both).
SCANNER_CONFIG_NETWORKS: dict[str, frozenset[str]] = {
    **{
        kind: networks
        for kind, profile in _URL_KIND_PROFILES.items()
        if (networks := profile.config_networks) is not None
    },
    # The Etherscan record declares no supported_networks: its config
    # dialects are the alias table's targets — exactly what the collapse
    # rule in :func:`resolve_scanner_target` (``aliases.get(canonical_name,
    # canonical_name)``) can produce for a chain in the surface.
    'eth': ETHERSCAN_CONFIG_NETWORKS,
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
#: in it — the wire spellings each scanner class declares for itself
#: (``NETWORK_NAME_DIALECT`` on ``BlockScoutV1`` / ``BlockScoutV2Scanner``).
BLOCKSCOUT_SCANNER_NETWORKS: frozenset[str] = (
    frozenset(BLOCKSCOUT_INSTANCE_HOSTS) - DROPPED_INSTANCE_ALIASES
)


#: Network names the Etherscan v2 scanner declares. Derived from the record's
#: alias table — the ONE declared source of the surface: the keys are the
#: served spellings, the targets the config dialects (so 'main' and the
#: self-collapsing 'sepolia' enter through the values). The scanner cannot
#: advertise a name ``resolve_chain_id`` would not answer, and every entry is
#: a chain the keyless ``GET /v2/chainlist`` registry listed on 2026-09-11
#: (goerli and holesky are not in it — the live endpoint answers them
#: "Missing or unsupported chainid parameter").
#:
#: Mutable, and the scanner class binds this very object rather than a copy:
#: :func:`register_etherscan_chain` adds to it so an opt-in registry sync
#: (:mod:`aiochainscan.registry_sync`) reaches a scanner class that was already
#: imported. Nothing else may mutate it.
ETHERSCAN_SCANNER_NETWORKS: set[str] = set(SCANNER_RECORDS['etherscan'].network_aliases) | set(
    ETHERSCAN_CONFIG_NETWORKS
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
