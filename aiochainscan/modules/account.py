from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aiochainscan.common import (
    ChainFeatures,
    check_blocktype,
    check_sort_direction,
    check_tag,
    check_token_standard,
    require_feature_support,
)
from aiochainscan.modules.base import BaseModule


class Account(BaseModule):
    """Accounts

    https://docs.etherscan.io/api-endpoints/accounts
    """

    # TODO: Deprecated in next major. Prefer facades in `aiochainscan.__init__`.

    @property
    def _module(self) -> str:
        return 'account'

    async def balance(self, address: str, tag: str = 'latest') -> str:
        """Get Ether Balance for a single Address."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.account import (
            get_address_balance as _svc_get_address_balance,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        # Respect tag conversion like legacy behavior
        extra_params = None
        if tag != 'latest':
            try:
                extra_params = {'tag': hex(int(tag)) if isinstance(tag, int) else tag}
            except Exception:
                extra_params = None
        value: int = await _svc_get_address_balance(
            address=address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            extra_params=extra_params,
        )
        return str(value)

    async def balances(
        self, addresses: Iterable[str], tag: str = 'latest'
    ) -> list[dict[str, Any]]:
        """Get Ether Balance for multiple Addresses in a single call."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.account import (
            get_address_balances as _svc_get_address_balances,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_address_balances(
            addresses=list(addresses),
            tag=check_tag(tag),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def normal_txs(
        self,
        address: str,
        start_block: int | None = None,
        end_block: int | None = None,
        sort: str | None = None,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get a list of 'Normal' Transactions By Address."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.account import (
            get_normal_transactions as _svc_get_normal_transactions,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_normal_transactions(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort=check_sort_direction(sort) if sort is not None else None,
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def internal_txs(
        self,
        address: str,
        start_block: int | None = None,
        end_block: int | None = None,
        sort: str | None = None,
        page: int | None = None,
        offset: int | None = None,
        txhash: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get a list of 'Internal' Transactions by Address or Transaction Hash."""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.account import (
            get_internal_transactions as _svc_get_internal_transactions,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_internal_transactions(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort=check_sort_direction(sort) if sort is not None else None,
            page=page,
            offset=offset,
            txhash=txhash,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def token_transfers(
        self,
        address: str | None = None,
        contract_address: str | None = None,
        start_block: int | None = None,
        end_block: int | None = None,
        sort: str | None = None,
        page: int | None = None,
        offset: int | None = None,
        token_standard: str = 'erc20',
    ) -> list[dict[str, Any]]:
        """Get a list of "ERC20 - Token Transfer Events" by Address"""
        if not address and not contract_address:
            raise ValueError('At least one of address or contract_address must be specified.')

        token_standard = check_token_standard(token_standard)
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.account import (
            get_token_transfers as _svc_get_token_transfers,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_token_transfers(
            address=address,
            contract_address=contract_address,
            start_block=start_block,
            end_block=end_block,
            sort=check_sort_direction(sort) if sort is not None else None,
            page=page,
            offset=offset,
            token_standard=token_standard,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def mined_blocks(
        self,
        address: str,
        blocktype: str = 'blocks',
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get list of Blocks Validated by Address"""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.account import get_mined_blocks as _svc_get_mined_blocks

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_mined_blocks(
            address=address,
            blocktype=check_blocktype(blocktype),
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def beacon_chain_withdrawals(
        self,
        address: str,
        start_block: int | None = None,
        end_block: int | None = None,
        sort: str | None = None,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get Beacon Chain Withdrawals by Address and Block Range"""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.account import (
            get_beacon_chain_withdrawals as _svc_get_beacon_withdrawals,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_beacon_withdrawals(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort=check_sort_direction(sort) if sort is not None else None,
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def account_balance_by_blockno(self, address: str, blockno: int) -> str:
        """Get Historical Ether Balance for a Single Address By BlockNo"""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.account import (
            get_account_balance_by_blockno as _svc_get_balance_by_blockno,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_balance_by_blockno(
            address=address,
            blockno=blockno,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def erc20_transfers(
        self,
        address: str,
        *,
        startblock: int = 0,
        endblock: int = 99999999,
        page: int = 1,
        offset: int = 100,
    ) -> list[dict[str, Any]]:
        """Get a list of ERC-20 Token Transfer Events by Address.

        Args:
            address: The address to get token transfers for
            startblock: Starting block number (default: 0)
            endblock: Ending block number (default: 99999999)
            page: Page number for pagination (default: 1)
            offset: Number of results per page (default: 100)

        Returns:
            List of ERC-20 token transfer events

        Raises:
            FeatureNotSupportedError: If the scanner doesn't support ERC-20 transfers
        """
        require_feature_support(self._client, ChainFeatures.ERC20_TRANSFERS)
        # Keep legacy call shape to match tests (no contractaddress/sort in params)
        result = await self._get(
            action='tokentx',
            address=address,
            startblock=startblock,
            endblock=endblock,
            page=page,
            offset=offset,
        )
        return list(result)
