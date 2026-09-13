"""Chain Registry - unified chain information and provider mappings.

The registry lives in the :mod:`aiochainscan.registry` package, split by
role: :mod:`registry.data` holds the static measured chain/scanner tables and
their read accessors, :mod:`registry.views` derives the per-scanner view
tables and owns topology validation plus the runtime mutation seam, and
:mod:`registry.resolve` turns ``(scanner, network, api_key)`` into a
:class:`~aiochainscan.registry.resolve.ScannerTarget`. Every name the former
single-module registry defined is re-exported here unchanged, so existing
``aiochainscan.chain_registry`` imports keep working.
"""

from .registry.data import (
    _URL_KIND_PROFILES as _URL_KIND_PROFILES,
)
from .registry.data import (
    SCANNER_RECORDS as SCANNER_RECORDS,
)
from .registry.data import (
    STANDARD_CHAINS as STANDARD_CHAINS,
)
from .registry.data import (
    URL_BUILDER_CHAIN_IDS as URL_BUILDER_CHAIN_IDS,
)
from .registry.data import (
    KindProfile as KindProfile,
)
from .registry.data import (
    ScannerRecord as ScannerRecord,
)
from .registry.data import (
    _blockscout_record as _blockscout_record,
)
from .registry.data import (
    get_blockscout_instance as get_blockscout_instance,
)
from .registry.data import (
    get_chain_aliases as get_chain_aliases,
)
from .registry.data import (
    get_chain_info as get_chain_info,
)
from .registry.data import (
    get_chain_name as get_chain_name,
)
from .registry.data import (
    get_moralis_hex as get_moralis_hex,
)
from .registry.data import (
    list_supported_chains as list_supported_chains,
)
from .registry.data import (
    resolve_chain_id as resolve_chain_id,
)
from .registry.resolve import (
    CUSTOM_NETWORK_LABEL as CUSTOM_NETWORK_LABEL,
)
from .registry.resolve import (
    ScannerTarget as ScannerTarget,
)
from .registry.resolve import (
    _lookup_api_key as _lookup_api_key,
)
from .registry.resolve import (
    _resolve_custom_base_url_target as _resolve_custom_base_url_target,
)
from .registry.resolve import (
    _resolve_scanner_identity as _resolve_scanner_identity,
)
from .registry.resolve import (
    _scanner_network_name as _scanner_network_name,
)
from .registry.resolve import (
    _validate_config_network as _validate_config_network,
)
from .registry.resolve import (
    get_url_builder_profile as get_url_builder_profile,
)
from .registry.resolve import (
    resolve_scanner_target as resolve_scanner_target,
)
from .registry.views import (
    BLOCKSCOUT_CONFIG_IDS as BLOCKSCOUT_CONFIG_IDS,
)
from .registry.views import (
    BLOCKSCOUT_DISPLAY_NAMES as BLOCKSCOUT_DISPLAY_NAMES,
)
from .registry.views import (
    BLOCKSCOUT_HOSTS as BLOCKSCOUT_HOSTS,
)
from .registry.views import (
    BLOCKSCOUT_INSTANCE_HOSTS as BLOCKSCOUT_INSTANCE_HOSTS,
)
from .registry.views import (
    BLOCKSCOUT_SCANNER_NETWORKS as BLOCKSCOUT_SCANNER_NETWORKS,
)
from .registry.views import (
    CONFIG_CREDENTIAL_FAMILY as CONFIG_CREDENTIAL_FAMILY,
)
from .registry.views import (
    CUSTOM_BASE_URL_SCANNERS as CUSTOM_BASE_URL_SCANNERS,
)
from .registry.views import (
    DEFAULT_SCANNER_VERSIONS as DEFAULT_SCANNER_VERSIONS,
)
from .registry.views import (
    DROPPED_INSTANCE_ALIASES as DROPPED_INSTANCE_ALIASES,
)
from .registry.views import (
    ETHERSCAN_SCANNER_NETWORKS as ETHERSCAN_SCANNER_NETWORKS,
)
from .registry.views import (
    SCANNER_API_KINDS as SCANNER_API_KINDS,
)
from .registry.views import (
    SCANNER_CONFIG_DEFINITIONS as SCANNER_CONFIG_DEFINITIONS,
)
from .registry.views import (
    SCANNER_CONFIG_IDS as SCANNER_CONFIG_IDS,
)
from .registry.views import (
    SCANNER_CONFIG_NETWORKS as SCANNER_CONFIG_NETWORKS,
)
from .registry.views import (
    SCANNER_NETWORK_ALIASES as SCANNER_NETWORK_ALIASES,
)
from .registry.views import (
    URL_BUILDER_CURRENCIES as URL_BUILDER_CURRENCIES,
)
from .registry.views import (
    V2_QUERY_AUTH_API_KINDS as V2_QUERY_AUTH_API_KINDS,
)
from .registry.views import (
    ConfigDefinition as ConfigDefinition,
)
from .registry.views import (
    _build_config_definitions as _build_config_definitions,
)
from .registry.views import (
    _validate_scanner_topology as _validate_scanner_topology,
)
from .registry.views import (
    config_id_for_scanner as config_id_for_scanner,
)
from .registry.views import (
    register_etherscan_chain as register_etherscan_chain,
)
