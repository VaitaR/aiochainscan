"""
Unified client for blockchain scanner APIs.
"""

from asyncio import AbstractEventLoop
from contextlib import AbstractAsyncContextManager
from typing import Any

from aiohttp import ClientTimeout
from aiohttp_retry import RetryOptionsBase

from ..chains import ChainInfo
from ..scanners import get_scanner_class
from ..scanners.base import Scanner
from ..url_builder import UrlBuilder
from .method import Method


class ChainscanClient:
    """
    Unified client for accessing different blockchain scanner APIs.

    This client provides a single interface for calling logical methods
    across different scanner implementations (Etherscan, BlockScout, Moralis),
    automatically handling API key management and URL construction.

    Example:
        ```python
        # Using ChainProvider (recommended)
        from aiochainscan import ChainProvider
        client = ChainProvider.etherscan(chain_id=1)

        # Direct instantiation with ChainInfo
        from aiochainscan.chains import resolve_chain
        chain_info = resolve_chain(1)  # Ethereum
        client = ChainscanClient('etherscan', 'v2', chain_info, 'your_api_key')

        # Make unified API calls
        balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
        ```
    """

    def __init__(
        self,
        scanner_name: str,
        scanner_version: str,
        chain_info: ChainInfo,
        api_key: str,
        loop: AbstractEventLoop | None = None,
        timeout: ClientTimeout | None = None,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager[Any] | None = None,
        retry_options: RetryOptionsBase | None = None,
    ):
        """
        Initialize the unified client.

        Args:
            scanner_name: Scanner implementation name (e.g., 'etherscan', 'blockscout', 'moralis')
            scanner_version: Scanner version (e.g., 'v1', 'v2')
            chain_info: ChainInfo object with chain metadata
            api_key: API key for authentication (empty string if not required)
            loop: Event loop instance
            timeout: Request timeout configuration
            proxy: Proxy URL
            throttler: Rate limiting throttler
            retry_options: Retry configuration
        """
        self.scanner_name = scanner_name
        self.scanner_version = scanner_version
        self.chain_info = chain_info
        self.api_key = api_key

        # Resolve legacy api_kind and network for UrlBuilder compatibility
        api_kind = chain_info.etherscan_api_kind or 'eth'
        network = chain_info.etherscan_network_name or 'main'

        # Build URL builder (reusing existing infrastructure)
        self._url_builder = UrlBuilder(api_key, api_kind, network)

        # Get scanner class and create instance
        scanner_class = get_scanner_class(scanner_name, scanner_version)
        self._scanner = scanner_class(api_key, chain_info, self._url_builder)

        # Store additional config for potential future use
        self._loop = loop
        self._timeout = timeout
        self._proxy = proxy
        self._throttler = throttler
        self._retry_options = retry_options

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
        return self.chain_info.native_currency

    @property
    def chain_id(self) -> int:
        """Get the EIP-155 chain ID."""
        return self.chain_info.chain_id

    @property
    def chain_name(self) -> str:
        """Get the canonical chain name."""
        return self.chain_info.name

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
            f'{self.chain_info.display_name} [chain_id={self.chain_info.chain_id}])'
        )

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"ChainscanClient(scanner_name='{self.scanner_name}', "
            f"scanner_version='{self.scanner_version}', "
            f'chain_id={self.chain_info.chain_id}, '
            f"chain_name='{self.chain_info.name}')"
        )
