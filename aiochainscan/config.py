from __future__ import annotations

import copy
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, cast

# dotenv is optional - manual env file loading is implemented below

logger = logging.getLogger(__name__)


def credential_env_names(scanner_id: str, display_name: str | None = None) -> tuple[str, ...]:
    """Credential env-var candidates for *scanner_id*, in priority order.

    This function is the ONE statement of the priority order; every consumer
    (env-state lookup, ``os.environ`` lookup, suggestion text, the ``.env``
    template, and the V2-family fallback) derives its names from here, so the
    order can never drift between lookup and error text:

    1. ``{DISPLAY_NAME}_KEY`` — name-based, e.g. ``ETHERSCAN_KEY`` (skipped
       when the display name is unknown)
    2. ``{ID}_KEY`` — id-based, e.g. ``ETH_KEY`` (backward compatibility)
    3. ``{ID}_API_KEY`` — e.g. ``ETH_API_KEY``
    4. ``SCANNER_{ID}_KEY`` — generic prefix
    5. ``API_KEY_{ID}`` — generic suffix

    Args:
        scanner_id: Scanner identifier (e.g. ``'eth'``).
        display_name: Scanner display name (e.g. ``'Etherscan'``), uppercased
           with spaces replaced by underscores for the primary pattern.
           ``None`` means the name is unknown — the name-based candidate is
           omitted (e.g. lookups for ids that are not registered).

    Deduplicated, first spelling kept: a scanner whose display name equals its
    id (``nodereal``) would otherwise repeat ``NODEREAL_KEY``, which is
    harmless for a lookup but reads as a mistake in suggestion text and in
    ``list_all_configurations()``.
    """
    scanner_id_upper = scanner_id.upper()
    candidates: list[str] = []
    if display_name is not None:
        candidates.append(f'{display_name.upper().replace(" ", "_")}_KEY')
    candidates.extend(
        (
            f'{scanner_id_upper}_KEY',
            f'{scanner_id_upper}_API_KEY',
            f'SCANNER_{scanner_id_upper}_KEY',
            f'API_KEY_{scanner_id_upper}',
        )
    )
    return tuple(dict.fromkeys(candidates))


#: U+FFFD — the only way a decoded ``.env`` line can contain it is
#: ``errors='replace'`` on bytes that are not valid UTF-8.
_REPLACEMENT_CHAR = '\ufffd'


def _normalize_env_key(raw_key: str) -> str | None:
    """Normalize a ``.env`` key: trim whitespace and an optional ``export ``.

    The python-dotenv convention ``export KEY=val`` is accepted; a bare
    ``export=val`` keeps ``export`` as a genuine key (no separator follows).
    ``None`` means the line has no usable key.
    """
    key = raw_key.strip()
    if key.startswith('export') and len(key) > len('export') and key[len('export')] in (' ', '\t'):
        key = key[len('export') :].strip()
    return key or None


def _parse_env_value(raw_value: str) -> str:
    """Parse the value half of a ``.env`` line.

    A single- or double-quoted value is unquoted and a ``#`` inside it is
    data. An unquoted value stops at the first ``#`` (inline comment) and
    quotes are stripped as legacy spelling, not syntax — the pre-dialect
    parser's ``strip('"\\'')`` behaviour for malformed/unterminated input.
    """
    value = raw_value.strip()
    if value[:1] in ('"', "'"):
        quote = value[0]
        end = value.find(quote, 1)
        if end > 0:
            return value[1:end]
    return value.split('#', 1)[0].strip().strip('"\'')


def _coerce_networks_list(networks_any: Any, scanner_id: str) -> list[str]:
    """Validate a ``supported_networks`` declaration into a list of strings.

    A bare string is the classic silent corruption: ``set('main')`` happily
    becomes ``{'m', 'a', 'i', 'n'}``. A non-iterable would surface as a bare
    ``TypeError``. Both are configuration errors and raise ``ValueError``
    naming the scanner and the offending value.
    """
    if isinstance(networks_any, str | bytes):
        raise ValueError(
            f'Invalid scanner configuration for {scanner_id}: supported_networks '
            f'must be a list of network names, got the string {networks_any!r} '
            '(did you mean ["main"]?)'
        )
    try:
        networks = list(networks_any)
    except TypeError as exc:
        raise ValueError(
            f'Invalid scanner configuration for {scanner_id}: supported_networks '
            f'must be a list of network names, got {type(networks_any).__name__}: '
            f'{networks_any!r}'
        ) from exc
    for item in networks:
        if not isinstance(item, str):
            raise ValueError(
                f'Invalid scanner configuration for {scanner_id}: supported_networks '
                f'entries must be strings, got {type(item).__name__}: {item!r}'
            )
    return networks


@dataclass
class ScannerConfig:
    """Configuration for a blockchain scanner."""

    name: str
    base_domain: str
    currency: str
    supported_networks: set[str] = field(default_factory=set)
    requires_api_key: bool = True
    special_config: dict[str, Any] = field(default_factory=dict)
    #: The family config id whose credential is the fallback when this
    #: scanner's own key is absent. Builtin-only, derived from the registry's
    #: kind profiles (the Etherscan V2 family: one account serves several
    #: chains); dynamic registrations carry ``None``. Read by
    #: :meth:`ConfigurationManager.get_api_key`.
    credential_family: str | None = None
    api_key: str | None = field(default=None, init=False)


class ConfigurationManager:
    """
    Advanced configuration manager for blockchain scanners with lazy initialization.

    Features:
    - Lazy loading: Scanner configs loaded only when first accessed
    - Singleton pattern: Single instance shared across application
    - Automatic .env file loading (on first access)
    - JSON configuration support
    - Dynamic scanner registration
    - Environment variable fallbacks
    - Runtime configuration updates
    - Thread-safe initialization

    Performance Benefits:
    - Reduced import time by ~70%
    - Lower memory usage - only loads configs that are actually used
    - Faster startup for single-scanner applications
    """

    _instance: ClassVar[ConfigurationManager | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    # Instance attributes (declared for mypy, initialized in __new__)
    _initialized: bool
    _scanners: dict[str, ScannerConfig]
    _env_loaded: bool
    _builtin_loaded: bool
    _config_files_loaded: bool
    _env_state: dict[str, str]
    config_dir: Path

    def __new__(cls, config_dir: Path | None = None) -> ConfigurationManager:
        """Thread-safe singleton pattern: return same instance on subsequent calls.

        The manager is process-wide configuration by design (the machine-level
        ``~/.aiochainscan/.env`` is read for every cwd), so a second
        construction cannot rebind it to another directory. It warns instead:
        silently keeping the first directory while the caller believes they
        configured another one is exactly how an embedder ends up reading a
        foreign ``.env``/JSON. ``reset_instance()`` (fresh binding) or
        ``reload(config_dir)`` (rebind in place) are the supported ways to
        change directories; a re-init with the SAME directory stays silent.
        """
        requested = config_dir if config_dir is not None else Path.cwd()
        if cls._instance is not None:
            existing = cls._instance
            if cls._differs(existing.config_dir, requested):
                logger.warning(
                    'ConfigurationManager is a process-wide singleton already '
                    f'bound to {existing.config_dir}; ignoring config_dir={requested}. '
                    'Use ConfigurationManager.reset_instance() to rebind.'
                )
            return cls._instance
        with cls._lock:
            # Double-check locking pattern for thread safety
            if cls._instance is None:
                instance = super().__new__(cls)
                # Initialize instance attributes here to avoid __init__ race conditions
                instance._initialized = False
                instance._scanners = {}
                instance._env_loaded = False
                instance._builtin_loaded = False
                instance._config_files_loaded = False
                instance._env_state = {}
                instance.config_dir = requested
                cls._instance = instance
        return cls._instance

    @staticmethod
    def _differs(bound: Path, requested: Path) -> bool:
        """Whether *requested* names a different directory than *bound*.

        Compares resolved paths so spelling differences (relative vs absolute,
        symlinked temp dirs) are not false alarms; if resolution fails the
        paths are treated as different — warning is the safe direction.
        """
        if bound == requested:
            return False
        try:
            return bound.resolve() != requested.resolve()
        except OSError:  # pragma: no cover - pathological paths
            return True

    def __init__(self, config_dir: Path | None = None) -> None:
        """
        Initialize configuration manager with lazy loading.

        Args:
            config_dir: Directory to search for config files (default: current working directory)

        Note:
            Actual initialization is deferred until first config access.
            This constructor can be called multiple times but only initializes once.
            All heavy lifting (loading env, builtin scanners, config files) happens lazily.
        """
        # All initialization is done in __new__ to ensure thread safety
        # This method exists only for API compatibility
        pass

    @classmethod
    def create_isolated(cls, config_dir: Path | None = None) -> ConfigurationManager:
        """An independent manager that neither reads nor becomes the shared one.

        The shared instance stays the public default (see
        ``docs/adr/0002-configuration-manager-stays-a-singleton.md``): process-wide
        configuration is the intended contract, and construction returning the
        shared instance is public behaviour. This is the escape hatch for
        callers that need a hermetic manager — tests above all, which
        otherwise reset the singleton before and after every case and leak
        state across modules when one forgets.
        """
        instance = super().__new__(cls)
        instance._initialized = False
        instance._scanners = {}
        instance._env_loaded = False
        instance._builtin_loaded = False
        instance._config_files_loaded = False
        instance._env_state = {}
        instance.config_dir = config_dir if config_dir is not None else Path.cwd()
        return instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for testing or reconfiguration)."""
        global _config_manager_instance
        with cls._lock:
            cls._instance = None
            _config_manager_instance = None

    def reload(self, config_dir: Path | None = None) -> None:
        """
        Force reload of all configurations.

        Useful for runtime configuration updates without restarting the application.

        Args:
            config_dir: Optional new config directory to use
        """
        with self._lock:
            if config_dir is not None:
                self.config_dir = config_dir
            self._scanners.clear()
            self._env_state.clear()
            self._env_loaded = False
            self._builtin_loaded = False
            self._config_files_loaded = False

    def _ensure_initialized(self) -> None:
        """
        Ensure configuration is loaded. Called lazily on first access.

        This method loads all configuration only when needed, not at import time.
        Thread-safe via double-check locking pattern.
        """
        # Fast path: already loaded
        if self._builtin_loaded and self._config_files_loaded:
            return

        with self._lock:
            # Double-check after acquiring lock
            if not self._env_loaded:
                self._load_env_files()
                self._env_loaded = True

            if not self._builtin_loaded:
                self._init_builtin_scanners()
                self._builtin_loaded = True

            if not self._config_files_loaded:
                self._load_config_files()
                self._config_files_loaded = True
                # Load API keys after config files (they might define keys)
                self._load_api_keys()

    def _ensure_env_loaded(self) -> None:
        """Load the ``.env`` files once, without the rest of the initialization.

        Credential resolution reads ``_env_state``, so any path that resolves a
        key before full initialization must come through here — otherwise the
        ".env is loaded on first access" contract holds only for whoever
        happens to trigger :meth:`_ensure_initialized` first.
        """
        if self._env_loaded:
            return
        with self._lock:
            if not self._env_loaded:
                self._load_env_files()
                self._env_loaded = True

    def _get_scanner_config_lazy(self, scanner_id: str) -> ScannerConfig | None:
        """
        Get scanner config with lazy loading for individual scanners.

        This enables loading only the specific scanner needed without
        initializing all builtin scanners first.

        Returns None if scanner_id is not a known builtin scanner.
        """
        # Check if already loaded
        if scanner_id in self._scanners:
            return self._scanners[scanner_id]

        # Ensure env is loaded for API keys
        self._ensure_env_loaded()

        # Try to load just this one scanner from builtins
        builtin_config = self._get_builtin_scanner(scanner_id)
        if builtin_config is not None:
            with self._lock:
                if scanner_id not in self._scanners:
                    self._scanners[scanner_id] = builtin_config
                    # Same priority ladder as _load_api_keys (the full path):
                    # ``.env`` state first, then os.environ overriding it. The
                    # env_state leg is not optional — this lazy path serves
                    # every builtin scanner, so without it a key that exists
                    # only in a ``.env`` file is silently ignored and the
                    # scanner reports "API key required".
                    env_key = self._resolve_env_state_key(scanner_id)
                    if env_key:
                        self._scanners[scanner_id].api_key = env_key
                    api_key = self._get_api_key_for_scanner(scanner_id)
                    if api_key:
                        self._scanners[scanner_id].api_key = api_key
            return self._scanners[scanner_id]

        return None

    def _get_builtin_scanner(self, scanner_id: str) -> ScannerConfig | None:
        """Get a single builtin scanner config without loading all scanners."""
        builtin_scanners = self._get_builtin_scanner_definitions()
        return builtin_scanners.get(scanner_id)

    def _init_builtin_scanners(self) -> None:
        """Initialize built-in scanner configurations."""
        builtin_scanners = self._get_builtin_scanner_definitions()
        self._scanners.update(builtin_scanners)

    def _get_builtin_scanner_definitions(self) -> dict[str, ScannerConfig]:
        """Return all builtin scanner definitions (factory method, no side effects).

        This module owns credentials and env resolution only. Every declared
        fact about a scanner id — display name, base domain, currency,
        supported networks, key requirement, special config and V2
        credential-family membership — is ONE row in
        :mod:`aiochainscan.chain_registry`
        (``SCANNER_CONFIG_DEFINITIONS``), so a scanner id cannot exist in the
        registry without a config entry or the reverse. The registry import is
        lazy because chain_registry imports this module for key lookups; at
        call time both modules are fully initialized.
        """
        from .chain_registry import SCANNER_CONFIG_DEFINITIONS

        return {
            scanner_id: ScannerConfig(
                name=row.name,
                base_domain=row.base_domain,
                currency=row.currency,
                supported_networks=set(row.supported_networks),
                requires_api_key=row.requires_api_key,
                special_config=dict(row.special_config),
                credential_family=row.credential_family,
            )
            for scanner_id, row in SCANNER_CONFIG_DEFINITIONS.items()
        }

    def _load_env_files(self) -> None:
        """Load environment variables from .env files.

        Parsing is first-setter-wins, so the load order IS the precedence:
        ``./.env.local`` > ``./.env`` > ``~/.aiochainscan/.env`` — the
        universal dotenv convention that the local, untracked file carries
        the more specific overrides. ``os.environ`` outranks every file
        regardless of order (enforced per key in :meth:`_load_env_file`).
        """
        env_files = [
            self.config_dir / '.env.local',
            self.config_dir / '.env',
            Path.home() / '.aiochainscan' / '.env',
        ]

        for env_file in env_files:
            if env_file.exists():
                self._load_env_file(env_file)
                logger.debug(f'Loaded environment from {env_file}')

    def _load_env_file(self, env_file: Path) -> None:
        """Load variables from a specific .env file into internal state.

        Variables are stored in ``_env_state`` so that the host process's
        ``os.environ`` is never mutated. Only the first setter of a key wins
        (``os.environ`` outranks every file).

        Dialect (python-dotenv conventions, kept deliberately small): an
        optional ``export `` key prefix, single- or double-quoted values (a
        ``#`` inside quotes is data), an unquoted inline ``#`` comment, CRLF
        line endings and a UTF-8 BOM.

        Like the JSON config loader, this is warn-and-continue on corruption:
        bytes that are not valid UTF-8 produce one warning naming the file
        and their lines are skipped — never stored half-decoded, since a
        corrupted credential is worse than a missing one — while the file's
        remaining lines still load.
        """
        skipped: int = 0
        try:
            with open(env_file, encoding='utf-8-sig', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key_part, _, raw_value = line.partition('=')
                    key = _normalize_env_key(key_part)
                    if key is None:
                        continue
                    value = _parse_env_value(raw_value)
                    if _REPLACEMENT_CHAR in key or _REPLACEMENT_CHAR in value:
                        # U+FFFD can only come from errors='replace' here:
                        # the line held bytes that are not valid UTF-8.
                        skipped += 1
                        continue
                    if key not in self._env_state and key not in os.environ:
                        self._env_state[key] = value
        except OSError as e:
            logger.warning(f'Failed to load {env_file}: {e}')
            return
        if skipped:
            logger.warning(
                f'{env_file}: {skipped} line(s) contained bytes that are not '
                f'valid UTF-8 and were skipped'
            )

    def _load_config_files(self) -> None:
        """Load scanner configurations from JSON files."""
        config_files = [
            self.config_dir / 'aiochainscan.json',
            self.config_dir / 'scanners.json',
            Path.home() / '.aiochainscan' / 'config.json',
        ]

        for config_file in config_files:
            if config_file.exists():
                self._load_config_file(config_file)
                logger.debug(f'Loaded configuration from {config_file}')

    def _load_config_file(self, config_file: Path) -> None:
        """Load configuration from a JSON file."""
        try:
            with open(config_file) as f:
                config_data = cast(dict[str, Any], json.load(f))

            # Load custom scanners
            if 'scanners' in config_data:
                scanners_section = cast(dict[str, dict[str, Any]], config_data['scanners'])
                for scanner_id, scanner_data in scanners_section.items():
                    self.register_scanner(scanner_id, scanner_data)

            # Load API keys
            if 'api_keys' in config_data:
                api_keys = cast(dict[str, str], config_data['api_keys'])
                unknown = [key for key in api_keys if key not in self._scanners]
                for scanner_id, api_key in api_keys.items():
                    if scanner_id in self._scanners:
                        self._scanners[scanner_id].api_key = api_key
                if unknown:
                    # A key bound to a typo'd id ('etherscan' instead of 'eth')
                    # must not vanish silently — the scanner would later fail
                    # with "API key required" and no hint why.
                    logger.warning(
                        f'{config_file}: ignoring api_keys for unknown scanner '
                        f'id(s): {", ".join(sorted(unknown))}'
                    )

        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            # ValueError: register_scanner's input validation (malformed
            # supported_networks etc.) — one bad entry must not crash client
            # construction, matching this loader's warn-and-continue contract.
            logger.warning(f'Failed to load config from {config_file}: {e}')

    def _load_api_keys(self) -> None:
        """Load API keys from various sources with priority order."""
        for scanner_id, scanner_config in self._scanners.items():
            # First: apply keys loaded from .env files (lower priority)
            env_key = self._resolve_env_state_key(scanner_id)
            if env_key and not scanner_config.api_key:
                scanner_config.api_key = env_key
            # Then: check os.environ (higher priority, overrides .env)
            api_key = self._get_api_key_for_scanner(scanner_id)
            if api_key:
                scanner_config.api_key = api_key

    def _resolve_env_state_key(self, scanner_id: str) -> str | None:
        """Resolve an API key for *scanner_id* from internal ``.env`` state only."""
        scanner = self._scanners.get(scanner_id)
        if scanner is None:
            return None
        for pattern in credential_env_names(scanner_id, scanner.name):
            val = self._env_state.get(pattern)
            if val:
                return val
        return None

    def _get_api_key_for_scanner(self, scanner_id: str) -> str | None:
        """Get API key for scanner with multiple fallback strategies.

        Checks the shared candidate list (:func:`credential_env_names` — the
        ONE priority order) against ``os.environ``; a key already stored on
        the scanner config is the last resort. An unknown scanner id has no
        name-based candidate and no cached key, so only the id-based env
        candidates apply and the result is ``None`` when none is set.
        """
        scanner = self._scanners.get(scanner_id)
        for pattern in credential_env_names(scanner_id, scanner.name if scanner else None):
            api_key = os.getenv(pattern)
            if api_key:
                return api_key
        if scanner is not None and scanner.api_key:
            return scanner.api_key
        return None

    def register_scanner(self, scanner_id: str, config_data: dict[str, Any]) -> None:
        """Dynamically register a new scanner."""
        # The credential lookup below reads ``.env`` state, and registration can
        # be the very first call made against this manager.
        self._ensure_env_loaded()
        try:
            networks_any: Any = config_data.get('supported_networks', ['main'])
            networks_list: list[str] = _coerce_networks_list(networks_any, scanner_id)

            scanner_config = ScannerConfig(
                name=config_data['name'],
                base_domain=config_data['base_domain'],
                currency=config_data['currency'],
                supported_networks=set(networks_list),
                requires_api_key=cast(bool, config_data.get('requires_api_key', True)),
                special_config=cast(dict[str, Any], config_data.get('special_config', {})),
            )

            self._scanners[scanner_id] = scanner_config

            # Try to load API key for new scanner from .env state first
            env_key = self._resolve_env_state_key(scanner_id)
            if env_key and not scanner_config.api_key:
                scanner_config.api_key = env_key
            # Then check os.environ (overrides .env values)
            api_key = self._get_api_key_for_scanner(scanner_id)
            if api_key:
                scanner_config.api_key = api_key

            logger.info(f'Registered new scanner: {scanner_id} ({scanner_config.name})')

        except KeyError as e:
            raise ValueError(f'Invalid scanner configuration for {scanner_id}: missing {e}') from e

    def get_scanner_config(self, scanner_id: str) -> ScannerConfig:
        """Get configuration for a specific scanner.

        Lazy loads configuration on first access. Attempts to load only the
        requested scanner first before falling back to full initialization.

        Returns a deep copy of the configuration to ensure thread safety and
        prevent mutable state leakage between different client instances.
        This is critical for multi-tenant applications where API keys and
        other sensitive configuration must remain isolated per client.
        """
        # Try lazy single-scanner loading first (most efficient path)
        config = self._get_scanner_config_lazy(scanner_id)
        if config is not None:
            return copy.deepcopy(config)

        # Fall back to full initialization (needed for custom scanners from config files)
        self._ensure_initialized()

        if scanner_id not in self._scanners:
            available = ', '.join(sorted(self._scanners.keys()))
            raise ValueError(f'Unknown scanner "{scanner_id}". Available: {available}')
        # Security: Return a deep copy to prevent mutation of shared global state.
        # This ensures API keys and other sensitive config cannot leak between
        # different client instances in multi-tenant environments.
        return copy.deepcopy(self._scanners[scanner_id])

    def get_api_key(self, scanner_id: str) -> str:
        """Get API key for a scanner with validation.

        After Etherscan V2 API migration, BSC/Polygon/Arbitrum/Base/Optimism
        all use ETHERSCAN_KEY as fallback. Family membership is registry
        topology, carried on each builtin definition as
        ``credential_family`` (derived from the registry's kind profiles;
        'eth' itself resolves ETHERSCAN_KEY as its primary strategy already
        and declares no family).
        """
        config = self.get_scanner_config(scanner_id)

        # If key is already set, use it
        if config.api_key:
            return config.api_key

        # The family's shared fallback credential is the family root's
        # primary env var (ETHERSCAN_KEY) — taken from the ONE pattern via
        # the pristine builtin definition, not retyped as a literal here.
        # Looked up on the builtin table (not the loaded config) so a dynamic
        # registration shadowing a family name keeps the same fallback.
        family_fallback: str | None = None
        builtin = self._get_builtin_scanner(scanner_id)
        family = builtin.credential_family if builtin is not None else None
        if family is not None:
            family_builtin = self._get_builtin_scanner(family)
            if family_builtin is not None:
                family_fallback = credential_env_names(family, family_builtin.name)[0]
                family_key = os.getenv(family_fallback) or self._env_state.get(family_fallback)
                if family_key:
                    return family_key

        if config.requires_api_key:
            suggestions = self._get_api_key_suggestions(scanner_id)
            # Add the family fallback to suggestions for V2 scanners
            if family_fallback is not None and family_fallback not in suggestions:
                suggestions.insert(0, family_fallback)
            raise ValueError(
                f'API key required for {config.name}. '
                f'Set one of these environment variables: {", ".join(suggestions)}'
            )

        return ''

    def _get_api_key_suggestions(self, scanner_id: str) -> list[str]:
        """Get suggestions for API key environment variable names.

        Exactly the lookup candidates of :func:`credential_env_names` in
        priority order, so suggestion text cannot drift from the real lookup.
        """
        scanner_name = self.get_scanner_config(scanner_id).name
        return list(credential_env_names(scanner_id, scanner_name))

    def get_supported_scanners(self) -> list[str]:
        """Get list of all supported scanner names."""
        self._ensure_initialized()
        return list(self._scanners.keys())

    def get_scanner_networks(self, scanner_id: str) -> set[str]:
        """Get supported networks for a specific scanner."""
        return self.get_scanner_config(scanner_id).supported_networks.copy()

    def list_all_configurations(self) -> dict[str, dict[str, Any]]:
        """Get overview of all scanner configurations."""
        self._ensure_initialized()
        result: dict[str, dict[str, Any]] = {}
        for scanner_id, config in self._scanners.items():
            api_key_sources = self._get_api_key_suggestions(scanner_id)

            result[scanner_id] = {
                'name': config.name,
                'domain': config.base_domain,
                'currency': config.currency,
                'networks': sorted(config.supported_networks),
                'requires_api_key': config.requires_api_key,
                'api_key_configured': bool(config.api_key),
                'api_key_sources': api_key_sources,
                'special_config': config.special_config,
            }
        return result

    def generate_env_template(self, output_file: Path | None = None) -> str:
        """Generate .env template with all possible API keys."""
        self._ensure_initialized()
        lines = [
            '# aiochainscan API Keys Configuration',
            '# Copy this file to .env and fill in your API keys',
            '# You only need keys for the scanners you plan to use',
            '',
        ]

        for scanner_id, config in self._scanners.items():
            if config.requires_api_key:
                # Primary format = first candidate of the ONE credential
                # pattern: scanner name + _KEY (e.g., ETHERSCAN_KEY).
                primary_var = credential_env_names(scanner_id, config.name)[0]
                lines.extend(
                    [
                        f'# {config.name} ({config.base_domain})',
                        f'# Networks: {", ".join(sorted(config.supported_networks))}',
                        f'{primary_var}=your_{scanner_id}_api_key_here',
                        '',
                    ]
                )

        lines.append('# Optional: Set log level for debugging')
        lines.append('# AIOCHAINSCAN_LOG_LEVEL=DEBUG')

        template = '\n'.join(lines)

        if output_file:
            output_file.write_text(template)
            logger.info(f'Generated .env template at {output_file}')

        return template

    def export_config(self, output_file: Path) -> None:
        """Export current configuration to JSON file."""
        config_data: dict[str, Any] = {'version': '1.0', 'scanners': {}, 'api_keys': {}}

        scanners_section = cast(dict[str, Any], config_data['scanners'])
        api_keys_section = cast(dict[str, str], config_data['api_keys'])

        for scanner_id, config in self._scanners.items():
            scanners_section[scanner_id] = {
                'name': config.name,
                'base_domain': config.base_domain,
                'currency': config.currency,
                'supported_networks': list(config.supported_networks),
                'requires_api_key': config.requires_api_key,
                'special_config': config.special_config,
            }

            if config.api_key:
                api_keys_section[scanner_id] = config.api_key

        with open(output_file, 'w') as f:
            json.dump(config_data, f, indent=2)

        logger.info(f'Configuration exported to {output_file}')

    def persist_scanner(self, scanner_id: str, config_file: Path) -> None:
        """Merge one registered scanner into a JSON config file this manager loads.

        Entries already in the file are preserved; the API key is never written,
        since key resolution stays with the environment.
        """
        config = self.get_scanner_config(scanner_id)

        document: dict[str, Any] = {}
        if config_file.exists():
            loaded: Any = json.loads(config_file.read_text())
            if not isinstance(loaded, dict):
                raise ValueError(f'{config_file} does not contain a JSON object')
            document = cast(dict[str, Any], loaded)

        scanners_section: Any = document.setdefault('scanners', {})
        if not isinstance(scanners_section, dict):
            raise ValueError(f'{config_file} has a non-object "scanners" section')

        cast(dict[str, Any], scanners_section)[scanner_id] = {
            'name': config.name,
            'base_domain': config.base_domain,
            'currency': config.currency,
            'supported_networks': sorted(config.supported_networks),
            'requires_api_key': config.requires_api_key,
            'special_config': config.special_config,
        }

        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(document, indent=2) + '\n')

        logger.info(f'Persisted scanner {scanner_id} to {config_file}')


_config_manager_instance: ConfigurationManager | None = None


def get_config_manager() -> ConfigurationManager:
    """Get lazily-initialized global configuration manager."""
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = ConfigurationManager()
    return _config_manager_instance


class _ConfigManagerProxy:
    """Backward-compatible lazy proxy for ``config_manager`` global."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_config_manager(), name)


# Backward-compatible symbol, now lazy
config_manager = _ConfigManagerProxy()


# Export new advanced interface
__all__ = [
    'ConfigurationManager',
    'ScannerConfig',
    'config_manager',
    'get_config_manager',
]
