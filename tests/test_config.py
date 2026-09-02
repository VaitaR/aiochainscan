import json
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
        # Reset to get a fresh instance
        ConfigurationManager.reset_instance()

        # Create fresh instance
        manager = ConfigurationManager()

        # Verify nothing is loaded at instantiation
        assert manager._builtin_loaded is False
        assert manager._env_loaded is False
        assert manager._config_files_loaded is False
        assert manager._scanners == {}

    def test_single_scanner_lazy_load(self):
        """Test that accessing a single scanner only loads that scanner."""
        # Reset to get a fresh instance
        ConfigurationManager.reset_instance()

        manager = ConfigurationManager()

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
        ConfigurationManager.reset_instance()
        manager = ConfigurationManager(tmp_path)

        with patch.dict(os.environ, {}, clear=True):
            assert manager.get_api_key('eth') == 'from_dotenv_only'
            assert manager._builtin_loaded is False  # still the lazy path

        ConfigurationManager.reset_instance()

    def test_os_environ_overrides_the_dotenv_key(self, tmp_path):
        (tmp_path / '.env').write_text('ETHERSCAN_KEY=from_dotenv\n')
        ConfigurationManager.reset_instance()
        manager = ConfigurationManager(tmp_path)

        with patch.dict(os.environ, {'ETHERSCAN_KEY': 'from_environ'}, clear=True):
            assert manager.get_api_key('eth') == 'from_environ'

        ConfigurationManager.reset_instance()

    def test_get_supported_scanners_triggers_full_init(self):
        """Test that get_supported_scanners() triggers full initialization."""
        ConfigurationManager.reset_instance()
        manager = ConfigurationManager()

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
        ConfigurationManager.reset_instance()
        # Hermetic: no host .env file may inject the fallback into _env_state
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        manager = ConfigurationManager(tmp_path)
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

        ConfigurationManager.reset_instance()
