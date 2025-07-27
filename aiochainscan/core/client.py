"""
Unified client for blockchain scanner APIs.
"""

from asyncio import AbstractEventLoop
from contextlib import AbstractAsyncContextManager
from typing import Any

from aiohttp import ClientTimeout
from aiohttp_retry import RetryOptionsBase

from ..config import config as global_config
from ..scanners import get_scanner_class
from ..scanners.base import Scanner
from ..url_builder import UrlBuilder
from .method import Method


class ChainscanClient:
    """
    Unified client for accessing different blockchain scanner APIs.

    This client provides a single interface for calling logical methods
    across different scanner implementations (Etherscan, OKLink, etc.),
    automatically handling API key management and URL construction.

    Example:
        ```python
        # Using configuration system
        client = ChainscanClient.from_config('etherscan', 'v1', 'eth', 'main')

        # Direct instantiation
        client = ChainscanClient('etherscan', 'v1', 'eth', 'main', 'your_api_key')

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
        loop: AbstractEventLoop | None = None,
        timeout: ClientTimeout | None = None,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager | None = None,
        retry_options: RetryOptionsBase | None = None,
    ):
        """
        Initialize the unified client.

        Args:
            scanner_name: Scanner implementation name (e.g., 'etherscan', 'oklink')
            scanner_version: Scanner version (e.g., 'v1', 'v2')
            api_kind: API kind for URL building (e.g., 'eth', 'xlayer')
            network: Network name (e.g., 'main', 'test')
            api_key: API key for authentication
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

        # Build URL builder (reusing existing infrastructure)
        self._url_builder = UrlBuilder(api_key, api_kind, network)

        # Get scanner class and create instance
        scanner_class = get_scanner_class(scanner_name, scanner_version)
        self._scanner = scanner_class(api_key, network, self._url_builder)

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
        scanner_version: str,
        scanner_id: str,
        network: str = 'main',
        loop: AbstractEventLoop | None = None,
        timeout: ClientTimeout | None = None,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager | None = None,
        retry_options: RetryOptionsBase | None = None,
    ) -> 'ChainscanClient':
        """
        Create client using the existing configuration system.

        Args:
            scanner_name: Scanner implementation ('etherscan', 'oklink')
            scanner_version: Scanner version ('v1', 'v2')
            scanner_id: Scanner ID for config lookup ('eth', 'xlayer')
            network: Network name ('main', 'test', etc.)
            loop: Event loop instance
            timeout: Request timeout configuration
            proxy: Proxy URL
            throttler: Rate limiting throttler
            retry_options: Retry configuration

        Returns:
            Configured ChainscanClient instance

        Example:
            ```python
            # Etherscan v1 for Ethereum mainnet
            client = ChainscanClient.from_config('etherscan', 'v1', 'eth', 'main')

            # OKLink v1 for XLayer
            client = ChainscanClient.from_config('oklink', 'v1', 'xlayer', 'main')
            ```
        """
        # Use existing config system to get API key and validate network
        client_config = global_config.create_client_config(scanner_id, network)

        return cls(
            scanner_name=scanner_name,
            scanner_version=scanner_version,
            api_kind=client_config['api_kind'],
            network=client_config['network'],
            api_key=client_config['api_key'],
            loop=loop,
            timeout=timeout,
            proxy=proxy,
            throttler=throttler,
            retry_options=retry_options,
        )

    async def call(self, method: Method, **params) -> Any:
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

    async def close(self):
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
