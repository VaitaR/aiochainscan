from typing import Any, cast

from aiochainscan.modules.base import BaseModule, _should_force_facades


class Transaction(BaseModule):
    """Transactions

    https://docs.etherscan.io/api-endpoints/stats
    """

    # TODO: Deprecated in next major. Prefer facades in `aiochainscan.__init__`.

    @property
    def _module(self) -> str:
        return 'transaction'

    async def contract_execution_status(self, txhash: str) -> dict[str, Any]:
        """[BETA] Check Contract Execution Status (if there was an error during contract execution)"""
        result = await self._get(action='getstatus', txhash=txhash)
        return cast(dict[str, Any], result)

    async def tx_receipt_status(self, txhash: str) -> dict[str, Any]:
        """[BETA] Check Transaction Receipt Status (Only applicable for Post Byzantium fork transactions)"""
        result = await self._get(action='gettxreceiptstatus', txhash=txhash)
        return cast(dict[str, Any], result)

    async def check_tx_status(self, txhash: str) -> dict[str, Any]:
        """Check transaction receipt status.

        This is a wrapper around tx_receipt_status for better naming consistency.
        Only applicable for Post Byzantium fork transactions.

        Args:
            txhash: Transaction hash to check

        Returns:
            Dictionary containing transaction receipt status

        Example:
            ```python
            status = await client.transaction.check_tx_status('0x...')
            print(f"Status: {status}")
            ```
        """
        return await self.tx_receipt_status(txhash)

    async def get_by_hash(self, txhash: str) -> dict[str, Any]:
        """Fetch transaction by hash via facade when available."""
        try:
            from aiochainscan import get_transaction  # lazy import to avoid cycles

            return await get_transaction(
                txhash=txhash,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
        except Exception:
            if _should_force_facades():
                raise
            data = await self._get(
                module='proxy', action='eth_getTransactionByHash', txhash=txhash
            )
            return cast(dict[str, Any], data)
