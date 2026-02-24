"""
Unified client for blockchain scanner APIs.
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Literal

import httpx

if TYPE_CHECKING:
    import polars as pl

    from ..ports.progress import ProgressCallback
    from ..services.ens_resolver import ENSResolver

from ..chain_registry import get_chain_info, resolve_chain_id
from ..config import config as global_config
from ..domain.contract import SmartContract
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

        # Lazy-initialized ENS resolver
        self._ens_resolver: ENSResolver | None = None

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

        # If network was passed as int (chain_id), resolve it to canonical name
        # This ensures from_config('etherscan', 8453) works correctly
        from aiochainscan.chain_registry import get_chain_name

        network_str = get_chain_name(network) if isinstance(network, int) else str(network)

        # Get API key using existing config system
        # For backward compatibility, map scanner names to their config IDs
        # BlockScout scanner ID is determined by network (not hardcoded to eth)
        if scanner_name == 'blockscout':
            # Map network to appropriate BlockScout config ID
            blockscout_config_map = {
                'ethereum': 'blockscout_eth',
                'eth': 'blockscout_eth',
                'polygon': 'blockscout_polygon',
                'gnosis': 'blockscout_gnosis',
                'optimism': 'blockscout_optimism',
                'base': 'blockscout_base',
            }
            scanner_id = blockscout_config_map.get(network_str, f'blockscout_{network_str}')
        else:
            scanner_id_map = {
                'blockscout_v2': 'blockscout_eth',  # V2 doesn't use config
                'etherscan': 'eth',
                'moralis': 'moralis',
                'routscan': 'routscan_mode',
            }
            scanner_id = scanner_id_map.get(scanner_name, scanner_name)

        # Normalize network aliases for different scanners (for config lookup only)
        # Different scanners use different naming conventions for the same networks
        network_aliases: dict[str, dict[str, str]] = {
            'etherscan': {'ethereum': 'main', 'eth': 'main', 'base': 'main'},
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
        # For blockscout, use the network-specific scanner_id (e.g., blockscout_polygon)
        if scanner_name == 'blockscout':
            api_kind = (
                scanner_id  # Use network-specific ID (blockscout_polygon, blockscout_gnosis, etc.)
            )
        else:
            api_kind_map = {
                'etherscan': 'eth',
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
        result: str = await self.call(Method.ACCOUNT_BALANCE, **params)
        return result

    async def get_transactions(
        self,
        address: str,
        start_block: int = 0,
        end_block: int | None = None,
        page: int = 1,
        offset: int = 100,
    ) -> list[dict[Any, Any]]:
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
        result: list[dict[Any, Any]] = await self.call(Method.ACCOUNT_TRANSACTIONS, **params)
        return result

    async def get_token_transfers(
        self,
        address: str,
        contract_address: str | None = None,
        start_block: int = 0,
        end_block: int | None = None,
    ) -> list[dict[Any, Any]]:
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
        result: list[dict[Any, Any]] = await self.call(Method.ACCOUNT_ERC20_TRANSFERS, **params)
        return result

    async def get_token_portfolio(self, address: str) -> list[dict[Any, Any]]:
        """Get all ERC20 tokens held by address.

        Args:
            address: Wallet address

        Returns:
            List of token holding dictionaries
        """
        result: list[dict[Any, Any]] = await self.call(
            Method.ACCOUNT_TOKEN_PORTFOLIO, address=address
        )
        return result

    async def get_contract_abi(self, address: str) -> str:
        """Get contract ABI as JSON string.

        Args:
            address: Contract address

        Returns:
            Contract ABI as JSON string
        """
        result: str = await self.call(Method.CONTRACT_ABI, address=address)
        return result

    async def get_contract(self, address: str) -> SmartContract:
        """
        Get a SmartContract instance with automatic ABI fetching and Proxy resolution.

        This is the recommended way to interact with smart contracts. The returned
        SmartContract object provides high-level methods for:
        - Iterating through decoded events
        - Iterating through decoded transactions
        - Accessing contract ABI information

        Args:
            address: Contract address

        Returns:
            SmartContract instance ready for use

        Raises:
            ValueError: If contract ABI cannot be fetched

        Example:
            ```python
            # Get USDT contract (automatically resolves proxy)
            usdt = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")

            # Iterate through Transfer events
            async for event in usdt.iter_events("Transfer", limit=100):
                print(f"{event.args['from']} -> {event.args['to']}: {event.args['value']}")

            # Iterate through transactions
            async for tx in usdt.iter_transactions(limit=50):
                print(f"Function: {tx.function_name}, Args: {tx.args}")
            ```
        """
        from ..domain.contract import SmartContract

        return await SmartContract.from_address(address, self)

    # =========================================================================
    # ENS INTEGRATION - Name resolution and reverse lookup
    # =========================================================================

    @property
    def ens(self) -> 'ENSResolver':
        """
        Get ENS resolver instance for name resolution.

        Lazy-initialized on first access. The resolver provides:
        - Forward resolution (name → address)
        - Reverse lookup (address → name)
        - Batch operations
        - Automatic caching

        Returns:
            ENSResolver instance

        Raises:
            ValueError: If ENS is not supported on this network

        Example:
            ```python
            # Access ENS resolver
            address = await client.ens.resolve_name("vitalik.eth")
            name = await client.ens.lookup_address("0xd8dA...")
            ```
        """
        if self._ens_resolver is None:
            from ..services.ens_resolver import ENSResolver

            self._ens_resolver = ENSResolver(self)
        return self._ens_resolver

    async def resolve_name(self, name: str) -> str | None:
        """
        Resolve ENS name to Ethereum address.

        Convenience method that delegates to the ENS resolver.

        Args:
            name: ENS name (e.g., "vitalik.eth")

        Returns:
            Ethereum address or None if not found

        Raises:
            ValueError: If ENS is not supported on this network

        Example:
            ```python
            address = await client.resolve_name("vitalik.eth")
            print(address)  # "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
            ```
        """
        return await self.ens.resolve_name(name)

    async def lookup_address(self, address: str) -> str | None:
        """
        Reverse lookup: Ethereum address to ENS name.

        Convenience method that delegates to the ENS resolver.

        Args:
            address: Ethereum address (e.g., "0xd8dA...")

        Returns:
            ENS name or None if not found

        Raises:
            ValueError: If ENS is not supported on this network

        Example:
            ```python
            name = await client.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
            print(name)  # "vitalik.eth"
            ```
        """
        return await self.ens.lookup_address(address)

    async def resolve_names(self, names: list[str]) -> dict[str, str]:
        """
        Batch resolve multiple ENS names to addresses.

        Resolves names in parallel for efficiency.

        Args:
            names: List of ENS names

        Returns:
            Dict mapping names to addresses (only successful resolutions)

        Example:
            ```python
            result = await client.resolve_names(["vitalik.eth", "uniswap.eth"])
            # {"vitalik.eth": "0xd8dA...", "uniswap.eth": "0x1f98..."}
            ```
        """
        return await self.ens.resolve_names(names)

    async def lookup_addresses(self, addresses: list[str]) -> dict[str, str]:
        """
        Batch reverse lookup multiple addresses to ENS names.

        Performs lookups in parallel for efficiency.

        Args:
            addresses: List of Ethereum addresses

        Returns:
            Dict mapping addresses to names (only successful lookups)

        Example:
            ```python
            result = await client.lookup_addresses([
                "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"
            ])
            # {"0xd8dA...": "vitalik.eth", "0x1f98...": "uniswap.eth"}
            ```
        """
        return await self.ens.lookup_addresses(addresses)

    # =========================================================================
    # STREAMING API - Memory-efficient iteration with optional decoding
    # =========================================================================

    async def iter_transactions(
        self,
        address: str,
        abi: list[dict[str, Any]] | None = None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Iterate through transactions one at a time with optional decoding.

        Memory-efficient streaming approach that fetches and optionally decodes
        transactions in batches, yielding them one by one. Never holds the entire
        dataset in memory, making it ideal for whale addresses with millions of txs.

        Args:
            address: Wallet address to fetch transactions for
            abi: Contract ABI for decoding (optional). If provided, transactions
                 will include 'decoded_func' and 'decoded_data' fields
            from_block: Starting block number (default: 0)
            to_block: Ending block number or 'latest' (default: 'latest')
            batch_size: Number of items to fetch per batch (default: 1000)

        Yields:
            Transaction dictionaries, decoded if ABI is provided

        Example:
            ```python
            # Stream without decoding
            async for tx in client.iter_transactions(whale_address):
                print(f"Hash: {tx['hash']}")

            # Stream with decoding
            abi = json.loads(await client.get_contract_abi(contract_address))
            async for tx in client.iter_transactions(whale_address, abi=abi):
                print(f"Function: {tx['decoded_func']}")
                print(f"Args: {tx['decoded_data']}")
            ```
        """
        # Validate batch_size to prevent infinite loops
        if batch_size < 1:
            raise ValueError(f'batch_size must be at least 1, got {batch_size}')

        # For simple pagination without decoding and no block range, use existing logic
        if abi is None and from_block == 0 and (to_block is None or to_block == 'latest'):
            # Use existing simple pagination (backward compatibility)
            # BlockScout V2 has special pagination with next_page_params
            if self.scanner_name == 'blockscout' and self.scanner_version == 'v2':
                # Import here to avoid circular dependency
                from ..scanners.blockscout_v2 import BlockScoutV2Scanner

                scanner = self._scanner
                if not isinstance(scanner, BlockScoutV2Scanner):
                    raise TypeError(f'Expected BlockScoutV2Scanner, got {type(scanner).__name__}')

                # Build initial request params
                spec = scanner.SPECS[Method.ACCOUNT_TRANSACTIONS]
                url = scanner._build_url(spec, address=address)
                query_params = scanner._build_query_params(spec, address=address)

                headers = {
                    'Accept': 'application/json',
                    'Accept-Encoding': 'gzip, deflate',
                }

                # Pagination loop using next_page_params
                # Uses self._network.request() which has proper retry logic via RetryPolicy
                while True:
                    # self._network.request() wraps calls with retry policy
                    # This ensures retries happen at page-fetch level, not generator level
                    raw_response = await self._network.request(
                        method='GET',
                        url=url,
                        params=query_params if query_params else None,
                        headers=headers,
                    )

                    # Extract items from response (raw_response is already parsed JSON)
                    if isinstance(raw_response, dict):
                        items = raw_response.get('items', [])
                        next_page_params = raw_response.get('next_page_params')
                    else:
                        # Fallback for list responses
                        items = raw_response if isinstance(raw_response, list) else []
                        next_page_params = None

                    for tx in items:
                        yield tx

                    # Check for next page
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
            return

        # Use advanced streaming decoder for decoding and/or block range filtering
        from aiochainscan.services.streaming_decoder import StreamingDecoder

        # Get HTTP client from network
        http_client = self._network._http2

        decoder = StreamingDecoder(
            api_kind=self.api_kind,
            network=self.network,
            api_key=self.api_key,
            http=http_client,  # type: ignore[arg-type]
            endpoint_builder=self._network._url_builder,  # type: ignore[arg-type]
            batch_size=batch_size,
            rate_limiter=self._rate_limiter,
            retry=self._retry_policy,
            telemetry=None,
            max_concurrent=1,
        )

        if abi is not None:
            # Stream with decoding
            async for tx in decoder.stream_transactions(
                address=address,
                abi=abi,
                from_block=from_block,
                to_block=to_block,
            ):
                yield tx
        else:
            # Stream without decoding
            async for batch in decoder._fetch_transaction_batches(
                address=address,
                from_block=from_block,
                to_block=to_block,
            ):
                for tx in batch:
                    yield tx

    # =========================================================================
    # BATCH STREAMING API - Memory-efficient batch iteration for whale addresses
    # =========================================================================

    async def iter_transactions_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: 'ProgressCallback | None' = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Stream transactions in batches for maximum memory efficiency.

        This method yields batches of transactions instead of individual items,
        providing constant memory usage regardless of total dataset size. Perfect
        for whale addresses with millions of transactions.

        Unlike iter_transactions() which yields one item at a time, this yields
        batches of `batch_size` items, allowing you to process large chunks
        efficiently while maintaining constant memory footprint.

        Args:
            address: Wallet address to fetch transactions for
            from_block: Starting block number (default: 0)
            to_block: Ending block number or 'latest' (default: 'latest')
            batch_size: Number of transactions per batch (default: 1000)
            on_progress: Optional callback for progress updates

        Yields:
            Batches of transaction dictionaries (list[dict])

        Example:
            ```python
            # Process 1M transactions using constant memory (~10MB)
            total = 0
            async for batch in client.iter_transactions_streaming(
                whale_address,
                batch_size=1000
            ):
                total += len(batch)
                # Process 1000 transactions at a time
                await bulk_insert_to_database(batch)

            print(f"Processed {total} transactions")
            ```

        Memory Usage:
            - Bulk fetch: 1M txs = ~2GB RAM
            - iter_transactions: 1M txs = ~100MB RAM (yields one at a time)
            - iter_transactions_streaming: 1M txs = ~10MB RAM (yields batches)
        """
        from aiochainscan.services.fetch_all_streaming import (
            fetch_all_transactions_streaming,
        )

        # Get HTTP client from network
        http_client = self._network._http2

        # Convert 'latest' to None for the fetch function
        end_block: int | None = (
            None if to_block == 'latest' else int(to_block) if to_block else None
        )

        async for batch in fetch_all_transactions_streaming(
            address=address,
            start_block=from_block,
            end_block=end_block,
            api_kind=self.api_kind,
            network=self.network,
            api_key=self.api_key,
            http=http_client,  # type: ignore[arg-type]
            endpoint_builder=self._network._url_builder,  # type: ignore[arg-type]
            rate_limiter=self._rate_limiter,
            retry=self._retry_policy,
            telemetry=None,
            max_offset=10_000,
            batch_size=batch_size,
            on_progress=on_progress,
            # Pass scanner for proper V2 routing (fixes split-brain bug)
            scanner=self._scanner,
        ):
            yield batch

    async def iter_internal_transactions_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: 'ProgressCallback | None' = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Stream internal transactions in batches for maximum memory efficiency.

        Args:
            address: Wallet address to fetch internal transactions for
            from_block: Starting block number (default: 0)
            to_block: Ending block number or 'latest' (default: 'latest')
            batch_size: Number of transactions per batch (default: 1000)
            on_progress: Optional callback for progress updates

        Yields:
            Batches of internal transaction dictionaries
        """
        from aiochainscan.services.fetch_all_streaming import (
            fetch_all_internal_streaming,
        )

        http_client = self._network._http2
        end_block: int | None = (
            None if to_block == 'latest' else int(to_block) if to_block else None
        )

        async for batch in fetch_all_internal_streaming(
            address=address,
            start_block=from_block,
            end_block=end_block,
            api_kind=self.api_kind,
            network=self.network,
            api_key=self.api_key,
            http=http_client,  # type: ignore[arg-type]
            endpoint_builder=self._network._url_builder,  # type: ignore[arg-type]
            rate_limiter=self._rate_limiter,
            retry=self._retry_policy,
            telemetry=None,
            max_offset=10_000,
            batch_size=batch_size,
            on_progress=on_progress,
        ):
            yield batch

    async def iter_token_transfers_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        contract_address: str | None = None,
        batch_size: int = 1000,
        on_progress: 'ProgressCallback | None' = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Stream ERC20 token transfers in batches for maximum memory efficiency.

        Args:
            address: Wallet address to fetch token transfers for
            from_block: Starting block number (default: 0)
            to_block: Ending block number or 'latest' (default: 'latest')
            contract_address: Filter by specific token contract (optional)
            batch_size: Number of transfers per batch (default: 1000)
            on_progress: Optional callback for progress updates

        Yields:
            Batches of token transfer dictionaries
        """
        from aiochainscan.services.fetch_all_streaming import (
            fetch_all_token_transfers_streaming,
        )

        http_client = self._network._http2
        end_block: int | None = (
            None if to_block == 'latest' else int(to_block) if to_block else None
        )

        async for batch in fetch_all_token_transfers_streaming(
            address=address,
            start_block=from_block,
            end_block=end_block,
            api_kind=self.api_kind,
            network=self.network,
            api_key=self.api_key,
            http=http_client,  # type: ignore[arg-type]
            endpoint_builder=self._network._url_builder,  # type: ignore[arg-type]
            contract_address=contract_address,
            rate_limiter=self._rate_limiter,
            retry=self._retry_policy,
            telemetry=None,
            max_offset=10_000,
            batch_size=batch_size,
            on_progress=on_progress,
        ):
            yield batch

    async def iter_logs_streaming(
        self,
        address: str | None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        topic0: str | None = None,
        topic1: str | None = None,
        topic2: str | None = None,
        topic3: str | None = None,
        batch_size: int = 1000,
        on_progress: 'ProgressCallback | None' = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Stream event logs in batches for maximum memory efficiency.

        Args:
            address: Contract address (None for all contracts)
            from_block: Starting block number (default: 0)
            to_block: Ending block number or 'latest' (default: 'latest')
            topic0: Event signature hash (optional)
            topic1: Indexed parameter 1 (optional)
            topic2: Indexed parameter 2 (optional)
            topic3: Indexed parameter 3 (optional)
            batch_size: Number of logs per batch (default: 1000)
            on_progress: Optional callback for progress updates

        Yields:
            Batches of event log dictionaries
        """
        from aiochainscan.services.fetch_all_streaming import (
            fetch_all_logs_streaming,
        )

        http_client = self._network._http2
        end_block: int | None = (
            None if to_block == 'latest' else int(to_block) if to_block else None
        )

        async for batch in fetch_all_logs_streaming(
            address=address,
            start_block=from_block,
            end_block=end_block,
            api_kind=self.api_kind,
            network=self.network,
            api_key=self.api_key,
            http=http_client,  # type: ignore[arg-type]
            endpoint_builder=self._network._url_builder,  # type: ignore[arg-type]
            topic0=topic0,
            topic1=topic1,
            topic2=topic2,
            topic3=topic3,
            rate_limiter=self._rate_limiter,
            retry=self._retry_policy,
            telemetry=None,
            max_offset=1_000,
            batch_size=batch_size,
            on_progress=on_progress,
        ):
            yield batch

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

    async def iter_logs(
        self,
        address: str,
        abi: list[dict[str, Any]] | None = None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        topics: list[str] | None = None,
        topic_operators: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Iterate through event logs one at a time with optional decoding.

        Memory-efficient streaming approach that fetches and optionally decodes
        event logs in batches, yielding them one by one.

        Args:
            address: Contract address to fetch logs for
            abi: Contract ABI for decoding (optional). If provided, logs
                 will include 'decoded_event' and 'decoded_data' fields
            from_block: Starting block number (default: 0)
            to_block: Ending block number or 'latest' (default: 'latest')
            batch_size: Number of items to fetch per batch (default: 1000)
            topics: Event topic filters (optional)
            topic_operators: Topic filter operators (optional)

        Yields:
            Log dictionaries, decoded if ABI is provided

        Example:
            ```python
            # Stream Transfer events
            abi = json.loads(await client.get_contract_abi(usdt_address))
            async for log in client.iter_logs(usdt_address, abi=abi):
                if log.get('decoded_event') == 'Transfer':
                    print(f"From: {log['decoded_data'].get('from')}")
                    print(f"To: {log['decoded_data'].get('to')}")
            ```
        """
        from aiochainscan.services.streaming_decoder import StreamingDecoder

        decoder = StreamingDecoder(
            api_kind=self.api_kind,
            network=self.network,
            api_key=self.api_key,
            http=self._network._http2,  # type: ignore[arg-type]
            endpoint_builder=self._network._url_builder,  # type: ignore[arg-type]
            batch_size=batch_size,
            rate_limiter=self._rate_limiter,
            retry=self._retry_policy,
            telemetry=None,
            max_concurrent=1,
        )

        if abi is not None:
            # Stream with decoding
            async for log in decoder.stream_logs(
                address=address,
                abi=abi,
                from_block=from_block,
                to_block=to_block,
                topics=topics,
                topic_operators=topic_operators,
            ):
                yield log
        else:
            # Stream without decoding
            async for batch in decoder._fetch_log_batches(
                address=address,
                from_block=from_block,
                to_block=to_block,
                topics=topics,
                topic_operators=topic_operators,
            ):
                for log in batch:
                    yield log

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
