import json
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from aiochainscan.config import (
    ConfigurationManager,
    ScannerConfig,
    config_manager,
    credential_env_names,
    get_config_manager,
)


class TestScannerConfig:
    """Test ScannerConfig dataclass."""

    def test_scanner_config_creation(self):
        """Test creating a ScannerConfig instance."""
        scanner_config = ScannerConfig(
            name='Test Scanner',
            base_domain='test.com',
            currency='TEST',
            supported_networks={'main', 'test'},
            requires_api_key=True,
        )

        assert scanner_config.name == 'Test Scanner'
        assert scanner_config.base_domain == 'test.com'
        assert scanner_config.currency == 'TEST'
        assert scanner_config.supported_networks == {'main', 'test'}
        assert scanner_config.requires_api_key is True
        assert scanner_config.special_config == {}
        assert scanner_config.api_key is None


class TestConfigurationManager:
    """Test ConfigurationManager class."""

    def test_init_builtin_scanners(self):
        """Test that built-in scanners are initialized."""
        manager = ConfigurationManager()
        scanners = manager.get_supported_scanners()

        expected_scanners = [
            'eth',
            'bsc',
            'polygon',
            'optimism',
            'arbitrum',
            'fantom',
            'gnosis',
            'flare',
            'base',
            'linea',
            'blast',
        ]

        for scanner in expected_scanners:
            assert scanner in scanners

    def test_get_scanner_config(self):
        """Test getting scanner configuration."""
        manager = ConfigurationManager()

        # Test valid scanner
        eth_config = manager.get_scanner_config('eth')
        assert eth_config.name == 'Etherscan'
        assert eth_config.base_domain == 'etherscan.io'
        assert eth_config.currency == 'ETH'

        # Test invalid scanner
        with pytest.raises(ValueError, match='Unknown scanner "invalid"'):
            manager.get_scanner_config('invalid')

    def test_get_scanner_config_returns_an_isolated_copy(self):
        """Returned configs are mutation-isolated from the manager's state.

        ``get_scanner_config`` deep-copies on read so callers can mutate the
        returned mapping (mutable ``supported_networks`` / ``special_config``)
        without corrupting the shared manager — the multi-tenant isolation
        guarantee. This pins the guarantee.
        """
        manager = ConfigurationManager()
        config = manager.get_scanner_config('eth')

        config.supported_networks.add('mutated_network')
        config.special_config['mutated'] = True
        config.name = 'Mutated Name'

        fresh = manager.get_scanner_config('eth')
        assert 'mutated_network' not in fresh.supported_networks
        assert 'mutated' not in fresh.special_config
        assert fresh.name == 'Etherscan'
        # The manager's own state is untouched too
        assert 'mutated_network' not in manager._scanners['eth'].supported_networks
        assert 'mutated' not in manager._scanners['eth'].special_config
        assert manager._scanners['eth'].name == 'Etherscan'

    def test_load_env_file(self):
        """Test loading environment variables from .env file."""
        manager = ConfigurationManager()

        # Create temporary .env file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("""
# Test configuration
ETH_KEY=test_eth_key_123
BSC_KEY=test_bsc_key_456
# Comment line
INVALID_LINE_WITHOUT_EQUALS

EMPTY_VALUE=
            """)
            env_file = Path(f.name)

        try:
            # Load the file
            manager._load_env_file(env_file)

            # Variables should be stored in _env_state, NOT mutating os.environ
            assert manager._env_state.get('ETH_KEY') == 'test_eth_key_123'
            assert manager._env_state.get('BSC_KEY') == 'test_bsc_key_456'
            # Verify os.environ is NOT mutated (this was the old buggy behavior)
            assert 'ETH_KEY' not in os.environ or os.environ['ETH_KEY'] != 'test_eth_key_123'

        finally:
            # Clean up
            env_file.unlink()

    def test_api_key_fallback_strategies(self):
        """Test multiple API key fallback strategies."""
        manager = ConfigurationManager()

        # Clear all possible environment variables
        for key in ['ETH_KEY', 'ETH_API_KEY', 'ETHERSCAN_KEY', 'SCANNER_ETH_KEY']:
            os.environ.pop(key, None)

        # Test primary pattern (new format: ETHERSCAN_KEY)
        os.environ['ETHERSCAN_KEY'] = 'primary_scanner_name_key'
        api_key = manager._get_api_key_for_scanner('eth')
        assert api_key == 'primary_scanner_name_key'

        # Test fallback to old format when new format not available
        del os.environ['ETHERSCAN_KEY']
        os.environ['ETH_KEY'] = 'fallback_scanner_id_key'
        api_key = manager._get_api_key_for_scanner('eth')
        assert api_key == 'fallback_scanner_id_key'

        # Test priority: new format should win over old format
        os.environ['ETHERSCAN_KEY'] = 'new_format_wins'
        os.environ['ETH_KEY'] = 'old_format_loses'
        api_key = manager._get_api_key_for_scanner('eth')
        assert api_key == 'new_format_wins'

        # Clean up
        for key in ['ETH_KEY', 'ETHERSCAN_KEY']:
            os.environ.pop(key, None)

    def test_register_scanner(self):
        """Test dynamic scanner registration."""
        manager = ConfigurationManager()

        scanner_data = {
            'name': 'Test Custom Scanner',
            'base_domain': 'testcustom.com',
            'currency': 'TEST',
            'supported_networks': ['main', 'testnet'],
            'requires_api_key': True,
            'special_config': {'rate_limit': 10},
        }

        manager.register_scanner('testcustom', scanner_data)

        # Verify scanner was registered
        config = manager.get_scanner_config('testcustom')
        assert config.name == 'Test Custom Scanner'
        assert config.base_domain == 'testcustom.com'
        assert config.currency == 'TEST'
        assert config.supported_networks == {'main', 'testnet'}
        assert config.special_config == {'rate_limit': 10}

    def test_register_scanner_invalid_data(self):
        """Test error handling for invalid scanner data."""
        manager = ConfigurationManager()

        # Missing required fields
        invalid_data = {
            'name': 'Invalid Scanner'
            # Missing base_domain, currency
        }

        with pytest.raises(ValueError, match='Invalid scanner configuration'):
            manager.register_scanner('invalid', invalid_data)

    def test_load_config_file(self):
        """Test loading configuration from JSON file."""
        manager = ConfigurationManager()

        config_data = {
            'version': '1.0',
            'scanners': {
                'custom1': {
                    'name': 'Custom Scanner 1',
                    'base_domain': 'custom1.com',
                    'currency': 'C1',
                    'supported_networks': ['main'],
                    'requires_api_key': True,
                }
            },
            'api_keys': {'custom1': 'custom1_api_key'},
        }

        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_file = Path(f.name)

        try:
            # Load configuration
            manager._load_config_file(config_file)

            # Verify scanner was loaded
            config = manager.get_scanner_config('custom1')
            assert config.name == 'Custom Scanner 1'
            assert config.api_key == 'custom1_api_key'

        finally:
            config_file.unlink()

    def test_get_api_key_with_validation(self):
        """Test API key retrieval with validation."""
        manager = ConfigurationManager()

        # Test with configured API key (new format)
        with patch.dict(os.environ, {'ETHERSCAN_KEY': 'test_key_123'}):
            manager._load_api_keys()
            api_key = manager.get_api_key('eth')
            assert api_key == 'test_key_123'

        # Test missing required API key - need to clear the scanner's API key too
        with patch.dict(os.environ, {}, clear=True):
            # Clear the cached API key from the scanner's internal state
            # Note: get_scanner_config() returns a deepcopy for security, so we
            # must modify the internal _scanners dict directly for testing
            manager._scanners['eth'].api_key = None

            with pytest.raises(ValueError, match='API key required for Etherscan'):
                manager.get_api_key('eth')

    def test_get_api_key_optional(self):
        """Test API key for scanner that doesn't require it."""
        manager = ConfigurationManager()

        with patch.dict(os.environ, {}, clear=True):
            manager._load_api_keys()
            # Flare doesn't require API key
            api_key = manager.get_api_key('flare')
            assert api_key == ''

    def test_generate_env_template(self):
        """Test .env template generation."""
        manager = ConfigurationManager()

        template = manager.generate_env_template()

        # Check that template contains expected sections
        assert '# aiochainscan API Keys Configuration' in template
        assert 'ETHERSCAN_KEY=' in template
        assert 'BSCSCAN_KEY=' in template
        assert '# Optional: Set log level' in template

        # Check that optional scanners are excluded
        assert 'FLARE_KEY=' not in template  # Flare doesn't require API key

    def test_export_config(self):
        """Test configuration export to JSON."""
        manager = ConfigurationManager()

        # Add API key for testing
        with patch.dict(os.environ, {'ETHERSCAN_KEY': 'test_export_key'}):
            manager._load_api_keys()

            # Create temporary output file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                output_file = Path(f.name)

            try:
                # Export configuration
                manager.export_config(output_file)

                # Load and verify exported data
                with open(output_file) as f:
                    exported_data = json.load(f)

                assert exported_data['version'] == '1.0'
                assert 'scanners' in exported_data
                assert 'api_keys' in exported_data
                assert 'eth' in exported_data['scanners']
                assert exported_data['scanners']['eth']['name'] == 'Etherscan'

            finally:
                output_file.unlink()


class TestGlobalConfigManager:
    """Test the global config manager instance."""

    def test_global_config_manager_exists(self):
        """Test that global config manager instance exists and works."""
        assert config_manager is not None
        manager = get_config_manager()
        assert isinstance(manager, ConfigurationManager)

        # Test basic functionality
        scanners = config_manager.get_supported_scanners()
        assert len(scanners) > 0
        assert 'eth' in scanners

    def test_reset_instance_clears_class_and_module_singletons(self):
        """Resetting either access path must not retain a stale manager."""
        import aiochainscan.config as config_module

        first = get_config_manager()
        assert ConfigurationManager() is first

        ConfigurationManager.reset_instance()

        assert config_module._config_manager_instance is None
        second = get_config_manager()
        assert second is not first
        assert ConfigurationManager() is second


class TestAdvancedFeatures:
    """Test advanced configuration features."""

    def test_api_key_suggestions(self):
        """Test API key suggestion generation."""
        manager = ConfigurationManager()

        suggestions = manager._get_api_key_suggestions('eth')

        expected_suggestions = [
            'ETHERSCAN_KEY',  # Primary format now first
            'ETH_KEY',
            'ETH_API_KEY',
            'SCANNER_ETH_KEY',
        ]

        assert all(suggestion in suggestions for suggestion in expected_suggestions)

    def test_api_key_suggestions_are_not_repeated(self):
        """A scanner whose display name equals its id must not be told twice.

        ``nodereal`` collapses the primary and fallback spellings onto
        ``NODEREAL_KEY``; the duplicate showed up in the missing-key error.
        """
        suggestions = ConfigurationManager()._get_api_key_suggestions('nodereal')

        assert suggestions == list(dict.fromkeys(suggestions))
        assert suggestions[0] == 'NODEREAL_KEY'

    def test_list_all_configurations(self):
        """Test listing all configurations with status."""
        manager = ConfigurationManager()

        with patch.dict(os.environ, {'ETHERSCAN_KEY': 'test_key'}):
            manager._load_api_keys()
            configs = manager.list_all_configurations()

            assert 'eth' in configs
            eth_config = configs['eth']
            assert eth_config['name'] == 'Etherscan'
            assert eth_config['api_key_configured'] is True
            assert 'api_key_sources' in eth_config
            assert eth_config['special_config'] == {}

    def test_special_scanner_configurations(self):
        """Test scanners with special configurations."""
        manager = ConfigurationManager()

        # Test Optimism special config
        optimism_config = manager.get_scanner_config('optimism')
        assert optimism_config.special_config['subdomain_pattern'] == 'optimistic'


class TestTopologyDerivedFromRegistry:
    """config.py carries credentials only: builtin scanner topology (BlockScout
    hosts, currencies, supported networks) is derived from chain_registry — the
    single source — instead of being mirrored here."""

    def test_blockscout_hosts_derive_from_registry(self):
        from aiochainscan.chain_registry import BLOCKSCOUT_HOSTS

        definitions = ConfigurationManager()._get_builtin_scanner_definitions()
        assert set(BLOCKSCOUT_HOSTS) <= set(definitions)
        for scanner_id, host in BLOCKSCOUT_HOSTS.items():
            assert definitions[scanner_id].base_domain == host

    def test_currencies_derive_from_registry(self):
        from aiochainscan.chain_registry import URL_BUILDER_CURRENCIES

        definitions = ConfigurationManager()._get_builtin_scanner_definitions()
        for scanner_id, config in definitions.items():
            assert config.currency == URL_BUILDER_CURRENCIES[scanner_id]

    def test_supported_networks_derive_from_registry(self):
        from aiochainscan.chain_registry import SCANNER_CONFIG_NETWORKS

        definitions = ConfigurationManager()._get_builtin_scanner_definitions()
        assert set(definitions) == set(SCANNER_CONFIG_NETWORKS)
        for scanner_id, config in definitions.items():
            assert config.supported_networks == set(SCANNER_CONFIG_NETWORKS[scanner_id])

    def test_v2_key_fallback_family_derives_from_registry(self):
        """The ETHERSCAN_KEY fallback family is the registry's V2 family."""
        manager = ConfigurationManager()
        manager.get_scanner_config('bsc')  # ensure the lazy definition is loaded
        with patch.dict(os.environ, {'ETHERSCAN_KEY': 'family_key'}):
            manager._scanners['bsc'].api_key = None
            assert manager.get_api_key('bsc') == 'family_key'


class TestLazyLoading:
    """Test lazy loading behavior of ConfigurationManager."""

    def test_no_config_loaded_at_import(self):
        """Test that configurations are not loaded until first access."""
        manager = ConfigurationManager.create_isolated()

        # Verify nothing is loaded at instantiation
        assert manager._builtin_loaded is False
        assert manager._env_loaded is False
        assert manager._config_files_loaded is False
        assert manager._scanners == {}

    def test_single_scanner_lazy_load(self):
        """Test that accessing a single scanner only loads that scanner."""
        manager = ConfigurationManager.create_isolated()

        # Access single scanner config
        config = manager.get_scanner_config('eth')

        # Verify only the requested scanner is loaded
        assert 'eth' in manager._scanners
        assert config.name == 'Etherscan'
        # Builtin_loaded remains False because we used lazy single-scanner path
        assert manager._builtin_loaded is False
        assert manager._env_loaded is True  # Env is loaded for API keys

    def test_lazy_path_applies_a_key_that_exists_only_in_a_dotenv_file(self, tmp_path):
        """A ``.env`` key must survive the lazy single-scanner path.

        That path serves every builtin scanner, so reading only ``os.environ``
        there made a documented setup (``ETHERSCAN_KEY`` in ``.env``, which is
        what ``make wt-new`` copies into a worktree) fail with "API key
        required".
        """
        (tmp_path / '.env').write_text('ETHERSCAN_KEY=from_dotenv_only\n')
        manager = ConfigurationManager.create_isolated(tmp_path)

        with patch.dict(os.environ, {}, clear=True):
            assert manager.get_api_key('eth') == 'from_dotenv_only'
            assert manager._builtin_loaded is False  # still the lazy path

    def test_registered_scanner_sees_a_key_that_exists_only_in_a_dotenv_file(self, tmp_path):
        """Registration is a valid first call, and it resolves a credential.

        It read ``.env`` state without loading the ``.env`` files, so the
        documented "loaded on first access" contract held only for whoever
        happened to trigger full initialization first.
        """
        (tmp_path / '.env').write_text('CUSTOMSCAN_KEY=from_dotenv_only\n')
        manager = ConfigurationManager.create_isolated(tmp_path)

        with patch.dict(os.environ, {}, clear=True):
            manager.register_scanner(
                'customscan',
                {'name': 'CustomScan', 'base_domain': 'customscan.io', 'currency': 'ETH'},
            )
            assert manager.get_api_key('customscan') == 'from_dotenv_only'

    def test_os_environ_overrides_the_dotenv_key(self, tmp_path):
        (tmp_path / '.env').write_text('ETHERSCAN_KEY=from_dotenv\n')
        manager = ConfigurationManager.create_isolated(tmp_path)

        with patch.dict(os.environ, {'ETHERSCAN_KEY': 'from_environ'}, clear=True):
            assert manager.get_api_key('eth') == 'from_environ'

    def test_get_supported_scanners_triggers_full_init(self):
        """Test that get_supported_scanners() triggers full initialization."""
        manager = ConfigurationManager.create_isolated()

        # This should trigger full initialization
        scanners = manager.get_supported_scanners()

        assert manager._builtin_loaded is True
        assert manager._config_files_loaded is True
        assert len(scanners) > 10  # We have many builtin scanners


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_load_invalid_env_file(self):
        """Test handling of invalid .env files."""
        manager = ConfigurationManager()

        # Create invalid file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write('invalid content that will cause error')
            f.write('\x00\x01\x02')  # Binary content
            env_file = Path(f.name)

        try:
            # Should not raise exception, just log warning
            manager._load_env_file(env_file)

        finally:
            env_file.unlink()

    def test_load_invalid_config_file(self):
        """Test handling of invalid JSON config files."""
        manager = ConfigurationManager()

        # Create invalid JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{ invalid json content')
            config_file = Path(f.name)

        try:
            # Should not raise exception, just log warning
            manager._load_config_file(config_file)

        finally:
            config_file.unlink()

    def test_api_key_fallback_with_exceptions(self):
        """Test API key fallback when strategies raise exceptions."""
        manager = ConfigurationManager()

        # Test with scanner that doesn't exist in the config
        with patch.dict(os.environ, {}, clear=True):
            try:
                api_key = manager._get_api_key_for_scanner('nonexistent_scanner')
                # This should return None or raise an exception gracefully
                assert api_key is None
            except KeyError:
                # This is also acceptable - the scanner doesn't exist
                pass


class TestCredentialEnvNamePattern:
    """``credential_env_names`` is the ONE statement of the credential
    env-var priority order; lookup, suggestions and the ``.env`` template
    all derive from it, so they cannot drift apart."""

    def test_credential_env_names_priority_order(self):
        """The candidate list, in priority order."""
        assert credential_env_names('eth', 'Etherscan') == (
            'ETHERSCAN_KEY',
            'ETH_KEY',
            'ETH_API_KEY',
            'SCANNER_ETH_KEY',
            'API_KEY_ETH',
        )

    def test_credential_env_names_without_display_name(self):
        """An unknown display name omits the name-based candidate only."""
        assert credential_env_names('eth') == (
            'ETH_KEY',
            'ETH_API_KEY',
            'SCANNER_ETH_KEY',
            'API_KEY_ETH',
        )

    def test_suggestions_match_lookup_candidates(self):
        """Suggestion text is exactly the lookup candidate list."""
        manager = ConfigurationManager()
        manager.get_scanner_config('eth')  # ensure the scanner is known

        assert manager._get_api_key_suggestions('eth') == list(
            credential_env_names('eth', 'Etherscan')
        )

    def test_every_pattern_candidate_is_honored_by_lookup(self):
        """Each generated candidate really is a lookup candidate."""
        manager = ConfigurationManager()
        manager.get_scanner_config('eth')  # ensure the scanner is known

        for pattern in credential_env_names('eth', 'Etherscan'):
            with patch.dict(os.environ, {pattern: f'key_via_{pattern}'}, clear=True):
                manager._scanners['eth'].api_key = None
                assert manager._get_api_key_for_scanner('eth') == f'key_via_{pattern}', pattern

    def test_lookup_follows_the_generated_priority_order(self):
        """Earlier candidates win: peel the list from the top."""
        manager = ConfigurationManager()
        manager.get_scanner_config('eth')  # ensure the scanner is known

        candidates = credential_env_names('eth', 'Etherscan')
        env = {pattern: f'key_{index}' for index, pattern in enumerate(candidates)}
        with patch.dict(os.environ, env, clear=True):
            for expected_index in range(len(candidates)):
                assert manager._get_api_key_for_scanner('eth') == f'key_{expected_index}'
                del os.environ[candidates[expected_index]]

    def test_v2_fallback_and_suggestions_come_from_the_pattern(self, tmp_path, monkeypatch):
        """The V2 family fallback is the eth scanner's primary candidate."""
        # Hermetic: no host .env file may inject the fallback into _env_state
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        manager = ConfigurationManager.create_isolated(tmp_path)
        manager.get_scanner_config('bsc')  # ensure the lazy definition is loaded

        with patch.dict(os.environ, {'ETHERSCAN_KEY': 'family_key'}, clear=True):
            manager._scanners['bsc'].api_key = None
            assert manager.get_api_key('bsc') == 'family_key'

        # Without the fallback key, the error suggests it first, ahead of the
        # bsc scanner's own candidates.
        with patch.dict(os.environ, {}, clear=True):
            manager._scanners['bsc'].api_key = None
            with pytest.raises(ValueError, match='ETHERSCAN_KEY, BSCSCAN_KEY'):
                manager.get_api_key('bsc')


# ─────────────────────────── fixtures and helpers ──────────────────────────


@pytest.fixture
def isolated_manager(tmp_path, monkeypatch):
    """A ConfigurationManager bound to tmp_path with a fake HOME.

    Hermetic by construction (:meth:`ConfigurationManager.create_isolated`):
    it is not the shared instance, so no machine-level ``~/.aiochainscan``
    state and no cwd-dependent config file can leak into — or out of — the
    test.
    """
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    return ConfigurationManager.create_isolated(tmp_path)


def _write(manager: ConfigurationManager, name: str, content) -> Path:
    """Write an env file next to the manager's config dir (str or bytes)."""
    env_file = manager.config_dir / name
    if isinstance(content, bytes):
        env_file.write_bytes(content)
    else:
        env_file.write_text(content)
    return env_file


class TestEnvFileDialect:
    """The hand-rolled ``.env`` parser follows python-dotenv conventions.

    Every test here runs against an isolated manager (fake HOME, tmp config
    dir) so the host's real ``~/.aiochainscan/.env`` can never mask a parse.
    """

    def test_export_prefix_is_not_part_of_the_key(self, isolated_manager):
        _write(isolated_manager, '.env', 'export ETHERSCAN_KEY=exported\n')
        isolated_manager._ensure_env_loaded()
        assert isolated_manager._env_state.get('ETHERSCAN_KEY') == 'exported'
        assert 'export ETHERSCAN_KEY' not in isolated_manager._env_state

    def test_export_prefix_with_tab_and_multiple_spaces(self, isolated_manager):
        _write(isolated_manager, '.env', 'export\tFIRST_KEY=a\nexport  SECOND_KEY=b\n')
        isolated_manager._ensure_env_loaded()
        assert isolated_manager._env_state.get('FIRST_KEY') == 'a'
        assert isolated_manager._env_state.get('SECOND_KEY') == 'b'

    def test_bare_export_is_kept_as_a_key(self, isolated_manager):
        # A line like `export=val` has no space after 'export'; 'export' is
        # then a genuine key, not a prefix.
        _write(isolated_manager, '.env', 'export=kept\n')
        isolated_manager._ensure_env_loaded()
        assert isolated_manager._env_state.get('export') == 'kept'

    def test_unquoted_inline_comment_is_stripped(self, isolated_manager):
        _write(isolated_manager, '.env', 'PLAIN_KEY=value # trailing comment\n')
        isolated_manager._ensure_env_loaded()
        assert isolated_manager._env_state.get('PLAIN_KEY') == 'value'

    def test_hash_inside_quoted_values_is_data(self, isolated_manager):
        _write(
            isolated_manager,
            '.env',
            'DOUBLE_KEY="v # kept"\nSINGLE_KEY=\'v # also kept\'\n',
        )
        isolated_manager._ensure_env_loaded()
        assert isolated_manager._env_state.get('DOUBLE_KEY') == 'v # kept'
        assert isolated_manager._env_state.get('SINGLE_KEY') == 'v # also kept'

    def test_bom_does_not_corrupt_the_first_key(self, isolated_manager):
        _write(isolated_manager, '.env', b'\xef\xbb\xbfETHERSCAN_KEY=bom_key\n')
        isolated_manager._ensure_env_loaded()
        assert isolated_manager._env_state.get('ETHERSCAN_KEY') == 'bom_key'
        assert '\ufeffETHERSCAN_KEY' not in isolated_manager._env_state

    def test_env_local_overshadows_env(self, isolated_manager):
        """``.env.local`` must beat ``.env`` — the universal dotenv convention.

        First-setter-wins parsing makes the load order the precedence, so the
        local (untracked) file loads before the tracked ``.env``.
        """
        _write(isolated_manager, '.env', 'ETHERSCAN_KEY=from_env\nONLY_IN_ENV=env\n')
        _write(isolated_manager, '.env.local', 'ETHERSCAN_KEY=from_local\n')
        isolated_manager._ensure_env_loaded()
        assert isolated_manager._env_state.get('ETHERSCAN_KEY') == 'from_local'
        # A key only present in .env still loads.
        assert isolated_manager._env_state.get('ONLY_IN_ENV') == 'env'

    def test_repo_files_still_overshadow_the_machine_level_file(
        self, isolated_manager, tmp_path, monkeypatch
    ):
        # Documented contract: repo-local ./.env overrides ~/.aiochainscan/.env.
        # (home is already the fake tmp_path; write the machine-level file.)
        (tmp_path / '.aiochainscan').mkdir()
        (tmp_path / '.aiochainscan' / '.env').write_text('ETHERSCAN_KEY=from_home\n')
        _write(isolated_manager, '.env', 'ETHERSCAN_KEY=from_repo\n')
        isolated_manager._ensure_env_loaded()
        assert isolated_manager._env_state.get('ETHERSCAN_KEY') == 'from_repo'

    @pytest.mark.parametrize(
        'content,key,expected',
        [
            # CRLF line endings
            ('CRLF_KEY=val\r\nNEXT=x\r\n', 'CRLF_KEY', 'val'),
            # no trailing newline on the last line
            ('NO_TRAILING=last', 'NO_TRAILING', 'last'),
            # '=' inside the value survives (split on the FIRST '=')
            ('EQ_KEY=a=b=c', 'EQ_KEY', 'a=b=c'),
            # quoted values keep inner spaces
            ('SPACED_KEY=" two words "', 'SPACED_KEY', ' two words '),
            # empty value
            ('EMPTY_KEY=', 'EMPTY_KEY', ''),
        ],
    )
    def test_existing_behavior_preserved(self, isolated_manager, content, key, expected):
        _write(isolated_manager, '.env', content)
        isolated_manager._ensure_env_loaded()
        assert isolated_manager._env_state.get(key) == expected


class TestBinaryEnvFileTolerance:
    """A non-UTF-8 ``.env`` must not crash client construction.

    The JSON config loader deliberately warns-and-continues on corruption;
    the env loader is the one config source that used to let
    ``UnicodeDecodeError`` escape ``ChainscanClient.from_config`` (round-2
    audit M5). Undecodable lines are skipped — a half-decoded credential is
    worse than a missing one — and the file's remaining lines still load.
    """

    def test_binary_env_file_warns_and_continues(self, isolated_manager, caplog):
        _write(
            isolated_manager,
            '.env',
            b'\x00\xff\xfebinary\xff=1\nETHERSCAN_KEY=works_despite_junk\n',
        )

        with caplog.at_level(logging.WARNING, logger='aiochainscan.config'):
            isolated_manager._ensure_env_loaded()

        assert isolated_manager._env_state.get('ETHERSCAN_KEY') == 'works_despite_junk'
        # The undecodable line was skipped, not stored half-decoded.
        assert not any('\ufffd' in key for key in isolated_manager._env_state)
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings, 'a binary .env must produce a warning'
        assert any('not valid UTF-8' in r.getMessage() for r in warnings)

    def test_binary_env_file_yields_a_working_client(self, isolated_manager, caplog):
        """End-to-end pin: construction-path credential resolution survives."""
        _write(
            isolated_manager,
            '.env',
            b'\xff\xd8\xff\xe0junk\x00\x01=2\nETHERSCAN_KEY=client_still_works\n',
        )

        with (
            caplog.at_level(logging.WARNING, logger='aiochainscan.config'),
            patch.dict(os.environ, {}, clear=True),
        ):
            assert isolated_manager.get_scanner_config('eth').name == 'Etherscan'
            assert isolated_manager.get_api_key('eth') == 'client_still_works'


class TestSingletonConfigDir:
    """``ConfigurationManager(config_dir=B)`` after the singleton exists must
    not silently keep directory A (round-2 audit M8).

    Chosen behaviour: warn and keep the first binding. The manager is
    documented as process-wide configuration (the machine-level
    ``~/.aiochainscan/.env`` is read for every cwd), so per-directory
    instances would multiply credential state and break the singleton
    identity contract; the surprise callers actually hit — reading another
    directory's ``.env``/JSON while believing they configured a different
    directory — is exactly what the warning names, together with the
    ``reset_instance()`` remedy.
    """

    def test_differing_config_dir_warns_and_keeps_first(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        dir_a = tmp_path / 'a'
        dir_b = tmp_path / 'b'
        dir_a.mkdir()
        dir_b.mkdir()
        ConfigurationManager.reset_instance()
        try:
            with caplog.at_level(logging.WARNING, logger='aiochainscan.config'):
                first = ConfigurationManager(dir_a)
                again = ConfigurationManager(dir_b)

            assert again is first
            assert first.config_dir == dir_a
            warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
            assert len(warnings) == 1
            message = warnings[0].getMessage()
            assert str(dir_a) in message
            assert str(dir_b) in message
            assert 'reset_instance' in message
        finally:
            ConfigurationManager.reset_instance()

    def test_differing_config_dir_warns_in_either_order(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        dir_a = tmp_path / 'a'
        dir_b = tmp_path / 'b'
        dir_a.mkdir()
        dir_b.mkdir()
        ConfigurationManager.reset_instance()
        try:
            with caplog.at_level(logging.WARNING, logger='aiochainscan.config'):
                first = ConfigurationManager(dir_b)
                second = ConfigurationManager(dir_a)

            assert second is first
            assert first.config_dir == dir_b
            warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
            assert len(warnings) == 1
        finally:
            ConfigurationManager.reset_instance()

    def test_same_config_dir_reinit_is_silent(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        ConfigurationManager.reset_instance()
        try:
            first = ConfigurationManager(tmp_path)
            with caplog.at_level(logging.WARNING, logger='aiochainscan.config'):
                again = ConfigurationManager(tmp_path)

            assert again is first
            assert first.config_dir == tmp_path
            assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        finally:
            ConfigurationManager.reset_instance()

    def test_equivalent_paths_are_not_a_directory_change(self, tmp_path, monkeypatch, caplog):
        """A differently-spelled path to the same directory is no change."""
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        target = tmp_path / 'a'
        ConfigurationManager.reset_instance()
        try:
            first = ConfigurationManager(target)
            with caplog.at_level(logging.WARNING, logger='aiochainscan.config'):
                again = ConfigurationManager(target.resolve())

            assert again is first
            assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        finally:
            ConfigurationManager.reset_instance()


class TestRegisterScannerInputValidation:
    """``supported_networks`` corruption must fail loudly, not become
    ``set('main')`` == ``{'m', 'a', 'i', 'n'}`` (round-2 audit LOW)."""

    def _base_data(self, **overrides):
        data = {
            'name': 'Test Scanner',
            'base_domain': 'test.example',
            'currency': 'TST',
        }
        data.update(overrides)
        return data

    def test_string_networks_rejected(self):
        manager = ConfigurationManager()
        with pytest.raises(ValueError, match='supported_networks'):
            manager.register_scanner('badscan', self._base_data(supported_networks='main'))

    def test_non_iterable_networks_raise_value_error_not_type_error(self):
        manager = ConfigurationManager()
        with pytest.raises(ValueError, match='supported_networks'):
            manager.register_scanner('badscan', self._base_data(supported_networks=42))

    def test_non_string_entries_rejected(self):
        manager = ConfigurationManager()
        with pytest.raises(ValueError, match='supported_networks'):
            manager.register_scanner('badscan', self._base_data(supported_networks=['main', 42]))

    @pytest.mark.parametrize('networks', [['main', 'test'], {'main'}, ('main', 't')])
    def test_sequence_networks_still_accepted(self, networks):
        manager = ConfigurationManager()
        manager.register_scanner('okscan', self._base_data(supported_networks=networks))
        assert manager.get_scanner_config('okscan').supported_networks == set(networks)

    def test_json_config_with_string_networks_warns_and_continues(self, isolated_manager, caplog):
        """The JSON loader's warn-and-continue contract covers the new
        validation error: one malformed scanner entry must not crash
        client construction."""
        config_file = isolated_manager.config_dir / 'aiochainscan.json'
        config_file.write_text(
            json.dumps(
                {
                    'scanners': {
                        'broken': {
                            'name': 'Broken',
                            'base_domain': 'broken.example',
                            'currency': 'BRK',
                            'supported_networks': 'main',
                        },
                    }
                }
            )
        )

        with caplog.at_level(logging.WARNING, logger='aiochainscan.config'):
            isolated_manager._load_config_file(config_file)

        assert any('supported_networks' in r.getMessage() for r in caplog.records)
        # Builtins remain reachable — construction not poisoned.
        assert isolated_manager.get_scanner_config('eth').name == 'Etherscan'

    def test_api_keys_for_unknown_scanner_ids_warn(self, isolated_manager, caplog):
        """An api_keys entry keyed by an unknown id is silently dropped today;
        the warning must name it (e.g. 'etherscan' instead of 'eth')."""
        isolated_manager.get_scanner_config('eth')  # load at least one scanner
        config_file = isolated_manager.config_dir / 'aiochainscan.json'
        config_file.write_text(
            json.dumps({'api_keys': {'eth': 'known_key', 'etherscan': 'misnamed_key'}})
        )

        with caplog.at_level(logging.WARNING, logger='aiochainscan.config'):
            isolated_manager._load_config_file(config_file)

        assert isolated_manager._scanners['eth'].api_key == 'known_key'
        warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert any('etherscan' in m for m in warnings)
