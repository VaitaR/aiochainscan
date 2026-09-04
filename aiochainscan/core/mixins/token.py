"""Token-domain API mixin for ``ChainscanClient``."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...domain.method import Method
from ...domain.models import Address
from ..host import ClientHost
from ..streaming import collect_stream
from ..types import JSONDict, JSONList

if TYPE_CHECKING:
    from ...ports.progress import ProgressCallback

logger = logging.getLogger(__name__)


class TokenMixin:
    """Token-focused typed convenience methods."""

    async def get_token_balance(
        self: ClientHost, address: str, contract_address: str, tag: str = 'latest'
    ) -> str:
        result: str = await self.call(
            Method.TOKEN_BALANCE,
            address=str(Address(address)),
            contract_address=str(Address(contract_address)),
            tag=tag,
        )
        return str(result)

    async def get_token_info(self: ClientHost, contract_address: str) -> JSONDict:
        result: JSONDict = await self.call(
            Method.TOKEN_INFO, contract_address=str(Address(contract_address))
        )
        return result

    async def get_token_supply(self: ClientHost, contract_address: str) -> str:
        result: str = await self.call(Method.TOKEN_SUPPLY, contract_address=contract_address)
        return str(result)

    async def get_token_holders(
        self: ClientHost,
        contract_address: str,
        page: int = 1,
        offset: int = 100,
    ) -> JSONList:
        """Get one page of token holders (single page, ~50-100 items).

        ``page``/``offset`` apply to page-numbered APIs (Etherscan); cursor
        paginated scanners (BlockScout V2) return their first server page.

        Unified item shape: ``{'address': EIP-55 str, 'value': str}`` where
        ``value`` is the raw-unit (Wei-like) quantity — always a string.
        Use :meth:`get_all_token_holders` or
        :meth:`iter_token_holders_streaming` for the complete list.
        """
        result: Any = await self.call(
            Method.TOKEN_HOLDERS,
            contract_address=str(Address(contract_address)),
            page=page,
            offset=offset,
        )
        return result if isinstance(result, list) else []

    async def get_all_token_holders(
        self: ClientHost,
        contract_address: str,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> JSONList:
        """Get all token holders by aggregating streaming batches.

        ``guarantee_complete`` (default ``True``) forbids silent truncation:
        an overflowing block range is split until complete, and
        ``PaginationDataLossError`` is raised if it cannot be. Pass ``False``
        for the cheaper pre-1.0 behaviour.
        """
        return await collect_stream(
            self.iter_token_holders_streaming(
                contract_address=contract_address,
                batch_size=1000,
                on_progress=on_progress,
                guarantee_complete=guarantee_complete,
            ),
            stream_name='iter_token_holders_streaming',
            noun='token holders',
            logger=logger,
        )

    async def get_top_token_holders(
        self: ClientHost,
        contract_address: str,
        limit: int = 100,
    ) -> JSONList:
        """Get the top-N holders by balance (Etherscan PRO ``topholders``).

        ``limit`` maps to the API's ``offset`` parameter (max 1000, throttled
        to 2 calls/s). Scanners without a guaranteed top-ordering endpoint
        (BlockScout V2, NodeReal) raise ``ValueError``.
        """
        if limit < 1:
            raise ValueError(f'limit must be at least 1, got {limit}')
        result: Any = await self.call(
            Method.TOKEN_TOP_HOLDERS,
            contract_address=str(Address(contract_address)),
            offset=limit,
        )
        return result if isinstance(result, list) else []

    async def get_token_holder_count(self: ClientHost, contract_address: str) -> int:
        """Get the number of addresses holding the token.

        Etherscan serves a scalar string count (PRO); BlockScout V2 reads it
        from the token info endpoint. Both are returned as ``int``.
        """
        result: Any = await self.call(
            Method.TOKEN_HOLDER_COUNT,
            contract_address=str(Address(contract_address)),
        )
        return int(result or 0)
