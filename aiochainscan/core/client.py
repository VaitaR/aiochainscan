"""
Unified client for blockchain scanner APIs.
"""

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any, Literal

import httpx

if TYPE_CHECKING:
    import polars as pl

    from ..ports.progress import ProgressCallback
    from ..services.ens_resolver import ENSResolver

from ..chain_registry import (
    get_chain_info,
    get_scanner_network_name,
    resolve_chain_id,
    resolve_scanner_target,
)
from ..constants import MAX_BLOCK_NUMBER
from ..ports.rate_limiter import RateLimiter, RetryPolicy
from ..scanners import get_scanner_class
from ..scanners.base import Scanner
from ..services.pagination import iter_items, iter_pages, normalize_items, page_fetcher
from .method import Method
from .mixins import (
    AccountMixin,
    BlockMixin,
    ContractMixin,
    ENSMixin,
    LogsMixin,
    ProxyMixin,
    StatsMixin,
    TokenMixin,
    TransactionMixin,
)
from .types import JSONDict
from .url_builder import UrlBuilder

# Strict type aliases for scanner and network names (defined after imports)
ScannerName = Literal['etherscan', 'blockscout', 'blockscout_v2', 'nodereal']
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


def _resolve_end_block_int(to_block: int | str | None) -> int:
    if to_block is None or to_block == 'latest':
        return MAX_BLOCK_NUMBER
    return int(to_block)


def _resolve_end_block_param(to_block: int | str | None) -> int | str:
    if to_block is None or to_block == 'latest':
        return 'latest'
    return int(to_block)


def _decode_with_abi(
    decode_fn: Callable[[JSONDict, list[dict[str, Any]]], JSONDict],
    abi: list[dict[str, Any]] | None,
) -> Callable[[JSONDict], JSONDict] | None:
    """Build a per-item decode hook over ``abi`` (``None`` passes items through)."""
    if abi is None:
        return None

    def decode(item: JSONDict) -> JSONDict:
        return decode_fn(dict(item), abi)

    return decode


class ChainscanClient(
    AccountMixin,
    ContractMixin,
    BlockMixin,
    TransactionMixin,
    LogsMixin,
    TokenMixin,
    StatsMixin,
    ProxyMixin,
    ENSMixin,
):
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
        scanner_network = get_scanner_network_name(scanner_name, scanner_version, network)
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
        api_key: str | None = None,
    ) -> 'ChainscanClient':
        """
        Create client using unified chain-based configuration.

        Thin factory: resolves the (scanner, network, api_kind, api_key)
        target via ``aiochainscan.chain_registry.resolve_scanner_target``
        and constructs the client. Configuration is loaded lazily at call
        time; nothing is resolved at import time.

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
            api_key: Explicit API key. If None (default), the key is resolved
                from the configuration manager (env vars / .env / config files)

        Returns:
            Configured ChainscanClient instance

        Example:
            ```python
            # Etherscan v2 for Ethereum (version defaults to 'v2')
            client = ChainscanClient.from_config('etherscan', 'ethereum')

            # BlockScout v1 for Polygon (version defaults to 'v1')
            client = ChainscanClient.from_config('blockscout', 'polygon')

            # BlockScout V2 alias for ('blockscout', 'v2') — no API key needed
            client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

            # Works with chain_id too
            client = ChainscanClient.from_config('etherscan', 8453)
            ```
        """
        target = resolve_scanner_target(
            scanner_name, network, api_key=api_key, scanner_version=scanner_version
        )
        return cls(
            scanner_name=target.scanner_name,
            scanner_version=target.scanner_version,
            api_kind=target.api_kind,
            network=target.network,
            api_key=target.api_key,
            chain_id=target.chain_id,
            timeout=timeout,
            proxy=proxy,
            rate_limiter=rate_limiter,
            retry_policy=retry_policy,
        )

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
        from ..decode import decode_transaction_input

        # Validate batch_size to prevent infinite loops
        if batch_size < 1:
            raise ValueError(f'batch_size must be at least 1, got {batch_size}')

        decode = _decode_with_abi(decode_transaction_input, abi)
        fetch = page_fetcher(self._scanner, Method.ACCOUNT_TRANSACTIONS)

        # For simple pagination without decoding and no block range, use
        # cursor pagination through the scanner port: fetch_page() returns
        # (items, next_cursor) where a None cursor ends iteration.
        if abi is None and from_block == 0 and (to_block is None or to_block == 'latest'):
            params: dict[str, Any] = {'address': address}
            if self.scanner_name == 'etherscan':
                # Etherscan paginates via page/offset
                params = {'address': address, 'page': 1, 'offset': batch_size}

            async for tx in iter_items(fetch, params):
                yield tx
            return

        # Block-range (or decoding) pagination follows the scanner cursor.
        end_block = _resolve_end_block_int(to_block)
        params = {
            'address': address,
            'startblock': from_block,
            'endblock': end_block,
            'page': 1,
            'offset': batch_size,
            'sort': 'asc',
        }
        async for tx in iter_items(fetch, params, decode=decode):
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
        end_block = _resolve_end_block_int(to_block)
        params: dict[str, Any] = {
            'address': address,
            'startblock': from_block,
            'endblock': end_block,
            'page': 1,
            'offset': batch_size,
            'sort': 'asc',
        }
        async for batch in iter_pages(
            page_fetcher(self._scanner, Method.ACCOUNT_TRANSACTIONS),
            params,
            on_progress=on_progress,
            operation='transactions',
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
        end_block = _resolve_end_block_int(to_block)
        params: dict[str, Any] = {
            'address': address,
            'startblock': from_block,
            'endblock': end_block,
            'page': 1,
            'offset': batch_size,
            'sort': 'asc',
        }
        async for batch in iter_pages(
            page_fetcher(self._scanner, Method.ACCOUNT_INTERNAL_TXS),
            params,
            on_progress=on_progress,
            operation='internal_transactions',
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
        end_block = _resolve_end_block_int(to_block)
        params: dict[str, Any] = {
            'address': address,
            'startblock': from_block,
            'endblock': end_block,
            'page': 1,
            'offset': batch_size,
            'sort': 'asc',
        }
        if contract_address is not None:
            params['contractaddress'] = contract_address
        async for batch in iter_pages(
            page_fetcher(self._scanner, Method.ACCOUNT_ERC20_TRANSFERS),
            params,
            on_progress=on_progress,
            operation='token_transfers',
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
        end_block = _resolve_end_block_param(to_block)
        params: dict[str, Any] = {
            'fromBlock': from_block,
            'toBlock': end_block,
            'page': 1,
            'offset': batch_size,
        }
        if address is not None:
            params['address'] = address
        if topic0 is not None:
            params['topic0'] = topic0
        if topic1 is not None:
            params['topic1'] = topic1
        if topic2 is not None:
            params['topic2'] = topic2
        if topic3 is not None:
            params['topic3'] = topic3
        async for batch in iter_pages(
            page_fetcher(self._scanner, Method.EVENT_LOGS),
            params,
            on_progress=on_progress,
            operation='logs',
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
        from ..decode import decode_log_data

        end_block = _resolve_end_block_param(to_block)
        params: dict[str, Any] = {
            'address': address,
            'fromBlock': from_block,
            'toBlock': end_block,
            'page': 1,
            'offset': batch_size,
        }

        if topics:
            if len(topics) > 0:
                params['topic0'] = topics[0]
            if len(topics) > 1:
                params['topic1'] = topics[1]
            if len(topics) > 2:
                params['topic2'] = topics[2]
            if len(topics) > 3:
                params['topic3'] = topics[3]

        if topic_operators:
            for i, operator in enumerate(topic_operators[:3]):
                params[f'topic{i}_{i + 1}_opr'] = operator

        async for log in iter_items(
            page_fetcher(self._scanner, Method.EVENT_LOGS),
            params,
            decode=_decode_with_abi(decode_log_data, abi),
        ):
            yield log

    # =========================================================================
    # DATAFRAME API - Polars integration for data analysis
    # =========================================================================

    async def get_transactions_df(self, address: str) -> 'pl.DataFrame':
        """
        Get ALL transactions as a Polars DataFrame (auto-paginated).

        Perfect for data analysis and AI agents.
        Requires: pip install aiochainscan[data]

        Returns:
            pl.DataFrame with columns: hash, block_number, from_address,
            to_address, value_wei, value_eth, gas_used, timestamp
        """
        from aiochainscan.services.analytics import transactions_to_dataframe

        return await transactions_to_dataframe(self.iter_transactions(address))

    async def get_token_portfolio_df(self, address: str) -> 'pl.DataFrame':
        """
        Get token portfolio as a Polars DataFrame.

        Requires: pip install aiochainscan[data]

        Returns:
            pl.DataFrame with columns: symbol, name, contract_address, balance, decimals
        """
        from aiochainscan.services.analytics import token_portfolio_to_dataframe

        tokens = await self.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address=address)
        items = normalize_items(tokens)
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
