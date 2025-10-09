"""
Unified client for blockchain scanner APIs.
"""

from asyncio import AbstractEventLoop
from contextlib import AbstractAsyncContextManager
from typing import Any

from aiohttp import ClientTimeout
from aiohttp_retry import RetryOptionsBase

from ..chain_registry import get_chain_info, resolve_chain_id
from ..config import config as global_config
from ..scanners import get_scanner_class
from ..scanners.base import Scanner
from ..url_builder import UrlBuilder
from .method import Method


class ChainscanClient:
    """
    Unified client for accessing different blockchain scanner APIs.

    This client provides a single interface for calling logical methods
    across different scanner implementations (Etherscan, BlockScout, Moralis, etc.),
    automatically handling API key management and URL construction.

    Example:
        ```python
        # Using configuration system (version defaults to 'v2' for etherscan)
        client = ChainscanClient.from_config('etherscan', network='ethereum')

        # Direct instantiation
        client = ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'your_api_key')

        # Make unified API calls
        balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
        ```
    """

    def __init__(
        self,
        scanner_name: str,
        scanner_version: str,
        api_kind: str,
        network: str,
        api_key: str,
        chain_id: int | None = None,
        loop: AbstractEventLoop | None = None,
        timeout: ClientTimeout | None = None,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager[Any] | None = None,
        retry_options: RetryOptionsBase | None = None,
    ):
        """
        Initialize the unified client.

        Args:
            scanner_name: Scanner implementation name (e.g., 'etherscan', 'blockscout')
            scanner_version: Scanner version (e.g., 'v1', 'v2')
            api_kind: API kind for URL building (e.g., 'eth', 'base')
            network: Network name (e.g., 'main', 'test')
            api_key: API key for authentication
            chain_id: Chain ID for the network (optional, auto-resolved from network)
            loop: Event loop instance
            timeout: Request timeout configuration
            proxy: Proxy URL
            throttler: Rate limiting throttler
            retry_options: Retry configuration
        """
        self.scanner_name = scanner_name
        self.scanner_version = scanner_version
        self.api_kind = api_kind
        self.network = network
        self.api_key = api_key
        self.chain_id = chain_id or resolve_chain_id(network)

        # Map network to appropriate network parameter for UrlBuilder
        # UrlBuilder expects 'main' for Ethereum mainnet, not 'ethereum'
        chain_info = get_chain_info(self.chain_id)
        network_for_urlbuilder = chain_info['name'] if chain_info['name'] != 'ethereum' else 'main'

        # Build URL builder (reusing existing infrastructure)
        self._url_builder = UrlBuilder(api_key, api_kind, network_for_urlbuilder)

        # Get scanner class and create instance
        scanner_class = get_scanner_class(scanner_name, scanner_version)
        # Use chain_id to resolve the correct network name for this scanner
        scanner_network = self._get_scanner_network_name(scanner_name, network)
        self._scanner = scanner_class(api_key, scanner_network, self._url_builder, chain_id)

        # Store additional config for potential future use
        self._loop = loop
        self._timeout = timeout
        self._proxy = proxy
        self._throttler = throttler
        self._retry_options = retry_options

    @classmethod
    def from_config(
        cls,
        scanner_name: str,
        network: str | int,
        scanner_version: str | None = None,
        loop: AbstractEventLoop | None = None,
        timeout: ClientTimeout | None = None,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager[Any] | None = None,
        retry_options: RetryOptionsBase | None = None,
    ) -> 'ChainscanClient':
        """
        Create client using unified chain-based configuration.

        Args:
            scanner_name: Scanner implementation ('etherscan', 'blockscout')
            network: Chain name/ID ('ethereum', 'base', 1, 8453)
            scanner_version: Scanner version ('v1', 'v2'). If None, uses default:
                - 'v2' for etherscan (recommended)
                - 'v1' for all other scanners
            loop: Event loop instance
            timeout: Request timeout configuration
            proxy: Proxy URL
            throttler: Rate limiting throttler
            retry_options: Retry configuration

        Returns:
            Configured ChainscanClient instance

        Example:
            ```python
            # Etherscan v2 for Ethereum (version defaults to 'v2')
            client = ChainscanClient.from_config('etherscan', 'ethereum')

            # BlockScout v1 for Polygon (version defaults to 'v1')
            client = ChainscanClient.from_config('blockscout', 'polygon')

            # Explicit version specification
            client = ChainscanClient.from_config('moralis', 'ethereum', 'v1')

            # Works with chain_id too
            client = ChainscanClient.from_config('etherscan', 8453)
            ```
        """
        # Determine default scanner version if not provided
        if scanner_version is None:
            scanner_version = 'v2' if scanner_name == 'etherscan' else 'v1'

        # Resolve chain_id from network name/id
        chain_id = resolve_chain_id(network)

        # Get API key using existing config system
        # For backward compatibility, map scanner names to their config IDs
        scanner_id_map = {
            'blockscout': 'blockscout_eth',
            'etherscan': 'eth',
            'moralis': 'moralis',
            'routscan': 'routscan_mode',
        }
        scanner_id = scanner_id_map.get(scanner_name, scanner_name)
        # Use the original network parameter for config lookup, not the resolved chain name
        # Ensure network is a string for config lookup
        network_str = str(network) if not isinstance(network, str) else network
        client_config = global_config.create_client_config(scanner_id, network_str)

        # Map scanner_name to appropriate api_kind for UrlBuilder
        # For backward compatibility, map scanner names to their api_kind equivalents
        api_kind_map = {
            'etherscan': 'eth',
            'blockscout': 'blockscout_eth',
            'moralis': 'moralis',
            'routscan': 'routscan_mode',
        }

        api_kind = api_kind_map.get(scanner_name, scanner_name)

        return cls(
            scanner_name=scanner_name,
            scanner_version=scanner_version,
            api_kind=api_kind,  # Use mapped api_kind for UrlBuilder compatibility
            network=network_str,  # Use string version of network
            api_key=client_config['api_key'],
            chain_id=chain_id,  # Pass chain_id to scanner
            loop=loop,
            timeout=timeout,
            proxy=proxy,
            throttler=throttler,
            retry_options=retry_options,
        )

    def _get_scanner_network_name(self, scanner_name: str, network: str) -> str:
        """
        Get the correct network name for a specific scanner.

        Different scanners use different naming conventions for the same networks.
        This method maps the unified network name to scanner-specific names.

        Args:
            scanner_name: Name of the scanner (e.g., 'etherscan', 'blockscout')
            network: Unified network name (e.g., 'ethereum', 'polygon', 1)

        Returns:
            Scanner-specific network name
        """
        # For Etherscan, map 'ethereum' to 'main' for backward compatibility
        if scanner_name == 'etherscan' and network == 'ethereum':
            return 'main'

        # For other scanners, use the network name as-is
        return network

    async def call(self, method: Method, **params: Any) -> Any:
        """
        Execute a logical method call on the scanner.

        Args:
            method: Logical method to execute (from Method enum)
            **params: Parameters for the method call

        Returns:
            Parsed response from the API

        Raises:
            ValueError: If method is not supported by the scanner
            Various API and network errors

        Example:
            ```python
            # Get account balance
            balance = await client.call(
                Method.ACCOUNT_BALANCE,
                address='0x742d35Cc6634C0532925a3b8D9Fa7a3D91'
            )

            # Get transaction list with pagination
            txs = await client.call(
                Method.ACCOUNT_TRANSACTIONS,
                address='0x742d35Cc6634C0532925a3b8D9Fa7a3D91',
                page=1,
                offset=100
            )
            ```
        """
        return await self._scanner.call(method, **params)

    def supports_method(self, method: Method) -> bool:
        """
        Check if the current scanner supports a logical method.

        Args:
            method: Method to check

        Returns:
            True if supported, False otherwise
        """
        return self._scanner.supports_method(method)

    def get_supported_methods(self) -> list[Method]:
        """
        Get list of all methods supported by the current scanner.

        Returns:
            List of supported Method enum values
        """
        return self._scanner.get_supported_methods()

    @property
    def scanner_info(self) -> str:
        """Get information about the current scanner."""
        return str(self._scanner)

    @property
    def currency(self) -> str:
        """Get the currency symbol for the current network."""
        return self._url_builder.currency

    async def close(self) -> None:
        """Close any open connections (for compatibility)."""
        # For now, this is a no-op since we create Network instances per request
        # In future, we might cache Network instances and need to close them
        pass

    @classmethod
    def get_available_scanners(cls) -> dict[tuple[str, str], type[Scanner]]:
        """
        Get all available scanner implementations.

        Returns:
            Dictionary mapping (name, version) to scanner classes
        """
        from ..scanners import list_scanners

        return list_scanners()

    @classmethod
    def list_scanner_capabilities(cls) -> dict[str, dict[str, Any]]:
        """
        Get overview of all scanner capabilities.

        Returns:
            Dictionary with scanner information and supported methods
        """
        from ..scanners import list_scanners

        result = {}
        for (name, version), scanner_class in list_scanners().items():
            key = f'{name}_{version}'
            result[key] = {
                'name': scanner_class.name,
                'version': scanner_class.version,
                'networks': sorted(scanner_class.supported_networks),
                'auth_mode': scanner_class.auth_mode,
                'auth_field': scanner_class.auth_field,
                'supported_methods': [str(method) for method in scanner_class.SPECS],
                'method_count': len(scanner_class.SPECS),
            }

        return result

    def __str__(self) -> str:
        """String representation of the client."""
        return (
            f'ChainscanClient({self.scanner_name} {self.scanner_version}, '
            f'{self.api_kind} {self.network})'
        )

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"ChainscanClient(scanner_name='{self.scanner_name}', "
            f"scanner_version='{self.scanner_version}', api_kind='{self.api_kind}', "
            f"network='{self.network}')"
        )
