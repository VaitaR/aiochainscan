from typing import Any, cast

from aiochainscan.modules.base import BaseModule


class Transaction(BaseModule):
    """Transactions

    https://docs.etherscan.io/api-endpoints/stats
    """

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
