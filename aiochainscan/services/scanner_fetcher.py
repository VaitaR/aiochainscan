"""
Scanner-aware page fetcher for bulk data retrieval.

This module provides scanner-agnostic page fetching that routes through
the scanner abstraction layer (ChainscanClient.call()). It ensures that:

1. BlockScout V2 uses modern REST API (/api/v2/addresses/{address}/transactions)
2. Etherscan/BlockScout V1 use legacy query API (module=account&action=txlist)
3. Both benefit from proper pagination, rate limiting, and retries

This fixes the "split-brain" bug where bulk fetching bypassed scanner abstraction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from aiochainscan.core.method import Method

if TYPE_CHECKING:
    from aiochainscan.scanners.base import Scanner


def is_blockscout_v2(api_kind: str) -> bool:
    """
    Check if the api_kind corresponds to BlockScout V2.

    BlockScout V2 uses a different API structure with path-based routing
    and proper cursor-based pagination (next_page_params).

    Args:
        api_kind: The API kind identifier (e.g., 'blockscout_v2', 'eth')

    Returns:
        True if this is a BlockScout V2 configuration
    """
    if not isinstance(api_kind, str):
        return False
    # BlockScout V2 is identified by either explicit 'blockscout_v2' or
    # by api_kind starting with 'blockscout_' when scanner_version is 'v2'
    return api_kind == 'blockscout_v2' or api_kind.startswith('blockscout_v2')


class ScannerAwarePageFetcher:
    """
    Scanner-aware page fetcher that routes through the scanner abstraction.

    This class provides consistent page fetching for bulk operations while
    respecting the scanner's native API format. For BlockScout V2, it uses
    cursor-based pagination (next_page_params). For V1 APIs, it uses
    traditional page/offset pagination.

    Example:
        fetcher = ScannerAwarePageFetcher(scanner)

        # Fetch transactions page by page
        async for page in fetcher.iter_transaction_pages(address='0x...'):
            for tx in page:
                print(tx['hash'])

        # Or with pagination params
        async for page, cursor in fetcher.iter_transaction_pages_with_cursor(
            address='0x...',
            start_block=0,
            end_block=None
        ):
            process_page(page)
    """

    def __init__(
        self,
        scanner: Scanner,
        *,
        scanner_version: str | None = None,
    ) -> None:
        """
        Initialize the scanner-aware page fetcher.

        Args:
            scanner: Scanner instance (e.g., BlockScoutV2Scanner, EtherscanScanner)
            scanner_version: Scanner version ('v1' or 'v2'). If None, inferred from scanner.
        """
        self._scanner = scanner
        self._version = scanner_version or getattr(scanner, 'version', 'v1')
        self._is_v2 = self._version == 'v2'

    @property
    def is_blockscout_v2(self) -> bool:
        """Check if this fetcher uses BlockScout V2 API."""
        return self._is_v2 and getattr(self._scanner, 'name', '') == 'blockscout'

    async def fetch_transactions_page(
        self,
        *,
        address: str,
        page: int = 1,
        offset: int = 100,
        start_block: int | None = None,
        end_block: int | None = None,
        sort: str = 'asc',
        next_page_params: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        Fetch a single page of transactions using the scanner's native API.

        For BlockScout V2:
        - Uses /api/v2/addresses/{address}/transactions
        - Returns next_page_params for cursor-based pagination

        For V1 APIs:
        - Uses module=account&action=txlist
        - Returns None for next_page_params (use page/offset)

        Args:
            address: Wallet address
            page: Page number (V1 only)
            offset: Items per page (V1 only)
            start_block: Starting block (V1 only)
            end_block: Ending block (V1 only)
            sort: Sort order (V1 only)
            next_page_params: Cursor for next page (V2 only)

        Returns:
            Tuple of (transactions, next_page_params_or_none)
        """
        if self.is_blockscout_v2:
            return await self._fetch_v2_page(
                address=address,
                next_page_params=next_page_params,
            )
        else:
            items = await self._fetch_v1_page(
                address=address,
                page=page,
                offset=offset,
                start_block=start_block,
                end_block=end_block,
                sort=sort,
            )
            return items, None

    async def _fetch_v2_page(
        self,
        *,
        address: str,
        next_page_params: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        Fetch a page using BlockScout V2 API with cursor pagination.

        V2 API returns response format:
        {
            "items": [...],
            "next_page_params": {...} or null
        }
        """
        from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner

        if not isinstance(self._scanner, BlockScoutV2Scanner):
            raise TypeError(f'Expected BlockScoutV2Scanner, got {type(self._scanner).__name__}')

        scanner = self._scanner
        spec = scanner.SPECS[Method.ACCOUNT_TRANSACTIONS]
        url = scanner._build_url(spec, address=address)
        query_params = scanner._build_query_params(spec, address=address)

        # Add cursor params if provided
        if next_page_params:
            query_params = {**query_params, **next_page_params}

        headers = {
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
        }

        # Use scanner's network client for request
        if scanner._network_client is None:
            from aiochainscan.network import Network

            scanner._network_client = Network(scanner.url_builder)

        raw_response = await scanner._network_client.request(
            method='GET',
            url=url,
            params=query_params if query_params else None,
            headers=headers,
        )

        # Extract items and next_page_params
        if isinstance(raw_response, dict):
            items = raw_response.get('items', [])
            next_cursor = raw_response.get('next_page_params')
        else:
            items = raw_response if isinstance(raw_response, list) else []
            next_cursor = None

        return items, next_cursor

    async def _fetch_v1_page(
        self,
        *,
        address: str,
        page: int = 1,
        offset: int = 100,
        start_block: int | None = None,
        end_block: int | None = None,
        sort: str = 'asc',
    ) -> list[dict[str, Any]]:
        """
        Fetch a page using V1 API (Etherscan-compatible).

        V1 API uses traditional pagination with page/offset parameters.
        """
        # Build params for V1 API
        params: dict[str, Any] = {'address': address}

        if start_block is not None:
            params['startblock'] = start_block
        if end_block is not None:
            params['endblock'] = end_block
        if page is not None:
            params['page'] = page
        if offset is not None:
            params['offset'] = offset
        if sort is not None:
            params['sort'] = sort

        result = await self._scanner.call(Method.ACCOUNT_TRANSACTIONS, **params)

        if isinstance(result, list):
            return list(result)
        if isinstance(result, dict):
            items = result.get('items', result.get('result', []))
            return list(items) if items else []
        return []

    async def iter_all_transactions(
        self,
        address: str,
        *,
        start_block: int | None = None,
        end_block: int | None = None,
        offset: int = 100,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Iterate through all transactions for an address, auto-paginating.

        This method yields transactions one at a time, handling pagination
        automatically based on the scanner type.

        Args:
            address: Wallet address
            start_block: Starting block (V1 only)
            end_block: Ending block (V1 only)
            offset: Items per page

        Yields:
            Individual transaction dictionaries
        """
        if self.is_blockscout_v2:
            # Use cursor-based pagination for V2
            next_params: dict[str, Any] | None = None
            while True:
                items, next_params = await self._fetch_v2_page(
                    address=address,
                    next_page_params=next_params,
                )

                for tx in items:
                    yield tx

                if not next_params:
                    break
        else:
            # Use page-based pagination for V1
            page = 1
            while True:
                items = await self._fetch_v1_page(
                    address=address,
                    page=page,
                    offset=offset,
                    start_block=start_block,
                    end_block=end_block,
                )

                if not items:
                    break

                for tx in items:
                    yield tx

                if len(items) < offset:
                    break

                page += 1

    async def iter_transaction_batches(
        self,
        address: str,
        *,
        start_block: int | None = None,
        end_block: int | None = None,
        offset: int = 100,
        batch_size: int = 1000,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Iterate through transactions in batches for memory-efficient processing.

        This method accumulates transactions into batches of the specified size,
        reducing memory pressure compared to accumulating all transactions.

        Args:
            address: Wallet address
            start_block: Starting block (V1 only)
            end_block: Ending block (V1 only)
            offset: Items per API page
            batch_size: Items per yielded batch

        Yields:
            Batches of transaction dictionaries
        """
        batch: list[dict[str, Any]] = []

        async for tx in self.iter_all_transactions(
            address,
            start_block=start_block,
            end_block=end_block,
            offset=offset,
        ):
            batch.append(tx)

            if len(batch) >= batch_size:
                yield batch
                batch = []

        if batch:
            yield batch


async def create_scanner_fetcher_from_client(
    client: Any,  # ChainscanClient - avoid circular import
) -> ScannerAwarePageFetcher:
    """
    Create a ScannerAwarePageFetcher from a ChainscanClient.

    This factory function creates the appropriate fetcher based on the client's
    scanner configuration.

    Args:
        client: ChainscanClient instance

    Returns:
        ScannerAwarePageFetcher configured for the client's scanner
    """
    return ScannerAwarePageFetcher(
        client._scanner,
        scanner_version=client.scanner_version,
    )
