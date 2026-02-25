"""Account-domain API mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from ...domain.models import Address
from ..method import Method

if TYPE_CHECKING:
    from ...ports.progress import ProgressCallback


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
    ) -> Any: ...

    def iter_token_transfers_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        contract_address: str | None = None,
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
    ) -> Any: ...

    def iter_internal_transactions_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
    ) -> Any: ...


class AccountMixin:
    """Account-focused typed convenience methods."""

    async def get_balance(self: _AccountClientProtocol, address: str, tag: str = 'latest') -> str:
        """Get account balance in Wei as string."""
        addr = Address(address)
        params: dict[str, Any] = {'address': str(addr)}
        if self.scanner_name == 'etherscan':
            params['tag'] = tag
        result: str = await self.call(Method.ACCOUNT_BALANCE, **params)
        return result

    async def get_transactions(
        self: _AccountClientProtocol,
        address: str,
        start_block: int = 0,
        end_block: int | None = None,
        page: int = 1,
        offset: int = 100,
    ) -> list[dict[str, Any]]:
        """Get list of normal transactions for address."""
        addr = Address(address)
        params: dict[str, Any] = {'address': str(addr)}
        if self.scanner_name == 'etherscan':
            params['startblock'] = start_block
            params['page'] = page
            params['offset'] = offset
            if end_block is not None:
                params['endblock'] = end_block
        result: list[dict[str, Any]] = await self.call(Method.ACCOUNT_TRANSACTIONS, **params)
        return result

    async def get_token_transfers(
        self: _AccountClientProtocol,
        address: str,
        contract_address: str | None = None,
        start_block: int = 0,
        end_block: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get ERC20 token transfers for address."""
        addr = Address(address)
        params: dict[str, Any] = {'address': str(addr)}
        if self.scanner_name == 'etherscan':
            params['startblock'] = start_block
            if contract_address:
                params['contractaddress'] = str(Address(contract_address))
            if end_block:
                params['endblock'] = end_block
        result: list[dict[str, Any]] = await self.call(Method.ACCOUNT_ERC20_TRANSFERS, **params)
        return result

    async def get_internal_transactions(
        self: _AccountClientProtocol,
        address: str,
        start_block: int = 0,
        end_block: int | None = None,
        page: int = 1,
        offset: int = 100,
        sort: str = 'asc',
    ) -> list[dict[str, Any]]:
        """Get internal transactions for an address (single page)."""
        addr = Address(address)
        params: dict[str, Any] = {
            'address': str(addr),
            'startblock': start_block,
            'page': page,
            'offset': offset,
            'sort': sort,
        }
        if end_block is not None:
            params['endblock'] = end_block
        result: Any = await self.call(Method.ACCOUNT_INTERNAL_TXS, **params)
        return result if isinstance(result, list) else []

    async def get_token_portfolio(
        self: _AccountClientProtocol, address: str
    ) -> list[dict[str, Any]]:
        """Get all ERC20 tokens held by address."""
        result: list[dict[str, Any]] = await self.call(
            Method.ACCOUNT_TOKEN_PORTFOLIO, address=str(Address(address))
        )
        return result

    async def get_erc721_transfers(
        self: _AccountClientProtocol,
        address: str,
        contract_address: str | None = None,
        start_block: int = 0,
        end_block: int | str = 99999999,
        page: int = 1,
        offset: int = 100,
        sort: str = 'asc',
    ) -> list[dict[str, Any]]:
        """Get ERC-721 token transfers for an address."""
        params: dict[str, Any] = {
            'address': address,
            'startblock': start_block,
            'endblock': end_block,
            'page': page,
            'offset': offset,
            'sort': sort,
        }
        if contract_address:
            params['contractaddress'] = contract_address
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
    ) -> list[dict[str, Any]]:
        """Get ERC-1155 token transfers for an address."""
        params: dict[str, Any] = {
            'address': address,
            'startblock': start_block,
            'endblock': end_block,
            'page': page,
            'offset': offset,
            'sort': sort,
        }
        if contract_address:
            params['contractaddress'] = contract_address
        result: Any = await self.call(Method.ACCOUNT_ERC1155_TRANSFERS, **params)
        return result if isinstance(result, list) else []

    async def get_nft_portfolio(
        self: _AccountClientProtocol, address: str
    ) -> list[dict[str, Any]]:
        """Get all NFTs owned by an address."""
        result: Any = await self.call(Method.ACCOUNT_NFT_PORTFOLIO, address=str(Address(address)))
        items: list[dict[str, Any]] = (
            result
            if isinstance(result, list)
            else result.get('items', [])
            if isinstance(result, dict)
            else []
        )
        return items

    async def get_all_transactions(
        self: _AccountClientProtocol,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        """Get all transactions by aggregating streaming batches."""
        all_txs: list[dict[str, Any]] = []
        async for batch in self.iter_transactions_streaming(
            address=address,
            from_block=from_block,
            to_block=to_block,
            batch_size=1000,
            on_progress=on_progress,
        ):
            all_txs.extend(batch)
        return all_txs

    async def get_all_token_transfers(
        self: _AccountClientProtocol,
        address: str,
        contract_address: str | None = None,
        from_block: int = 0,
        to_block: int | str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        """Get all ERC20 token transfers by aggregating streaming batches."""
        all_transfers: list[dict[str, Any]] = []
        async for batch in self.iter_token_transfers_streaming(
            address=address,
            from_block=from_block,
            to_block=to_block,
            contract_address=contract_address,
            batch_size=1000,
            on_progress=on_progress,
        ):
            all_transfers.extend(batch)
        return all_transfers

    async def get_all_internal_transactions(
        self: _AccountClientProtocol,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        """Get all internal transactions by aggregating streaming batches."""
        all_txs: list[dict[str, Any]] = []
        async for batch in self.iter_internal_transactions_streaming(
            address=address,
            from_block=from_block,
            to_block=to_block,
            batch_size=1000,
            on_progress=on_progress,
        ):
            all_txs.extend(batch)
        return all_txs
