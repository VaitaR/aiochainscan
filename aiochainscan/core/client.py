"""
Unified client for blockchain scanner APIs.
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Literal

import httpx

if TYPE_CHECKING:
    import polars as pl

from ..chain_registry import get_chain_info, resolve_chain_id
from ..config import config as global_config
from ..ports.rate_limiter import RateLimiter, RetryPolicy
from ..scanners import get_scanner_class
from ..scanners.base import Scanner
from ..url_builder import UrlBuilder
from .method import Method

# Strict type aliases for scanner and network names (defined after imports)
ScannerName = Literal['etherscan', 'blockscout', 'blockscout_v2']
NetworkName = Literal[
    'ethereum',
    'mainnet',
    'goerli',
    'sepolia',
    'polygon',
    'arbitrum',
    'optimism',
    'base',
    'bsc',
    'gnosis',
    'zksync',
    'scroll',
    'linea',
    'celo',
]


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
        timeout: float | httpx.Timeout | None = 10.0,
        proxy: str | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
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
            timeout: Request timeout in seconds or httpx.Timeout instance
            proxy: Proxy URL
            rate_limiter: Rate limiter implementation (default: AioLimiterAdapter)
            retry_policy: Retry policy implementation (default: TenacityRetryAdapter)
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

        # Store additional config
        self._timeout = timeout
        self._proxy = proxy
        self._rate_limiter = rate_limiter
        self._retry_policy = retry_policy

        # Create Network instance owned by this client for connection pooling
        from ..network import Network

        self._network = Network(
            url_builder=self._url_builder,
            timeout=timeout,
            proxy=proxy,
            rate_limiter=rate_limiter,
            retry_policy=retry_policy,
        )

        # Get scanner class and create instance with shared network client
        scanner_class = get_scanner_class(scanner_name, scanner_version)
        # Use chain_id to resolve the correct network name for this scanner
        scanner_network = self._get_scanner_network_name(scanner_name, scanner_version, network)
        self._scanner = scanner_class(
            api_key, scanner_network, self._url_builder, chain_id, network_client=self._network
        )

    @classmethod
    def from_config(
        cls,
        scanner_name: ScannerName | str,
        network: NetworkName | str | int,
        scanner_version: str | None = None,
        timeout: float | httpx.Timeout | None = 10.0,
        proxy: str | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> 'ChainscanClient':
        """
        Create client using unified chain-based configuration.

        Args:
            scanner_name: Scanner implementation ('etherscan', 'blockscout')
            network: Chain name/ID ('ethereum', 'base', 1, 8453)
            scanner_version: Scanner version ('v1', 'v2'). If None, uses default:
                - 'v2' for etherscan (recommended)
                - 'v1' for all other scanners
            timeout: Request timeout in seconds or httpx.Timeout instance
            proxy: Proxy URL
            rate_limiter: Rate limiter implementation
            retry_policy: Retry policy implementation

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
            if scanner_name == 'etherscan' or scanner_name == 'blockscout_v2':
                scanner_version = 'v2'
            else:
                scanner_version = 'v1'

        # Handle blockscout_v2 special case
        actual_scanner_name = scanner_name
        if scanner_name == 'blockscout_v2':
            actual_scanner_name = 'blockscout'
            scanner_version = 'v2'

        # Resolve chain_id from network name/id
        chain_id = resolve_chain_id(network)

        # Get API key using existing config system
        # For backward compatibility, map scanner names to their config IDs
        scanner_id_map = {
            'blockscout': 'blockscout_eth',
            'blockscout_v2': 'blockscout_eth',  # BlockScout V2 uses same config
            'etherscan': 'eth',
            'moralis': 'moralis',
            'routscan': 'routscan_mode',
        }
        scanner_id = scanner_id_map.get(scanner_name, scanner_name)
        # Use the original network parameter for config lookup, not the resolved chain name
        # Ensure network is a string for config lookup
        network_str = str(network) if not isinstance(network, str) else network

        # Normalize network aliases for different scanners (for config lookup only)
        # Different scanners use different naming conventions for the same networks
        network_aliases: dict[str, dict[str, str]] = {
            'etherscan': {'ethereum': 'main', 'eth': 'main'},
            'blockscout': {'ethereum': 'eth', 'main': 'eth'},
            'blockscout_v2': {'main': 'ethereum'},
        }
        config_network = network_str  # Preserve original for client property
        if scanner_name in network_aliases:
            aliases = network_aliases[scanner_name]
            config_network = aliases.get(network_str, network_str)

        # For blockscout_v2, we don't need config validation - it handles its own networks
        if scanner_name == 'blockscout_v2':
            api_key = ''  # BlockScout V2 doesn't require API key
        else:
            client_config = global_config.create_client_config(scanner_id, config_network)
            api_key = client_config['api_key']

        # Map scanner_name to appropriate api_kind for UrlBuilder
        # For backward compatibility, map scanner names to their api_kind equivalents
        api_kind_map = {
            'etherscan': 'eth',
            'blockscout': 'blockscout_eth',
            'blockscout_v2': 'blockscout_eth',
            'moralis': 'moralis',
            'routscan': 'routscan_mode',
        }

        api_kind = api_kind_map.get(scanner_name, scanner_name)

        return cls(
            scanner_name=actual_scanner_name,
            scanner_version=scanner_version,
            api_kind=api_kind,  # Use mapped api_kind for UrlBuilder compatibility
            network=network_str,  # Preserve original network value
            api_key=api_key,
            chain_id=chain_id,  # Pass chain_id to scanner
            timeout=timeout,
            proxy=proxy,
            rate_limiter=rate_limiter,
            retry_policy=retry_policy,
        )

    def _get_scanner_network_name(
        self, scanner_name: str, scanner_version: str, network: str
    ) -> str:
        """
        Get the correct network name for a specific scanner.

        Different scanners use different naming conventions for the same networks.
        This method maps the unified network name to scanner-specific names.

        Args:
            scanner_name: Name of the scanner (e.g., 'etherscan', 'blockscout')
            scanner_version: Version of the scanner (e.g., 'v1', 'v2')
            network: Unified network name (e.g., 'ethereum', 'polygon', 1)

        Returns:
            Scanner-specific network name
        """
        # Network aliases for different scanners
        # blockscout v1 uses 'eth', v2 uses 'ethereum'
        if scanner_name == 'blockscout' and scanner_version == 'v1':
            # v1 uses 'eth' for Ethereum mainnet
            if network in ('ethereum', 'main'):
                return 'eth'
        elif scanner_name == 'blockscout' and scanner_version == 'v2':
            # v2 uses 'ethereum' for Ethereum mainnet
            if network == 'main':
                return 'ethereum'
        elif scanner_name == 'etherscan' and network == 'ethereum':
            # Etherscan uses 'main' for Ethereum mainnet
            return 'main'

        # For other cases, use the network name as-is
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
        """Close the network client and release resources."""
        if self._network is not None:
            await self._network.close()
            self._network = None  # type: ignore[assignment]

    # Context manager support
    async def __aenter__(self) -> 'ChainscanClient':
        """Enter async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context manager, closing the client."""
        await self.close()

    # =========================================================================
    # PUBLIC API - Typed convenience methods with autocomplete support
    # =========================================================================

    async def get_balance(self, address: str, tag: str = 'latest') -> str:
        """Get account balance in Wei as string.

        Args:
            address: Wallet address to check
            tag: Block tag ('latest', 'earliest', or block number) - Etherscan only

        Returns:
            Balance in Wei as string
        """
        params: dict[str, Any] = {'address': address}
        # Only pass tag for Etherscan (other scanners may not support it)
        if self.scanner_name == 'etherscan':
            params['tag'] = tag
        return await self.call(Method.ACCOUNT_BALANCE, **params)

    async def get_transactions(
        self,
        address: str,
        start_block: int = 0,
        end_block: int | None = None,
        page: int = 1,
        offset: int = 100,
    ) -> list[dict]:
        """Get list of normal transactions for address.

        Args:
            address: Wallet address
            start_block: Starting block number (Etherscan only)
            end_block: Ending block number (Etherscan only, None for latest)
            page: Page number for pagination (Etherscan only)
            offset: Number of transactions per page (Etherscan only, max 10000)

        Returns:
            List of transaction dictionaries
        """
        params: dict[str, Any] = {'address': address}
        # Only pass pagination params for Etherscan (blockscout_v2 doesn't support them)
        if self.scanner_name == 'etherscan':
            params['startblock'] = start_block
            params['page'] = page
            params['offset'] = offset
            if end_block is not None:
                params['endblock'] = end_block
        return await self.call(Method.ACCOUNT_TRANSACTIONS, **params)

    async def get_token_transfers(
        self,
        address: str,
        contract_address: str | None = None,
        start_block: int = 0,
        end_block: int | None = None,
    ) -> list[dict]:
        """Get ERC20 token transfers for address.

        Args:
            address: Wallet address
            contract_address: Filter by specific token contract (optional, Etherscan only)
            start_block: Starting block number (Etherscan only)
            end_block: Ending block number (Etherscan only, None for latest)

        Returns:
            List of token transfer dictionaries
        """
        params: dict[str, Any] = {'address': address}
        # Only pass extra params for Etherscan
        if self.scanner_name == 'etherscan':
            params['startblock'] = start_block
            if contract_address:
                params['contractaddress'] = contract_address
            if end_block:
                params['endblock'] = end_block
        return await self.call(Method.ACCOUNT_ERC20_TRANSFERS, **params)

    async def get_token_portfolio(self, address: str) -> list[dict]:
        """Get all ERC20 tokens held by address.

        Args:
            address: Wallet address

        Returns:
            List of token holding dictionaries
        """
        return await self.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address=address)

    async def get_contract_abi(self, address: str) -> str:
        """Get contract ABI as JSON string.

        Args:
            address: Contract address

        Returns:
            Contract ABI as JSON string
        """
        return await self.call(Method.CONTRACT_ABI, address=address)

    # =========================================================================
    # STREAMING API - Memory-efficient iteration
    # =========================================================================

    async def iter_transactions(
        self,
        address: str,
        batch_size: int = 1000,
    ) -> AsyncIterator[dict]:
        """
        Stream transactions with O(1) memory usage.

        Yields transactions one by one as they are fetched,
        perfect for processing large wallets without OOM.

        Args:
            address: Wallet address to fetch transactions for
            batch_size: Number of transactions to fetch per API call (max 10000, Etherscan only)

        Yields:
            Transaction dictionaries one at a time

        Example:
            ```python
            async for tx in client.iter_transactions(address):
                await db.save(tx)
            ```
        """
        # BlockScout V2 has special pagination with next_page_params
        if self.scanner_name == 'blockscout' and self.scanner_version == 'v2':
            # Import here to avoid circular dependency
            from ..exceptions import ChainscanClientApiError, ChainscanNetworkError
            from ..scanners.blockscout_v2 import BlockScoutV2Scanner

            scanner = self._scanner
            if not isinstance(scanner, BlockScoutV2Scanner):
                raise TypeError(f'Expected BlockScoutV2Scanner, got {type(scanner).__name__}')

            # Build initial request params
            spec = scanner.SPECS[Method.ACCOUNT_TRANSACTIONS]
            url = scanner._build_url(spec, address=address)
            query_params = scanner._build_query_params(spec, address=address)

            # Import aiohttp for raw API calls
            import aiohttp

            headers = {
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate',
            }

            # Pagination loop using next_page_params
            while True:
                try:
                    async with (
                        aiohttp.ClientSession() as session,
                        session.get(
                            url,
                            params=query_params if query_params else None,
                            headers=headers,
                        ) as response,
                    ):
                        response.raise_for_status()
                        raw_response = await response.json()
                except aiohttp.ClientResponseError as e:
                    raise ChainscanClientApiError(
                        f'BlockScout V2 API error ({e.status})',
                        f'{e.message} - URL: {url}',
                    ) from e
                except aiohttp.ClientError as e:
                    raise ChainscanNetworkError(
                        f'BlockScout V2 network error: {e}',
                        retryable=True,
                    ) from e
                except Exception as e:
                    raise ChainscanNetworkError(
                        f'BlockScout V2 unexpected error: {e}',
                        retryable=False,
                    ) from e

                # Extract items from response
                items = raw_response.get('items', [])
                for tx in items:
                    yield tx

                # Check for next page
                next_page_params = raw_response.get('next_page_params')
                if not next_page_params:
                    break

                # Update query params with next_page_params for next iteration
                query_params = {**query_params, **next_page_params}

            return

        # For Etherscan, use page-based pagination
        if self.scanner_name == 'etherscan':
            page = 1
            while True:
                txs = await self.call(
                    Method.ACCOUNT_TRANSACTIONS,
                    address=address,
                    page=page,
                    offset=batch_size,
                )

                # Handle both list and dict responses
                items = txs if isinstance(txs, list) else txs.get('items', [])
                if not items:
                    break

                for tx in items:
                    yield tx

                if len(items) < batch_size:
                    break

                page += 1
            return

        # For other scanners (e.g., blockscout_v1), fetch once (no pagination)
        txs = await self.call(
            Method.ACCOUNT_TRANSACTIONS,
            address=address,
        )
        items = txs if isinstance(txs, list) else txs.get('items', [])
        for tx in items:
            yield tx

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

    # =========================================================================
    # DATAFRAME API - Polars integration for data analysis
    # =========================================================================

    async def get_transactions_df(self, address: str) -> 'pl.DataFrame':
        """
        Get transactions as a Polars DataFrame.

        Perfect for data analysis and AI agents.
        Requires: pip install aiochainscan[data]

        Returns:
            pl.DataFrame with columns: hash, block_number, from_address,
            to_address, value_wei, value_eth, gas_used, timestamp
        """
        from aiochainscan.services.analytics import transactions_to_dataframe

        txs = await self.call(Method.ACCOUNT_TRANSACTIONS, address=address)
        items = txs if isinstance(txs, list) else txs.get('items', [])
        return await transactions_to_dataframe(items)

    async def get_token_portfolio_df(self, address: str) -> 'pl.DataFrame':
        """
        Get token portfolio as a Polars DataFrame.

        Requires: pip install aiochainscan[data]

        Returns:
            pl.DataFrame with columns: symbol, name, contract_address, balance, decimals
        """
        from aiochainscan.services.analytics import token_portfolio_to_dataframe

        tokens = await self.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address=address)
        items = tokens if isinstance(tokens, list) else tokens.get('items', [])
        return await token_portfolio_to_dataframe(items)

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
