from __future__ import annotations

from typing import Any, cast

from aiochainscan.common import check_hex, check_tag
from aiochainscan.modules.base import BaseModule


class Proxy(BaseModule):
    """Geth/Parity Proxy

    https://docs.etherscan.io/api-endpoints/geth-parity-proxy
    """

    @property
    def _module(self) -> str:
        return 'proxy'

    async def balance(self, address: str, tag: str = 'latest') -> int:
        """Get Ether balance for an address.

        First attempts to use module=account&action=balance endpoint.
        For ETH-clones, falls back to module=proxy&action=eth_getBalance.

        Args:
            address: The address to check balance for
            tag: Block parameter (default: 'latest')

        Returns:
            Balance in wei as integer

        Example:
            ```python
            balance = await client.proxy.balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
            print(f"Balance: {balance} wei")
            ```
        """
        try:
            # Try account module first (primary endpoint)
            result = await self._client.account.balance(address, tag)
            return int(result)
        except Exception:
            # Fallback to proxy endpoint for ETH-clones
            try:
                result = await self._get(
                    action='eth_getBalance',
                    address=address,
                    tag=check_tag(tag),
                )
                # Convert hex string to int
                return (
                    int(result, 16)
                    if isinstance(result, str) and result.startswith('0x')
                    else int(result)
                )
            except Exception:
                # If both fail, re-raise the original account error
                result = await self._client.account.balance(address, tag)
                return int(result)

    async def get_balance(self, address: str, tag: str = 'latest') -> int:
        """Legacy alias for balance method.

        Args:
            address: The address to check balance for
            tag: Block parameter (default: 'latest')

        Returns:
            Balance in wei as integer
        """
        return await self.balance(address, tag)

    async def block_number(self) -> str:
        """Returns the number of most recent block via facade when available."""
        try:
            from aiochainscan import get_block_number  # lazy import to avoid cycles

            return await get_block_number(
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
        except Exception:
            result = await self._get(action='eth_blockNumber')
            return str(result)

    async def block_by_number(self, full: bool, tag: int | str = 'latest') -> dict[str, Any]:
        """Returns information about a block by block number."""
        result = await self._get(
            action='eth_getBlockByNumber',
            boolean=full,
            tag=check_tag(tag),
        )
        return cast(dict[str, Any], result)

    async def uncle_block_by_number_and_index(
        self, index: int | str, tag: int | str = 'latest'
    ) -> dict[str, Any]:
        """Returns information about a uncle by block number."""
        result = await self._get(
            action='eth_getUncleByBlockNumberAndIndex',
            index=check_hex(index),
            tag=check_tag(tag),
        )
        return cast(dict[str, Any], result)

    async def block_tx_count_by_number(self, tag: int | str = 'latest') -> str:
        """Returns the number of transactions in a block from a block matching the given block number."""
        try:
            # NOTE: Proxy tx_count endpoint expects address-based count; for block tx count keep legacy
            raise ImportError()
        except Exception:
            result = await self._get(
                action='eth_getBlockTransactionCountByNumber',
                tag=check_tag(tag),
            )
            return str(result)

    async def tx_by_hash(self, txhash: int | str) -> dict[str, Any]:
        """Returns the information about a transaction requested by transaction hash."""
        result = await self._get(
            action='eth_getTransactionByHash',
            txhash=check_hex(txhash),
        )
        return cast(dict[str, Any], result)

    async def tx_by_number_and_index(
        self, index: int | str, tag: int | str = 'latest'
    ) -> dict[str, Any]:
        """Returns information about a transaction by block number and transaction index position."""
        result = await self._get(
            action='eth_getTransactionByBlockNumberAndIndex',
            index=check_hex(index),
            tag=check_tag(tag),
        )
        return cast(dict[str, Any], result)

    async def tx_count(self, address: str, tag: int | str = 'latest') -> str:
        """Returns the number of transactions sent from an address."""
        try:
            from aiochainscan import get_tx_count  # lazy

            return await get_tx_count(
                address=address,
                tag=tag,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
        except Exception:
            result = await self._get(
                action='eth_getTransactionCount',
                address=address,
                tag=check_tag(tag),
            )
            return cast(str, result)

    async def send_raw_tx(self, raw_hex: str) -> dict[str, Any]:
        """Creates new message call transaction or a contract creation for signed transactions."""
        result = await self._post(module='proxy', action='eth_sendRawTransaction', hex=raw_hex)
        return cast(dict[str, Any], result)

    async def tx_receipt(self, txhash: str) -> dict[str, Any]:
        """Returns the receipt of a transaction by transaction hash."""
        result = await self._get(
            action='eth_getTransactionReceipt',
            txhash=check_hex(txhash),
        )
        return cast(dict[str, Any], result)

    async def call(self, to: str, data: str, tag: int | str = 'latest') -> str:
        """Executes a new message call immediately without creating a transaction on the block chain."""
        try:
            from aiochainscan import eth_call  # lazy

            return await eth_call(
                to=check_hex(to),
                data=check_hex(data),
                tag=tag,  # let service handle tag formatting; avoid double validation in tests
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
        except Exception:
            result = await self._get(
                action='eth_call',
                to=check_hex(to),
                data=check_hex(data),
                tag=check_tag(tag),
            )
            return str(result)

    async def code(self, address: str, tag: int | str = 'latest') -> str:
        """Returns code at a given address."""
        try:
            from aiochainscan import get_code  # lazy

            return await get_code(
                address=address,
                tag=tag,  # avoid double validation; service will sanitize
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
        except Exception:
            result = await self._get(
                action='eth_getCode',
                address=address,
                tag=check_tag(tag),
            )
            return str(result)

    async def storage_at(self, address: str, position: str, tag: int | str = 'latest') -> str:
        """Returns the value from a storage position at a given address."""
        try:
            from aiochainscan import get_storage_at  # lazy

            return await get_storage_at(
                address=address,
                position=position,
                tag=tag,  # avoid double validation; service will sanitize
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
        except Exception:
            result = await self._get(
                action='eth_getStorageAt',
                address=address,
                position=position,
                tag=check_tag(tag),
            )
            return str(result)

    async def gas_price(self) -> str:
        """Returns the current price per gas in wei."""
        result = await self._get(
            action='eth_gasPrice',
        )
        return str(result)

    async def estimate_gas(self, to: str, value: str, gas_price: str, gas: str) -> str:
        """Makes a call or transaction, which won't be added to the blockchain and returns the used gas.

        Can be used for estimating the used gas.
        """
        result = await self._get(
            action='eth_estimateGas',
            to=check_hex(to),
            value=value,
            gasPrice=gas_price,
            gas=gas,
        )
        return str(result)
