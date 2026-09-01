"""Transaction-domain API mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import Any, Protocol, cast

from ...domain.models import TxHash
from ...exceptions import ChainscanClientApiError, ChainscanRateLimitError
from ..method import Method
from ..types import JSONDict
from ._waiting import poll_until_final


class _TransactionClientProtocol(Protocol):
    async def call(self, method: Method, **params: Any) -> Any: ...


def _tx_status_is_final(result: Any) -> bool:
    """Whether a ``TX_STATUS_CHECK`` payload is a final execution verdict.

    Etherscan-like scanners answer ``{'isError': '0'|'1', ...}`` once the
    transaction is mined; NodeReal wraps the receipt verdict in an envelope
    (``{'status': '1', 'result': '0'|'1'}``) and reports pending transactions
    as ``{'status': '0', ...}``. Anything else (strings, pending dicts) is
    treated as non-final.
    """
    if not isinstance(result, dict):
        return False
    is_error = result.get('isError')
    if isinstance(is_error, str) and is_error in ('0', '1'):
        return True
    return result.get('status') == '1' and str(result.get('result')) in ('0', '1')


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

    async def wait_for_transaction(
        self: _TransactionClientProtocol,
        tx_hash: str,
        timeout: float = 120.0,
        poll_interval: float = 10.0,
    ) -> JSONDict:
        """Wait until a transaction is mined and reaches a final execution status.

        Polls the execution-status endpoint (:meth:`check_transaction_status`)
        every ``poll_interval`` seconds until the transaction is final or the
        ``timeout`` budget elapses. A transaction that is not mined/indexed
        yet is NOT an error: explorers answer pending hashes with an API
        error envelope (``Error! Invalid transaction hash``), which keeps the
        poll going. A reverted transaction is a final outcome — its status
        dict is returned, not raised, mirroring :meth:`check_transaction_status`.
        Transient rate-limit responses also keep the poll going; genuine
        network failures (already transport-retried) propagate immediately.

        Args:
            tx_hash: Transaction hash to wait for.
            timeout: Total wait budget in seconds (default: 120).
            poll_interval: Delay between polls in seconds (default: 10).

        Returns:
            Final status dict — ``{'isError': '0'|'1', 'errDescription': str}``
            for Etherscan-like scanners, ``{'status': '1', 'result': '0'|'1'}``
            for NodeReal.

        Raises:
            ValueError: If ``tx_hash`` is malformed or the timing arguments
                are negative.
            ChainscanWaitTimeoutError: If the transaction is still pending
                after ``timeout`` seconds.
        """
        txhash = str(TxHash(tx_hash))

        async def probe() -> tuple[bool, Any]:
            try:
                result: Any = await self.call(Method.TX_STATUS_CHECK, txhash=txhash)
            except (ChainscanClientApiError, ChainscanRateLimitError) as exc:
                return False, exc
            return _tx_status_is_final(result), result

        outcome = await poll_until_final(
            probe,
            what=f'transaction {txhash} to reach a final status',
            timeout=timeout,
            poll_interval=poll_interval,
        )
        return cast(JSONDict, outcome)
