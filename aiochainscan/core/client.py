"""
Unified client for blockchain scanner APIs.
"""

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    import polars as pl

    from ..ports.progress import ProgressCallback
    from ..services.ens_resolver import ENSResolver

from ..chain_registry import (
    ScannerTarget,
    get_scanner_network_name,
    resolve_scanner_target,
)
from ..constants import MAX_BLOCK_NUMBER
from ..domain.method import Method
from ..domain.normalize import (
    normalize_internal_transaction,
    normalize_log,
    normalize_token_transfer,
    normalize_transaction,
)
from ..domain.normalized import InternalTransaction, Log, TokenTransfer, Transaction
from ..exceptions import BlockRangeNotSupportedError
from ..ports.rate_limiter import RateLimiter, RetryPolicy
from ..scanners import get_scanner_class
from ..scanners.base import Scanner
from ..services.pagination import (
    BoundPageFetch,
    PaginationContext,
    iter_items,
    iter_pages,
    normalize_items,
    page_fetcher,
    validate_batch_size,
)
from .mixins import (
    AccountMixin,
    BlockMixin,
    ChainMixin,
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
    ChainMixin,
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

        # Direct instantiation — honest constructor (chain id or alias, provider name)
        client = ChainscanClient(chain='ethereum', provider='etherscan', api_key='your_api_key')

        # Make unified API calls
        balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
        ```
    """

    def __init__(
        self,
        target: ScannerTarget | None = None,
        *,
        chain: str | int | None = None,
        provider: str | None = None,
        api_key: str | None = None,
        scanner_version: str | None = None,
        expected_chain_id: int | None = None,
        allow_http: bool = False,
        timeout: float | httpx.Timeout | None = 10.0,
        proxy: str | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
    ):
        """
        Initialize the unified client from a resolved :class:`ScannerTarget`.

        ``ScannerTarget`` is the single internal construction currency: chain
        id, UrlBuilder network name and credentials are resolved exactly once
        — by :func:`aiochainscan.chain_registry.resolve_scanner_target` — and
        this constructor trusts the result (no re-derivation). Build one via
        ``from_config``, the ``chain``/``provider`` keyword form, or
        ``resolve_scanner_target`` directly.

        Args:
            target: Resolved construction target (see
                :class:`~aiochainscan.chain_registry.ScannerTarget`). When
                ``None``, the ``chain``/``provider`` keyword pair resolves one
                first through the same single resolution point as
                ``from_config``.
            chain: Keyword-only honest-constructor form: a chain id or alias
                ('ethereum', 8453, a self-hosted base URL). Required together
                with ``provider`` when ``target`` is not given; mutually
                exclusive with a given ``target``.
            provider: Keyword-only honest-constructor form of the scanner
                name (e.g. 'etherscan', 'blockscout', 'blockscout_v2').
            api_key: Explicit API key for the ``chain``/``provider`` form
                (default: resolved from the configuration manager).
            scanner_version: Explicit scanner version override for the
                ``chain``/``provider`` form (default: registry default).
            expected_chain_id: Chain id the instance must serve for the
                ``chain``/``provider`` form. When set, it is validated before
                the first request and a mismatch raises
                ``ChainscanDataError`` (see ``validate_chain``).
            allow_http: Permit cleartext ``http://`` base URLs for the
                ``chain``/``provider`` form (see ``from_config``).
            timeout: Request timeout in seconds or httpx.Timeout instance
            proxy: Proxy URL
            rate_limiter: Rate limiter implementation (default: AioLimiterAdapter)
            retry_policy: Retry policy implementation (default: TenacityRetryAdapter)

        Raises:
            TypeError: Neither a ``target`` nor the ``chain``/``provider``
                pair was given; a ``target`` was accompanied by resolution
                kwargs; or the removed pre-1.0 positional
                ``(scanner_name, scanner_version, api_kind, network,
                api_key)`` form was used.
        """
        if target is None:
            if chain is None or provider is None:
                raise TypeError(
                    'ChainscanClient: pass a resolved ScannerTarget, or the '
                    "('chain', 'provider') keyword pair — never neither."
                )
            target = resolve_scanner_target(
                provider,
                chain,
                api_key=api_key,
                scanner_version=scanner_version,
                expected_chain_id=expected_chain_id,
                allow_http=allow_http,
            )
        elif not isinstance(target, ScannerTarget):
            raise TypeError(
                'ChainscanClient: the first argument must be a ScannerTarget — the '
                'pre-1.0 positional (scanner_name, scanner_version, api_kind, network, '
                'api_key) constructor was removed. Use from_config, the '
                "('chain', 'provider') keyword form, or build a target via "
                'aiochainscan.chain_registry.resolve_scanner_target.'
            )
        elif (
            chain is not None
            or provider is not None
            or api_key is not None
            or scanner_version is not None
            or expected_chain_id is not None
            or allow_http
        ):
            raise TypeError(
                'ChainscanClient: a ScannerTarget is already resolved — resolution '
                "kwargs ('chain', 'provider', 'api_key', 'scanner_version', "
                "'expected_chain_id', 'allow_http') cannot accompany it."
            )

        self._target = target
        self.scanner_name = target.scanner_name
        self.scanner_version = target.scanner_version
        self.api_kind = target.api_kind
        self.network = target.network
        self.api_key = target.api_key
        self.base_url = target.base_url
        self.chain_id: int | None = target.chain_id
        self._expected_chain_id = target.expected_chain_id

        # UrlBuilder network name resolved exactly once, by the registry
        # (ScannerTarget.url_network owns it) — never re-derived here.
        self._url_builder = UrlBuilder(
            target.api_key, target.api_kind, target.url_network, api_url=target.base_url
        )

        # Store additional config
        self._timeout = timeout
        self._proxy = proxy
        self._rate_limiter = rate_limiter
        self._retry_policy = retry_policy

        # Create Network instance owned by this client for connection pooling.
        # With expected_chain_id the network runs a one-shot validation guard
        # before the first admitted request (fail fast on chain mismatch).
        from ..network import Network

        self._network = Network(
            url_builder=self._url_builder,
            timeout=timeout,
            proxy=proxy,
            rate_limiter=rate_limiter,
            retry_policy=retry_policy,
            first_request_guard=(
                self._validate_expected_chain_once
                if target.expected_chain_id is not None
                else None
            ),
        )

        # Get scanner class and create instance with shared network client.
        # The scanner receives the already-resolved chain_id and trusts it
        # (resolution ownership: resolve_scanner_target — see ScannerTarget).
        scanner_class = get_scanner_class(target.scanner_name, target.scanner_version)
        # Use chain_id to resolve the correct network name for this scanner
        scanner_network = get_scanner_network_name(
            target.scanner_name, target.scanner_version, target.network
        )
        self._scanner = scanner_class(
            target.api_key,
            scanner_network,
            self._url_builder,
            target.chain_id,
            network_client=self._network,
            base_url=target.base_url,
        )

        # Lazy-initialized ENS resolver
        self._ens_resolver: ENSResolver | None = None

    @classmethod
    def from_config(
        cls,
        scanner_name: str,
        network: str | int,
        scanner_version: str | None = None,
        timeout: float | httpx.Timeout | None = 10.0,
        proxy: str | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
        api_key: str | None = None,
        expected_chain_id: int | None = None,
        allow_http: bool = False,
    ) -> 'ChainscanClient':
        """
        Create client using unified chain-based configuration.

        Thin factory: resolves the construction target via
        ``aiochainscan.chain_registry.resolve_scanner_target`` and hands it to
        the constructor — one resolution point, one wiring path. Scanner and
        network names are plain strings validated at runtime by the registry
        (unknown names fail fast with the supported list; see
        ``chain_registry.STANDARD_CHAINS``). Configuration is loaded lazily at
        call time; nothing is resolved at import time.

        URL-vs-alias heuristic: a string ``network`` containing a
        ``scheme://`` prefix is treated as a custom base URL — a self-hosted
        BlockScout instance or an Etherscan v2 proxy — while anything else
        resolves through the chain registry as before (backward compatible;
        chain aliases never contain ``://``). Custom instances are validated
        (https by default, no credentials/query/``..`` in the URL — see
        ``aiochainscan.base_url``).

        Args:
            scanner_name: Scanner implementation ('etherscan', 'blockscout')
            network: Chain name/ID ('ethereum', 'base', 1, 8453) or a base
                URL ('https://my-blockscout.internal')
            scanner_version: Scanner version ('v1', 'v2'). If None, uses default:
                - 'v2' for etherscan (recommended)
                - 'v1' for all other scanners
            timeout: Request timeout in seconds or httpx.Timeout instance
            proxy: Proxy URL
            rate_limiter: Rate limiter implementation
            retry_policy: Retry policy implementation
            api_key: Explicit API key. If None (default), the key is resolved
                from the configuration manager (env vars / .env / config files).
                Never required for BlockScout scanners, including self-hosted.
            expected_chain_id: Chain id the configured instance must serve.
                Validated before the first request; a mismatch raises
                ``ChainscanDataError``. Required for URL-shaped networks on
                etherscan (V2 routes by chainid); optional elsewhere.
            allow_http: Allow cleartext ``http://`` base URLs (default False).

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

            # Self-hosted BlockScout — chain validated before first request
            client = ChainscanClient.from_config(
                'blockscout_v2', 'https://my-blockscout.internal', expected_chain_id=100
            )

            # Etherscan v2 behind a proxy (API key still required)
            client = ChainscanClient.from_config(
                'etherscan', 'https://eth-proxy.internal',
                api_key='...', expected_chain_id=137,
            )
            ```
        """
        return cls(
            resolve_scanner_target(
                scanner_name,
                network,
                api_key=api_key,
                scanner_version=scanner_version,
                expected_chain_id=expected_chain_id,
                allow_http=allow_http,
            ),
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

    async def fetch_page(
        self, method: Method, params: dict[str, Any]
    ) -> tuple[list[JSONDict], dict[str, Any] | None]:
        """Fetch a single page via the scanner's public cursor seam.

        Thin passthrough to :meth:`aiochainscan.scanners.base.Scanner.fetch_page`
        so cursor-driven consumers (e.g. the MCP tools) never reach into the
        client's privates: returns ``(items, next_cursor)`` where a non-``None``
        cursor merges into ``params`` (``{**params, **cursor}``) for the next
        page and ``None`` terminates pagination.

        Args:
            method: Logical method to execute for every page.
            params: Request parameters, including ``page``/``offset`` for
                page-numbered APIs; merge the previous cursor on top for
                subsequent pages.

        Returns:
            Tuple of ``(items, next_cursor)``.

        Raises:
            ValueError: If the method is not supported by the scanner.
            Various network/API errors from the underlying transport.
        """
        return await self._scanner.fetch_page(method, params)

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

    def _pagination_context(self, method: Method) -> PaginationContext:
        """Identity passed to the pagination engine for honest error messages.

        ``alternatives`` is computed from the scanner registry, not hardcoded:
        any registered scanner declaring ``method`` with no result window can
        serve it completely.
        """
        from ..scanners import scanners_serving_completely

        return PaginationContext(
            method=method.name,
            provider=f'{self.scanner_name}/{self.scanner_version}',
            alternatives=scanners_serving_completely(method),
        )

    def _stream_fetch(self, method: Method) -> BoundPageFetch:
        """Bind scanner + method into one page fetch for the pagination engine.

        The binding carries the provider's declared ``result_window`` and the
        method's :class:`PaginationContext`, so streaming call sites pass a
        single object to ``iter_pages``/``iter_items`` instead of threading
        parallel ``result_window=``/``context=`` kwargs (explicit kwargs
        still override the binding when given).
        """
        return page_fetcher(self._scanner, method, context=self._pagination_context(method))

    def _guard_block_range(
        self,
        method: Method,
        from_block: int,
        to_block: int | str | None,
    ) -> None:
        """Refuse a BOUNDED range the provider would silently drop.

        A single guard for every streaming/paginated path: when the requested
        range is bounded (``from_block > 0`` or a concrete ``to_block``) and
        the scanner's ``SPECS`` declare no block-range parameter for the
        method, the bounds never reach the wire — the request would silently
        answer a wider range than asked for. Providers able to narrow the
        query are named from the scanner registry.
        """
        bounded = from_block > 0 or (to_block is not None and to_block != 'latest')
        if not bounded or self._scanner.supports_block_range(method):
            return
        from ..scanners import scanners_serving_block_range

        provider = f'{self.scanner_name}/{self.scanner_version}'
        alternatives = scanners_serving_block_range(method)
        if alternatives:
            remedy = f'Providers that declare a block range for it: {", ".join(alternatives)}.'
        else:
            remedy = f'No registered provider declares a block range for {method.name}.'
        raise BlockRangeNotSupportedError(
            f'{provider} does not declare a block-range parameter for {method.name}, so the '
            f'requested bounds (from_block={from_block}, to_block={to_block!r}) would be '
            f'silently dropped: the answer would cover a wider range than asked for. '
            f'Request an unbounded range (from_block=0, to_block=None) or use a provider '
            f'that declares the range. {remedy}'
        )

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
        guarantee_complete: bool = True,
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

        validate_batch_size(batch_size)

        decode = _decode_with_abi(decode_transaction_input, abi)
        fetch = self._stream_fetch(Method.ACCOUNT_TRANSACTIONS)
        self._guard_block_range(Method.ACCOUNT_TRANSACTIONS, from_block, to_block)

        # Every scanner speaks the same public param dialect here; its SPECS
        # translate to wire names (or drop params the endpoint never took —
        # only possible for an unbounded range, which the guard above ensures).
        # For simple pagination without decoding and no block range, use
        # cursor pagination through the scanner port: fetch_page() returns
        # (items, next_cursor) where a None cursor ends iteration.
        if (
            abi is None
            and from_block == 0
            and (to_block is None or to_block == 'latest')
            and not guarantee_complete
        ):
            # Rangeless shortcut: fewer params, but nothing to split if the
            # provider's result window is hit.
            params: dict[str, Any] = {'address': address, 'page': 1, 'offset': batch_size}
        else:
            end_block = _resolve_end_block_int(to_block)
            params = {
                'address': address,
                'start_block': from_block,
                'end_block': end_block,
                'page': 1,
                'offset': batch_size,
                'sort': 'asc',
            }

        async for tx in iter_items(
            fetch,
            params,
            decode=decode,
            guarantee_complete=guarantee_complete,
        ):
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
        guarantee_complete: bool = True,
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

            guarantee_complete: When ``True`` (default) the engine detects a
                provider result-window overflow and splits the block range
                until every matching record is returned, raising
                ``PaginationDataLossError`` if a single block still exceeds
                the cap. ``False`` restores the pre-1.0 behaviour: fewer
                requests on wide ranges, at the risk of silent truncation.
                Inert for scanners that paginate by opaque cursor
                (``Scanner.result_window is None``).

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
        validate_batch_size(batch_size)
        self._guard_block_range(Method.ACCOUNT_TRANSACTIONS, from_block, to_block)
        end_block = _resolve_end_block_int(to_block)
        params: dict[str, Any] = {
            'address': address,
            'start_block': from_block,
            'end_block': end_block,
            'page': 1,
            'offset': batch_size,
            'sort': 'asc',
        }
        async for batch in iter_pages(
            self._stream_fetch(Method.ACCOUNT_TRANSACTIONS),
            params,
            on_progress=on_progress,
            operation='transactions',
            guarantee_complete=guarantee_complete,
        ):
            yield batch

    async def iter_transactions_normalized(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: 'ProgressCallback | None' = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[Transaction]]:
        """Stream normalized ``Transaction`` batches over the complete history.

        Wraps :meth:`iter_transactions_streaming` (identical params, identical
        ``guarantee_complete`` semantics/default) and maps each raw batch onto
        :class:`~aiochainscan.domain.normalized.Transaction` as it arrives —
        never after the raw list is fully collected, so memory stays bounded
        by ``batch_size`` regardless of dataset size.
        """
        async for batch in self.iter_transactions_streaming(
            address=address,
            from_block=from_block,
            to_block=to_block,
            batch_size=batch_size,
            on_progress=on_progress,
            guarantee_complete=guarantee_complete,
        ):
            yield [normalize_transaction(item) for item in batch]

    async def iter_internal_transactions_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: 'ProgressCallback | None' = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Stream internal transactions in batches for maximum memory efficiency.

        Args:
            address: Wallet address to fetch internal transactions for
            from_block: Starting block number (default: 0)
            to_block: Ending block number or 'latest' (default: 'latest')
            batch_size: Number of transactions per batch (default: 1000)
            on_progress: Optional callback for progress updates

            guarantee_complete: When ``True`` (default) the engine detects a
                provider result-window overflow and splits the block range
                until every matching record is returned, raising
                ``PaginationDataLossError`` if a single block still exceeds
                the cap. ``False`` restores the pre-1.0 behaviour: fewer
                requests on wide ranges, at the risk of silent truncation.
                Inert for scanners that paginate by opaque cursor
                (``Scanner.result_window is None``).

        Yields:
            Batches of internal transaction dictionaries
        """
        validate_batch_size(batch_size)
        self._guard_block_range(Method.ACCOUNT_INTERNAL_TXS, from_block, to_block)
        end_block = _resolve_end_block_int(to_block)
        params: dict[str, Any] = {
            'address': address,
            'start_block': from_block,
            'end_block': end_block,
            'page': 1,
            'offset': batch_size,
            'sort': 'asc',
        }
        async for batch in iter_pages(
            self._stream_fetch(Method.ACCOUNT_INTERNAL_TXS),
            params,
            on_progress=on_progress,
            operation='internal_transactions',
            guarantee_complete=guarantee_complete,
        ):
            yield batch

    async def iter_internal_transactions_normalized(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: 'ProgressCallback | None' = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[InternalTransaction]]:
        """Stream normalized ``InternalTransaction`` batches over the complete history.

        Wraps :meth:`iter_internal_transactions_streaming`; same params, same
        ``guarantee_complete`` semantics/default, per-batch normalization.
        """
        async for batch in self.iter_internal_transactions_streaming(
            address=address,
            from_block=from_block,
            to_block=to_block,
            batch_size=batch_size,
            on_progress=on_progress,
            guarantee_complete=guarantee_complete,
        ):
            yield [normalize_internal_transaction(item) for item in batch]

    async def iter_token_transfers_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        contract_address: str | None = None,
        batch_size: int = 1000,
        on_progress: 'ProgressCallback | None' = None,
        guarantee_complete: bool = True,
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

            guarantee_complete: When ``True`` (default) the engine detects a
                provider result-window overflow and splits the block range
                until every matching record is returned, raising
                ``PaginationDataLossError`` if a single block still exceeds
                the cap. ``False`` restores the pre-1.0 behaviour: fewer
                requests on wide ranges, at the risk of silent truncation.
                Inert for scanners that paginate by opaque cursor
                (``Scanner.result_window is None``).

        Yields:
            Batches of token transfer dictionaries
        """
        validate_batch_size(batch_size)
        self._guard_block_range(Method.ACCOUNT_ERC20_TRANSFERS, from_block, to_block)
        end_block = _resolve_end_block_int(to_block)
        params: dict[str, Any] = {
            'address': address,
            'start_block': from_block,
            'end_block': end_block,
            'page': 1,
            'offset': batch_size,
            'sort': 'asc',
        }
        if contract_address is not None:
            params['contract_address'] = contract_address
        async for batch in iter_pages(
            self._stream_fetch(Method.ACCOUNT_ERC20_TRANSFERS),
            params,
            on_progress=on_progress,
            operation='token_transfers',
            guarantee_complete=guarantee_complete,
        ):
            yield batch

    async def iter_token_transfers_normalized(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        contract_address: str | None = None,
        batch_size: int = 1000,
        on_progress: 'ProgressCallback | None' = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[TokenTransfer]]:
        """Stream normalized ``TokenTransfer`` batches over the complete history.

        Wraps :meth:`iter_token_transfers_streaming`; same params, same
        ``guarantee_complete`` semantics/default, per-batch normalization.
        """
        async for batch in self.iter_token_transfers_streaming(
            address=address,
            from_block=from_block,
            to_block=to_block,
            contract_address=contract_address,
            batch_size=batch_size,
            on_progress=on_progress,
            guarantee_complete=guarantee_complete,
        ):
            yield [normalize_token_transfer(item) for item in batch]

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
        guarantee_complete: bool = True,
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

            guarantee_complete: When ``True`` (default) the engine detects a
                provider result-window overflow and splits the block range
                until every matching record is returned, raising
                ``PaginationDataLossError`` if a single block still exceeds
                the cap. ``False`` restores the pre-1.0 behaviour: fewer
                requests on wide ranges, at the risk of silent truncation.
                Inert for scanners that paginate by opaque cursor
                (``Scanner.result_window is None``).

        Yields:
            Batches of event log dictionaries
        """
        validate_batch_size(batch_size)
        self._guard_block_range(Method.EVENT_LOGS, from_block, to_block)
        end_block = _resolve_end_block_param(to_block)
        params: dict[str, Any] = {
            'from_block': from_block,
            'to_block': end_block,
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
            self._stream_fetch(Method.EVENT_LOGS),
            params,
            on_progress=on_progress,
            operation='logs',
            guarantee_complete=guarantee_complete,
        ):
            yield batch

    async def iter_logs_normalized(
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
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[Log]]:
        """Stream normalized ``Log`` batches over the complete event-log history.

        Wraps :meth:`iter_logs_streaming`; same params, same
        ``guarantee_complete`` semantics/default, per-batch normalization.
        """
        async for batch in self.iter_logs_streaming(
            address,
            from_block=from_block,
            to_block=to_block,
            topic0=topic0,
            topic1=topic1,
            topic2=topic2,
            topic3=topic3,
            batch_size=batch_size,
            on_progress=on_progress,
            guarantee_complete=guarantee_complete,
        ):
            yield [normalize_log(item) for item in batch]

    async def iter_token_holders_streaming(
        self,
        contract_address: str,
        batch_size: int = 1000,
        on_progress: 'ProgressCallback | None' = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Stream token holders in batches for maximum memory efficiency.

        Yields unified ``{'address': EIP-55 str, 'value': str}`` items (the
        ``value`` is the raw-unit, Wei-like quantity — never Int64). Etherscan
        walks page/offset; BlockScout V2 follows ``next_page_params`` cursors
        (its ``page``/``offset`` request params are ignored by the scanner).

        Args:
            contract_address: ERC-20 token contract address
            batch_size: Number of holders per batch (default: 1000; Etherscan
                caps a page at 1000)
            on_progress: Optional callback for progress updates

            guarantee_complete: When ``True`` (default) the engine detects a
                provider result-window overflow and splits the block range
                until every matching record is returned, raising
                ``PaginationDataLossError`` if a single block still exceeds
                the cap. ``False`` restores the pre-1.0 behaviour: fewer
                requests on wide ranges, at the risk of silent truncation.
                Inert for scanners that paginate by opaque cursor
                (``Scanner.result_window is None``).

        Yields:
            Batches of token holder dictionaries
        """
        from ..domain.models import Address

        validate_batch_size(batch_size)
        params: dict[str, Any] = {
            'contract_address': str(Address(contract_address)),
            'page': 1,
            'offset': batch_size,
        }
        async for batch in iter_pages(
            self._stream_fetch(Method.TOKEN_HOLDERS),
            params,
            on_progress=on_progress,
            operation='token_holders',
            guarantee_complete=guarantee_complete,
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
        guarantee_complete: bool = True,
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

        validate_batch_size(batch_size)
        self._guard_block_range(Method.EVENT_LOGS, from_block, to_block)
        end_block = _resolve_end_block_param(to_block)
        params: dict[str, Any] = {
            'address': address,
            'from_block': from_block,
            'to_block': end_block,
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
            self._stream_fetch(Method.EVENT_LOGS),
            params,
            decode=_decode_with_abi(decode_log_data, abi),
            guarantee_complete=guarantee_complete,
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
