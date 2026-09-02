"""Account-domain API mixin for ``ChainscanClient``."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol

from ...domain.method import Method
from ...domain.models import Address
from ...domain.normalize import (
    normalize_internal_transaction,
    normalize_token_transfer,
    normalize_transaction,
)
from ...domain.normalized import InternalTransaction, TokenTransfer, Transaction
from ...services.pagination import collect_all, normalize_items
from ..types import JSONList

if TYPE_CHECKING:
    from ...ports.progress import ProgressCallback


logger = logging.getLogger(__name__)
AGGREGATION_WARNING_THRESHOLD = 100_000


class _AccountClientProtocol(Protocol):
    scanner_name: str

    async def call(self, method: Method, **params: Any) -> Any: ...

    def iter_transactions_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> Any: ...

    def iter_token_transfers_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        contract_address: str | None = None,
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> Any: ...

    def iter_internal_transactions_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> Any: ...

    def iter_transactions_normalized(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[Transaction]]: ...

    def iter_token_transfers_normalized(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        contract_address: str | None = None,
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[TokenTransfer]]: ...

    def iter_internal_transactions_normalized(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[InternalTransaction]]: ...


class AccountMixin:
    """Account-focused typed convenience methods."""

    async def get_balance(self: _AccountClientProtocol, address: str, tag: str = 'latest') -> str:
        """Get account balance in Wei as string."""
        addr = Address(address)
        params: dict[str, Any] = {'address': str(addr)}
        params['tag'] = tag
        result: Any = await self.call(Method.ACCOUNT_BALANCE, **params)
        return str(result)

    async def get_transactions(
        self: _AccountClientProtocol,
        address: str,
        start_block: int = 0,
        end_block: int | None = None,
        page: int = 1,
        offset: int = 100,
    ) -> JSONList:
        """Get list of normal transactions for address."""
        addr = Address(address)
        params: dict[str, Any] = {'address': str(addr)}
        params.update({'start_block': start_block, 'page': page, 'offset': offset})
        if end_block is not None:
            params['end_block'] = end_block
        result: Any = await self.call(Method.ACCOUNT_TRANSACTIONS, **params)
        return result if isinstance(result, list) else []

    async def get_transactions_normalized(
        self: _AccountClientProtocol,
        address: str,
        start_block: int = 0,
        end_block: int | None = None,
        page: int = 1,
        offset: int = 100,
    ) -> list[Transaction]:
        """Same page as ``get_transactions``, mapped onto ``domain.normalized.Transaction``."""
        raw = await AccountMixin.get_transactions(
            self, address, start_block, end_block, page, offset
        )
        return [normalize_transaction(item) for item in raw]

    async def get_token_transfers(
        self: _AccountClientProtocol,
        address: str,
        contract_address: str | None = None,
        start_block: int = 0,
        end_block: int | None = None,
    ) -> JSONList:
        """Get ERC20 token transfers for address."""
        addr = Address(address)
        params: dict[str, Any] = {'address': str(addr)}
        params['start_block'] = start_block
        if contract_address:
            params['contract_address'] = str(Address(contract_address))
        if end_block is not None:
            params['end_block'] = end_block
        result: Any = await self.call(Method.ACCOUNT_ERC20_TRANSFERS, **params)
        return result if isinstance(result, list) else []

    async def get_token_transfers_normalized(
        self: _AccountClientProtocol,
        address: str,
        contract_address: str | None = None,
        start_block: int = 0,
        end_block: int | None = None,
    ) -> list[TokenTransfer]:
        """Same page as ``get_token_transfers``, mapped onto ``domain.normalized.TokenTransfer``."""
        raw = await AccountMixin.get_token_transfers(
            self, address, contract_address, start_block, end_block
        )
        return [normalize_token_transfer(item) for item in raw]

    async def get_internal_transactions(
        self: _AccountClientProtocol,
        address: str,
        start_block: int = 0,
        end_block: int | None = None,
        page: int = 1,
        offset: int = 100,
        sort: str = 'asc',
    ) -> JSONList:
        """Get internal transactions for an address (single page)."""
        addr = Address(address)
        params: dict[str, Any] = {
            'address': str(addr),
            'start_block': start_block,
            'page': page,
            'offset': offset,
            'sort': sort,
        }
        if end_block is not None:
            params['end_block'] = end_block
        result: Any = await self.call(Method.ACCOUNT_INTERNAL_TXS, **params)
        return result if isinstance(result, list) else []

    async def get_internal_transactions_normalized(
        self: _AccountClientProtocol,
        address: str,
        start_block: int = 0,
        end_block: int | None = None,
        page: int = 1,
        offset: int = 100,
        sort: str = 'asc',
    ) -> list[InternalTransaction]:
        """Same page as ``get_internal_transactions``, mapped onto ``domain.normalized.InternalTransaction``."""
        raw = await AccountMixin.get_internal_transactions(
            self, address, start_block, end_block, page, offset, sort
        )
        return [normalize_internal_transaction(item) for item in raw]

    async def get_token_portfolio(self: _AccountClientProtocol, address: str) -> JSONList:
        """Get all ERC20 tokens held by address."""
        result: Any = await self.call(
            Method.ACCOUNT_TOKEN_PORTFOLIO, address=str(Address(address))
        )
        return result if isinstance(result, list) else []

    async def get_erc721_transfers(
        self: _AccountClientProtocol,
        address: str,
        contract_address: str | None = None,
        start_block: int = 0,
        end_block: int | str = 99999999,
        page: int = 1,
        offset: int = 100,
        sort: str = 'asc',
    ) -> JSONList:
        """Get ERC-721 token transfers for an address."""
        params: dict[str, Any] = {
            'address': address,
            'start_block': start_block,
            'end_block': end_block,
            'page': page,
            'offset': offset,
            'sort': sort,
        }
        if contract_address:
            params['contract_address'] = contract_address
        result: Any = await self.call(Method.ACCOUNT_ERC721_TRANSFERS, **params)
        return result if isinstance(result, list) else []

    async def get_erc1155_transfers(
        self: _AccountClientProtocol,
        address: str,
        contract_address: str | None = None,
        start_block: int = 0,
        end_block: int | str = 99999999,
        page: int = 1,
        offset: int = 100,
        sort: str = 'asc',
    ) -> JSONList:
        """Get ERC-1155 token transfers for an address."""
        params: dict[str, Any] = {
            'address': address,
            'start_block': start_block,
            'end_block': end_block,
            'page': page,
            'offset': offset,
            'sort': sort,
        }
        if contract_address:
            params['contract_address'] = contract_address
        result: Any = await self.call(Method.ACCOUNT_ERC1155_TRANSFERS, **params)
        return result if isinstance(result, list) else []

    async def get_nft_portfolio(self: _AccountClientProtocol, address: str) -> JSONList:
        """Get all NFTs owned by an address."""
        result: Any = await self.call(Method.ACCOUNT_NFT_PORTFOLIO, address=str(Address(address)))
        items: JSONList = normalize_items(result)
        return items

    async def get_all_transactions(
        self: _AccountClientProtocol,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> JSONList:
        """Get all transactions by aggregating streaming batches.

        ``guarantee_complete`` (default ``True``) forbids silent truncation:
        an overflowing block range is split until complete, and
        ``PaginationDataLossError`` is raised if it cannot be. Pass ``False``
        for the cheaper pre-1.0 behaviour.
        """
        return await collect_all(
            self.iter_transactions_streaming(
                address=address,
                from_block=from_block,
                to_block=to_block,
                batch_size=1000,
                on_progress=on_progress,
                guarantee_complete=guarantee_complete,
            ),
            threshold=AGGREGATION_WARNING_THRESHOLD,
            warning='Aggregating >100k transactions in memory. '
            'Consider using iter_transactions_streaming() to avoid OOM.',
            logger=logger,
        )

    async def get_all_token_transfers(
        self: _AccountClientProtocol,
        address: str,
        contract_address: str | None = None,
        from_block: int = 0,
        to_block: int | str | None = None,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> JSONList:
        """Get all ERC20 token transfers by aggregating streaming batches.

        ``guarantee_complete`` (default ``True``) forbids silent truncation:
        an overflowing block range is split until complete, and
        ``PaginationDataLossError`` is raised if it cannot be. Pass ``False``
        for the cheaper pre-1.0 behaviour.
        """
        return await collect_all(
            self.iter_token_transfers_streaming(
                address=address,
                from_block=from_block,
                to_block=to_block,
                contract_address=contract_address,
                batch_size=1000,
                on_progress=on_progress,
                guarantee_complete=guarantee_complete,
            ),
            threshold=AGGREGATION_WARNING_THRESHOLD,
            warning='Aggregating >100k token transfers in memory. '
            'Consider using iter_token_transfers_streaming() to avoid OOM.',
            logger=logger,
        )

    async def get_all_internal_transactions(
        self: _AccountClientProtocol,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> JSONList:
        """Get all internal transactions by aggregating streaming batches.

        ``guarantee_complete`` (default ``True``) forbids silent truncation:
        an overflowing block range is split until complete, and
        ``PaginationDataLossError`` is raised if it cannot be. Pass ``False``
        for the cheaper pre-1.0 behaviour.
        """
        return await collect_all(
            self.iter_internal_transactions_streaming(
                address=address,
                from_block=from_block,
                to_block=to_block,
                batch_size=1000,
                on_progress=on_progress,
                guarantee_complete=guarantee_complete,
            ),
            threshold=AGGREGATION_WARNING_THRESHOLD,
            warning='Aggregating >100k internal transactions in memory. '
            'Consider using iter_internal_transactions_streaming() to avoid OOM.',
            logger=logger,
        )

    # =========================================================================
    # NORMALIZED "GET ALL" API - complete history, mapped onto domain models
    # =========================================================================
    #
    # Each materializes the client's matching ``iter_*_normalized`` generator
    # (defined on ``ChainscanClient`` itself, next to ``iter_*_streaming`` —
    # see core/client.py), which normalizes items batch-by-batch as they
    # arrive, never after collecting the raw list. ``guarantee_complete`` is
    # forwarded unchanged: the completeness engine underneath
    # (``services/pagination.py``) decides whether a batch is complete before
    # normalization ever sees it.

    async def get_all_transactions_normalized(
        self: _AccountClientProtocol,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> list[Transaction]:
        """Materialize ``iter_transactions_normalized`` into one list.

        Same completeness guarantee as :meth:`get_all_transactions`; the only
        difference is the item type (``Transaction`` instead of ``dict``).
        """
        items: list[Transaction] = []
        async for batch in self.iter_transactions_normalized(
            address=address,
            from_block=from_block,
            to_block=to_block,
            batch_size=1000,
            on_progress=on_progress,
            guarantee_complete=guarantee_complete,
        ):
            items.extend(batch)
            if len(items) == AGGREGATION_WARNING_THRESHOLD:
                logger.warning(
                    'Aggregating >100k normalized transactions in memory. '
                    'Consider using iter_transactions_normalized() to avoid OOM.'
                )
        return items

    async def get_all_token_transfers_normalized(
        self: _AccountClientProtocol,
        address: str,
        contract_address: str | None = None,
        from_block: int = 0,
        to_block: int | str | None = None,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> list[TokenTransfer]:
        """Materialize ``iter_token_transfers_normalized`` into one list."""
        items: list[TokenTransfer] = []
        async for batch in self.iter_token_transfers_normalized(
            address=address,
            from_block=from_block,
            to_block=to_block,
            contract_address=contract_address,
            batch_size=1000,
            on_progress=on_progress,
            guarantee_complete=guarantee_complete,
        ):
            items.extend(batch)
            if len(items) == AGGREGATION_WARNING_THRESHOLD:
                logger.warning(
                    'Aggregating >100k normalized token transfers in memory. '
                    'Consider using iter_token_transfers_normalized() to avoid OOM.'
                )
        return items

    async def get_all_internal_transactions_normalized(
        self: _AccountClientProtocol,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> list[InternalTransaction]:
        """Materialize ``iter_internal_transactions_normalized`` into one list."""
        items: list[InternalTransaction] = []
        async for batch in self.iter_internal_transactions_normalized(
            address=address,
            from_block=from_block,
            to_block=to_block,
            batch_size=1000,
            on_progress=on_progress,
            guarantee_complete=guarantee_complete,
        ):
            items.extend(batch)
            if len(items) == AGGREGATION_WARNING_THRESHOLD:
                logger.warning(
                    'Aggregating >100k normalized internal transactions in memory. '
                    'Consider using iter_internal_transactions_normalized() to avoid OOM.'
                )
        return items
