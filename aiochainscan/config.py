from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

# dotenv is optional - manual env file loading is implemented below

logger = logging.getLogger(__name__)


@dataclass
class ScannerCapabilities:
    """Describes which API actions are supported by each scanner network."""

    # Block module actions
    block_reward: bool = True
    block_countdown: bool = True
    block_number_by_timestamp: bool = True
    daily_block_stats: bool = True

    # Account module actions
    account_balance: bool = True
    account_transactions: bool = True
    account_internal_txs: bool = True
    account_erc20_transfers: bool = True
    account_erc721_transfers: bool = True
    account_erc1155_transfers: bool = True

    # Contract module actions
    contract_abi: bool = True
    contract_source_code: bool = True
    contract_creation: bool = True
    contract_verification: bool = False  # Most networks don't support verification

    # Transaction module actions
    tx_receipt_status: bool = True
    tx_status_check: bool = True

    # Stats module actions
    eth_supply: bool = True
    eth_price: bool = True
    nodes_size: bool = False  # Not supported by most networks

    # Gas tracker actions
    gas_estimate: bool = True
    gas_oracle: bool = True

    # Logs actions
    event_logs: bool = True

    # Token actions
    token_supply: bool = True
    token_balance: bool = True
    token_info: bool = True

    # Proxy actions
    proxy_eth_calls: bool = True


@dataclass
class ScannerConfig:
    """Configuration for a blockchain scanner."""

    name: str
    base_domain: str
    currency: str
    supported_networks: set[str] = field(default_factory=set)
    requires_api_key: bool = True
    special_config: dict[str, Any] = field(default_factory=dict)
    api_key: str | None = field(default=None, init=False)
    capabilities: ScannerCapabilities = field(default_factory=ScannerCapabilities)


class ConfigurationManager:
    """
    Advanced configuration manager for blockchain scanners.

    Features:
    - Automatic .env file loading
    - JSON configuration support
    - Dynamic scanner registration
    - Environment variable fallbacks
    - Validation and error handling
    """

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path.cwd()
        self._scanners: dict[str, ScannerConfig] = {}
        self._env_loaded = False

        # Initialize with built-in scanners
        self._init_builtin_scanners()

        # Load configuration from files
        self._load_env_files()
        self._load_config_files()
        self._load_api_keys()

    def _init_builtin_scanners(self) -> None:
        """Initialize built-in scanner configurations."""
        builtin_scanners = {
            'eth': ScannerConfig(
                name='Etherscan',
                base_domain='etherscan.io',
                currency='ETH',
                supported_networks={'main', 'test', 'goerli', 'sepolia'},
                requires_api_key=True,
            ),
            'bsc': ScannerConfig(
                name='BscScan',
                base_domain='bscscan.com',
                currency='BNB',
                supported_networks={'main', 'test'},
                requires_api_key=True,
            ),
            'polygon': ScannerConfig(
                name='PolygonScan',
                base_domain='polygonscan.com',
                currency='MATIC',
                supported_networks={'main', 'mumbai', 'test'},
                requires_api_key=True,
            ),
            'optimism': ScannerConfig(
                name='Optimism Etherscan',
                base_domain='etherscan.io',
                currency='ETH',
                supported_networks={'main', 'goerli', 'test'},
                requires_api_key=True,
                special_config={'subdomain_pattern': 'optimistic'},
            ),
            'arbitrum': ScannerConfig(
                name='Arbiscan',
                base_domain='arbiscan.io',
                currency='ETH',
                supported_networks={'main', 'nova', 'goerli', 'test'},
                requires_api_key=True,
            ),
            'fantom': ScannerConfig(
                name='FtmScan',
                base_domain='ftmscan.com',
                currency='FTM',
                supported_networks={'main', 'test'},
                requires_api_key=True,
            ),
            'gnosis': ScannerConfig(
                name='GnosisScan',
                base_domain='gnosisscan.io',
                currency='GNO',
                supported_networks={'main', 'chiado'},
                requires_api_key=True,
            ),
            'flare': ScannerConfig(
                name='Flare Explorer',
                base_domain='flare.network',
                currency='FLR',
                supported_networks={'main', 'test'},
                requires_api_key=False,
                special_config={'subdomain_pattern': 'flare-explorer'},
            ),
            'base': ScannerConfig(
                name='BaseScan',
                base_domain='basescan.org',
                currency='BASE',
                supported_networks={'main', 'goerli', 'sepolia'},
                requires_api_key=True,
            ),
            'linea': ScannerConfig(
                name='LineaScan',
                base_domain='lineascan.build',
                currency='LINEA',
                supported_networks={'main', 'test'},
                requires_api_key=True,
            ),
            'blast': ScannerConfig(
                name='BlastScan',
                base_domain='blastscan.io',
                currency='BLAST',
                supported_networks={'main', 'sepolia'},
                requires_api_key=True,
            ),
            'blockscout_eth': ScannerConfig(
                name='BlockScout Ethereum',
                base_domain='eth.blockscout.com',
                currency='ETH',
                supported_networks={'eth'},
                requires_api_key=False,
                special_config={'public_api': True},
            ),
            'blockscout_sepolia': ScannerConfig(
                name='BlockScout Sepolia',
                base_domain='eth-sepolia.blockscout.com',
                currency='ETH',
                supported_networks={'sepolia'},
                requires_api_key=False,
                special_config={'public_api': True},
            ),
            'blockscout_gnosis': ScannerConfig(
                name='BlockScout Gnosis',
                base_domain='gnosis.blockscout.com',
                currency='xDAI',
                supported_networks={'gnosis'},
                requires_api_key=False,
                special_config={'public_api': True},
            ),
            'blockscout_polygon': ScannerConfig(
                name='BlockScout Polygon',
                base_domain='polygon.blockscout.com',
                currency='MATIC',
                supported_networks={'polygon'},
                requires_api_key=False,
                special_config={'public_api': True},
            ),
            'moralis': ScannerConfig(
                name='Moralis Web3 Data API',
                base_domain='deep-index.moralis.io',
                currency='Multi-chain',
                supported_networks={
                    'eth',
                    'bsc',
                    'polygon',
                    'arbitrum',
                    'base',
                    'optimism',
                    'avalanche',
                },
                requires_api_key=True,
                special_config={
                    'api_version': 'v2.2',
                    'auth_mode': 'header',
                    'auth_field': 'X-API-Key',
                    'chain_mappings': {
                        'eth': '0x1',
                        'bsc': '0x38',
                        'polygon': '0x89',
                        'arbitrum': '0xa4b1',
                        'base': '0x2105',
                        'optimism': '0xa',
                        'avalanche': '0xa86a',
                    },
                },
            ),
        }

        self._scanners.update(builtin_scanners)

    def _load_env_files(self) -> None:
        """Load environment variables from .env files."""
        env_files = [
            self.config_dir / '.env',
            self.config_dir / '.env.local',
            Path.home() / '.aiochainscan' / '.env',
        ]

        for env_file in env_files:
            if env_file.exists():
                self._load_env_file(env_file)
                logger.debug(f'Loaded environment from {env_file}')

    def _load_env_file(self, env_file: Path) -> None:
        """Load variables from a specific .env file."""
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')

                        # Only set if not already set in environment
                        if key not in os.environ:
                            os.environ[key] = value
        except Exception as e:
            logger.warning(f'Failed to load {env_file}: {e}')

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
                for scanner_id, api_key in api_keys.items():
                    if scanner_id in self._scanners:
                        self._scanners[scanner_id].api_key = api_key

        except Exception as e:
            logger.warning(f'Failed to load config from {config_file}: {e}')

    def _load_api_keys(self) -> None:
        """Load API keys from various sources with priority order."""
        for scanner_id, scanner_config in self._scanners.items():
            api_key = self._get_api_key_for_scanner(scanner_id)
            if api_key:
                scanner_config.api_key = api_key

    def _get_api_key_for_scanner(self, scanner_id: str) -> str | None:
        """Get API key for scanner with multiple fallback strategies."""
        # Priority order for API key lookup:
        strategies: list[Callable[[], str | None]] = [
            # 1. Primary: Scanner name-based variables (e.g., ETHERSCAN_KEY)
            lambda: os.getenv(f'{self._scanners[scanner_id].name.upper().replace(" ", "_")}_KEY'),
            # 2. Fallback: Scanner ID-based variables (e.g., ETH_KEY) - for backward compatibility
            lambda: os.getenv(f'{scanner_id.upper()}_KEY'),
            lambda: os.getenv(f'{scanner_id.upper()}_API_KEY'),
            # 3. Generic patterns
            lambda: os.getenv(f'SCANNER_{scanner_id.upper()}_KEY'),
            lambda: os.getenv(f'API_KEY_{scanner_id.upper()}'),
            # 4. Already set in scanner config
            lambda: self._scanners[scanner_id].api_key,
        ]

        for strategy in strategies:
            try:
                api_key = strategy()
                if api_key:
                    return api_key
            except Exception:
                continue

        return None

    def register_scanner(self, scanner_id: str, config_data: dict[str, Any]) -> None:
        """Dynamically register a new scanner."""
        try:
            networks_any: Any = config_data.get('supported_networks', ['main'])
            networks_list: list[str]
            if isinstance(networks_any, set):
                networks_list = list(cast(set[str], networks_any))
            else:
                networks_list = cast(list[str], networks_any)

            scanner_config = ScannerConfig(
                name=config_data['name'],
                base_domain=config_data['base_domain'],
                currency=config_data['currency'],
                supported_networks=set(networks_list),
                requires_api_key=cast(bool, config_data.get('requires_api_key', True)),
                special_config=cast(dict[str, Any], config_data.get('special_config', {})),
            )

            self._scanners[scanner_id] = scanner_config

            # Try to load API key for new scanner
            api_key = self._get_api_key_for_scanner(scanner_id)
            if api_key:
                scanner_config.api_key = api_key

            logger.info(f'Registered new scanner: {scanner_id} ({scanner_config.name})')

        except KeyError as e:
            raise ValueError(f'Invalid scanner configuration for {scanner_id}: missing {e}') from e

    def get_scanner_config(self, scanner_id: str) -> ScannerConfig:
        """Get configuration for a specific scanner."""
        if scanner_id not in self._scanners:
            available = ', '.join(self._scanners.keys())
            raise ValueError(f'Unknown scanner "{scanner_id}". Available: {available}')
        return self._scanners[scanner_id]

    def get_api_key(self, scanner_id: str) -> str:
        """Get API key for a scanner with validation.

        After Etherscan V2 API migration, BSC/Polygon/Arbitrum/Base/Optimism
        all use ETHERSCAN_KEY as fallback.
        """
        config = self.get_scanner_config(scanner_id)

        # If key is already set, use it
        if config.api_key:
            return config.api_key

        # V2 API scanners can use ETHERSCAN_KEY as fallback
        v2_scanners = {'bsc', 'polygon', 'arbitrum', 'base', 'optimism'}
        if scanner_id in v2_scanners:
            # Try ETHERSCAN_KEY as fallback for V2 API scanners
            import os

            etherscan_key = os.getenv('ETHERSCAN_KEY')
            if etherscan_key:
                return etherscan_key

        if config.requires_api_key:
            suggestions = self._get_api_key_suggestions(scanner_id)
            # Add ETHERSCAN_KEY to suggestions for V2 scanners
            if scanner_id in v2_scanners and 'ETHERSCAN_KEY' not in suggestions:
                suggestions.insert(0, 'ETHERSCAN_KEY')
            raise ValueError(
                f'API key required for {config.name}. '
                f'Set one of these environment variables: {", ".join(suggestions)}'
            )

        return ''

    def _get_api_key_suggestions(self, scanner_id: str) -> list[str]:
        """Get suggestions for API key environment variable names."""
        scanner_name = self._scanners[scanner_id].name.upper().replace(' ', '_')
        return [
            f'{scanner_name}_KEY',  # Primary format: ETHERSCAN_KEY
            f'{scanner_id.upper()}_KEY',  # Fallback: ETH_KEY
            f'{scanner_id.upper()}_API_KEY',  # Alternative: ETH_API_KEY
            f'SCANNER_{scanner_id.upper()}_KEY',  # Generic: SCANNER_ETH_KEY
        ]

    def validate_network(self, scanner_id: str, network: str) -> str:
        """Validate and normalize network name for a scanner."""
        config = self.get_scanner_config(scanner_id)

        # Network aliases
        network_aliases = {
            'mainnet': 'main',
            'testnet': 'test',
        }

        normalized_network = network_aliases.get(network, network)

        if normalized_network not in config.supported_networks:
            available = ', '.join(sorted(config.supported_networks))
            raise ValueError(
                f'Network "{network}" not supported by {config.name}. '
                f'Available networks: {available}'
            )

        return normalized_network

    def get_supported_scanners(self) -> list[str]:
        """Get list of all supported scanner names."""
        return list(self._scanners.keys())

    def get_scanner_networks(self, scanner_id: str) -> set[str]:
        """Get supported networks for a specific scanner."""
        return self.get_scanner_config(scanner_id).supported_networks.copy()

    def create_client_config(self, scanner_id: str, network: str = 'main') -> dict[str, str]:
        """Create configuration dict for Client initialization."""
        validated_network = self.validate_network(scanner_id, network)
        api_key = self.get_api_key(scanner_id)

        return {
            'api_key': api_key,
            'api_kind': scanner_id,
            'network': validated_network,
        }

    def list_all_configurations(self) -> dict[str, dict[str, Any]]:
        """Get overview of all scanner configurations."""
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
        lines = [
            '# aiochainscan API Keys Configuration',
            '# Copy this file to .env and fill in your API keys',
            '# You only need keys for the scanners you plan to use',
            '',
        ]

        for scanner_id, config in self._scanners.items():
            if config.requires_api_key:
                # Use primary format: scanner name + _KEY (e.g., ETHERSCAN_KEY)
                scanner_name = config.name.upper().replace(' ', '_')
                primary_var = f'{scanner_name}_KEY'
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


# Global configuration manager instance
config_manager = ConfigurationManager()


# Backward compatibility - expose the same interface as before
class ChainScanConfig:
    """Backward compatibility wrapper."""

    def __init__(self) -> None:
        self._manager = config_manager

    def get_scanner_config(self, scanner: str) -> ScannerConfig:
        return self._manager.get_scanner_config(scanner)

    def get_api_key(self, scanner: str) -> str | None:
        try:
            return self._manager.get_api_key(scanner)
        except ValueError:
            config = self._manager.get_scanner_config(scanner)
            if not config.requires_api_key:
                return ''
            raise

    def validate_network(self, scanner: str, network: str) -> str:
        return self._manager.validate_network(scanner, network)

    def get_supported_scanners(self) -> list[str]:
        return self._manager.get_supported_scanners()

    def get_scanner_networks(self, scanner: str) -> set[str]:
        return self._manager.get_scanner_networks(scanner)

    def create_client_config(self, scanner: str, network: str = 'main') -> dict[str, str]:
        return self._manager.create_client_config(scanner, network)

    def list_all_configurations(self) -> dict[str, dict[str, Any]]:
        return self._manager.list_all_configurations()


# Global instance for backward compatibility
config = ChainScanConfig()


# Export new advanced interface
__all__ = ['ConfigurationManager', 'ScannerConfig', 'ChainScanConfig', 'config', 'config_manager']
