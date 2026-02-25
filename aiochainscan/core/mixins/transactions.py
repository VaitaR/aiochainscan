"""Transaction-domain API mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import Any, Protocol

from ...domain.models import TxHash
from ..method import Method
from ..types import JSONDict


class _TransactionClientProtocol(Protocol):
    async def call(self, method: Method, **params: Any) -> Any: ...


class TransactionMixin:
    """Transaction-focused typed convenience methods."""

    async def get_transaction(self: _TransactionClientProtocol, tx_hash: str) -> JSONDict:
        result: JSONDict = await self.call(Method.TX_BY_HASH, txhash=str(TxHash(tx_hash)))
        return result

    async def get_transaction_status(self: _TransactionClientProtocol, tx_hash: str) -> JSONDict:
        result: JSONDict = await self.call(Method.TX_RECEIPT_STATUS, txhash=str(TxHash(tx_hash)))
        return result

    async def check_transaction_status(self: _TransactionClientProtocol, tx_hash: str) -> JSONDict:
        result: JSONDict = await self.call(Method.TX_STATUS_CHECK, txhash=str(TxHash(tx_hash)))
        return result
