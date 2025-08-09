from __future__ import annotations

from typing import Any

from aiochainscan.common import check_hex, check_tag
from aiochainscan.modules.base import BaseModule


class Proxy(BaseModule):
    """Geth/Parity Proxy

    https://docs.etherscan.io/api-endpoints/geth-parity-proxy
    """

    # TODO: Deprecated in next major. Prefer facades in `aiochainscan.__init__`.

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
        account_exc: Exception | None = None
        try:
            # Try account module first (primary endpoint)
            result = await self._client.account.balance(address, tag)
            return int(result)
        except Exception as e:
            account_exc = e
            # Fallback to proxy endpoint for ETH-clones via service
            try:
                from aiochainscan.modules.base import _facade_injection, _resolve_api_context
                from aiochainscan.services.proxy import get_balance as _svc_get_balance

                http, endpoint = _facade_injection(self._client)
                api_kind, network, api_key = _resolve_api_context(self._client)
                hex_balance = await _svc_get_balance(
                    address=address,
                    tag=check_tag(tag),
                    api_kind=api_kind,
                    network=network,
                    api_key=api_key,
                    http=http,
                    _endpoint_builder=endpoint,
                )
                if isinstance(hex_balance, str) and hex_balance.startswith('0x'):
                    return int(hex_balance, 16)
                return int(hex_balance)
            except Exception:
                # If both fail, re-raise the original account error
                raise account_exc from None

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
        from aiochainscan.modules.base import _facade_injection
        from aiochainscan.services.proxy import get_block_number as _svc_get_block_number

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.modules.base import _resolve_api_context

        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_block_number(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def block_by_number(self, full: bool, tag: int | str = 'latest') -> dict[str, Any]:
        """Returns information about a block by block number."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.block import get_block_by_number as _svc_get_block

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_get_block(
            tag=check_tag(tag),
            full=full,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return result

    async def uncle_block_by_number_and_index(
        self, index: int | str, tag: int | str = 'latest'
    ) -> dict[str, Any]:
        """Returns information about a uncle by block number."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import (
            get_uncle_by_block_number_and_index as _svc_uncle_by_bn_idx,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        _ = check_tag(tag)
        result = await _svc_uncle_by_bn_idx(
            tag=tag,
            index=check_hex(index),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return result

    async def block_tx_count_by_number(self, tag: int | str = 'latest') -> str:
        """Returns the number of transactions in a block from a block matching the given block number."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import (
            get_block_tx_count_by_number as _svc_block_tx_count,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        _ = check_tag(tag)
        return await _svc_block_tx_count(
            tag=tag,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def tx_by_hash(self, txhash: int | str) -> dict[str, Any]:
        """Returns the information about a transaction requested by transaction hash."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import get_tx_by_hash as _svc_get_tx_by_hash

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_get_tx_by_hash(
            txhash=check_hex(txhash),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return result

    async def tx_by_number_and_index(
        self, index: int | str, tag: int | str = 'latest'
    ) -> dict[str, Any]:
        """Returns information about a transaction by block number and transaction index position."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import (
            get_tx_by_block_number_and_index as _svc_tx_by_bn_idx,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        _ = check_tag(tag)
        result = await _svc_tx_by_bn_idx(
            tag=tag,
            index=check_hex(index),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return result

    async def tx_count(self, address: str, tag: int | str = 'latest') -> str:
        """Returns the number of transactions sent from an address."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import get_tx_count as _svc_get_tx_count

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        # Preserve legacy tag validation call in tests
        _ = check_tag(tag)
        return await _svc_get_tx_count(
            address=address,
            tag=tag,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def send_raw_tx(self, raw_hex: str) -> dict[str, Any]:
        """Creates new message call transaction or a contract creation for signed transactions."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import send_raw_tx as _svc_send_raw_tx

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_send_raw_tx(
            raw_hex=raw_hex,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return result

    async def tx_receipt(self, txhash: str) -> dict[str, Any]:
        """Returns the receipt of a transaction by transaction hash."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import get_tx_receipt as _svc_get_tx_receipt

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_get_tx_receipt(
            txhash=check_hex(txhash),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return result

    async def call(self, to: str, data: str, tag: int | str = 'latest') -> str:
        """Executes a new message call immediately without creating a transaction on the block chain."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import eth_call as _svc_eth_call

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        _ = check_tag(tag)
        return await _svc_eth_call(
            to=check_hex(to),
            data=check_hex(data),
            tag=tag,  # let service handle tag formatting; avoid double validation in tests
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def code(self, address: str, tag: int | str = 'latest') -> str:
        """Returns code at a given address."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import get_code as _svc_get_code

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        _ = check_tag(tag)
        return await _svc_get_code(
            address=address,
            tag=tag,  # avoid double validation; service will sanitize
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def storage_at(self, address: str, position: str, tag: int | str = 'latest') -> str:
        """Returns the value from a storage position at a given address."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import get_storage_at as _svc_get_storage_at

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        _ = check_tag(tag)
        return await _svc_get_storage_at(
            address=address,
            position=position,
            tag=tag,  # avoid double validation; service will sanitize
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def gas_price(self) -> str:
        """Returns the current price per gas in wei."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import get_gas_price as _svc_get_gas_price

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_gas_price(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def estimate_gas(self, to: str, value: str, gas_price: str, gas: str) -> str:
        """Makes a call or transaction, which won't be added to the blockchain and returns the used gas.

        Can be used for estimating the used gas.
        """
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.proxy import estimate_gas as _svc_estimate_gas

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_estimate_gas(
            to=check_hex(to),
            value=value,
            gas_price=gas_price,
            gas=gas,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
