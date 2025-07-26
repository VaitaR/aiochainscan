import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from aiochainscan import Client
from aiochainscan.config import ConfigurationManager, ScannerConfig, config_manager


class TestScannerConfig:
    """Test ScannerConfig dataclass."""

    def test_scanner_config_creation(self):
        """Test creating a ScannerConfig instance."""
        scanner_config = ScannerConfig(
            name="Test Scanner",
            base_domain="test.com",
            currency="TEST",
            supported_networks={'main', 'test'},
            requires_api_key=True
        )

        assert scanner_config.name == "Test Scanner"
        assert scanner_config.base_domain == "test.com"
        assert scanner_config.currency == "TEST"
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
            'eth', 'bsc', 'polygon', 'optimism', 'arbitrum', 'fantom',
            'gnosis', 'flare', 'base', 'linea', 'blast', 'xlayer'
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

            # Check that variables were loaded
            assert os.getenv('ETH_KEY') == 'test_eth_key_123'
            assert os.getenv('BSC_KEY') == 'test_bsc_key_456'

        finally:
            # Clean up
            env_file.unlink()
            # Clean up environment
            for key in ['ETH_KEY', 'BSC_KEY', 'EMPTY_VALUE']:
                os.environ.pop(key, None)

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
            'special_config': {'rate_limit': 10}
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
                    'requires_api_key': True
                }
            },
            'api_keys': {
                'custom1': 'custom1_api_key'
            }
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

    def test_validate_network(self):
        """Test network validation."""
        manager = ConfigurationManager()

        # Test valid network
        network = manager.validate_network('eth', 'main')
        assert network == 'main'

        # Test network alias
        network = manager.validate_network('eth', 'mainnet')
        assert network == 'main'

        # Test invalid network
        with pytest.raises(ValueError, match='Network "invalid" not supported'):
            manager.validate_network('eth', 'invalid')

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
            # Clear the cached API key from the scanner config
            eth_config = manager.get_scanner_config('eth')
            eth_config.api_key = None

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
        assert isinstance(config_manager, ConfigurationManager)

        # Test basic functionality
        scanners = config_manager.get_supported_scanners()
        assert len(scanners) > 0
        assert 'eth' in scanners


class TestClientIntegration:
    """Test Client integration with the new configuration system."""

    def test_client_from_config(self):
        """Test creating client from configuration."""
        with (
            patch.dict(os.environ, {'ETHERSCAN_KEY': 'test_api_key'}),
            patch('asyncio.get_running_loop') as mock_loop,
        ):
                mock_loop.return_value = None

                # Reload config to pick up environment variable
                config_manager._load_api_keys()

                client = Client.from_config('eth', 'main')

                assert client._url_builder._API_KEY == 'test_api_key'
                assert client._url_builder._api_kind == 'eth'
                assert client._url_builder._network == 'main'

    def test_client_from_config_missing_key(self):
        """Test error when creating client with missing API key."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear the cached API key from the scanner config
            eth_config = config_manager.get_scanner_config('eth')
            eth_config.api_key = None

            with pytest.raises(ValueError, match='API key required'):
                Client.from_config('eth', 'main')

    def test_client_from_config_invalid_scanner(self):
        """Test error when creating client with invalid scanner."""
        with pytest.raises(ValueError, match='Unknown scanner'):
            Client.from_config('invalid_scanner', 'main')

    def test_client_from_config_invalid_network(self):
        """Test error when creating client with invalid network."""
        with patch.dict(os.environ, {'ETHERSCAN_KEY': 'test_key'}):
            config_manager._load_api_keys()
            with pytest.raises(ValueError, match='not supported'):
                Client.from_config('eth', 'invalid_network')


class TestAdvancedFeatures:
    """Test advanced configuration features."""

    def test_api_key_suggestions(self):
        """Test API key suggestion generation."""
        manager = ConfigurationManager()

        suggestions = manager._get_api_key_suggestions('eth')

        expected_suggestions = [
            'ETHERSCAN_KEY',     # Primary format now first
            'ETH_KEY',
            'ETH_API_KEY',
            'SCANNER_ETH_KEY',
        ]

        assert all(suggestion in suggestions for suggestion in expected_suggestions)

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

        # Test XLayer special config
        xlayer_config = manager.get_scanner_config('xlayer')
        assert xlayer_config.special_config['auth_header'] == 'OK-ACCESS-KEY'

        # Test Optimism special config
        optimism_config = manager.get_scanner_config('optimism')
        assert optimism_config.special_config['subdomain_pattern'] == 'optimistic'


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_load_invalid_env_file(self):
        """Test handling of invalid .env files."""
        manager = ConfigurationManager()

        # Create invalid file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("invalid content that will cause error")
            f.write("\x00\x01\x02")  # Binary content
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
            f.write("{ invalid json content")
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
