from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

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

    @property
    def _module(self) -> str:
        return 'account'

    async def balance(self, address: str, tag: str = 'latest') -> str:
        """Get Ether Balance for a single Address."""
        # Prefer new service path via facade for hexagonal migration
        try:
            from aiochainscan import get_balance  # lazy import to avoid cycles

            value: int = await get_balance(
                address=address,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
            return str(value)
        except Exception:
            # Fallback to legacy path if facade unavailable
            result = await self._get(action='balance', address=address, tag=check_tag(tag))
            return cast(str, result)

    async def balances(
        self, addresses: Iterable[str], tag: str = 'latest'
    ) -> list[dict[str, Any]]:
        """Get Ether Balance for multiple Addresses in a single call."""
        try:
            from aiochainscan import get_address_balances  # lazy

            return cast(
                list[dict[str, Any]],
                await get_address_balances(
                    addresses=list(addresses),
                    tag=check_tag(tag),
                    api_kind=self._client.api_kind,
                    network=self._client.network,
                    api_key=self._client.api_key,
                ),
            )
        except Exception:
            result = await self._get(
                action='balancemulti', address=','.join(addresses), tag=check_tag(tag)
            )
            return list(result)

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
        try:
            from aiochainscan import get_normal_transactions  # lazy

            return cast(
                list[dict[str, Any]],
                await get_normal_transactions(
                    address=address,
                    start_block=start_block,
                    end_block=end_block,
                    sort=check_sort_direction(sort) if sort is not None else None,
                    page=page,
                    offset=offset,
                    api_kind=self._client.api_kind,
                    network=self._client.network,
                    api_key=self._client.api_key,
                ),
            )
        except Exception:
            result = await self._get(
                action='txlist',
                address=address,
                startblock=start_block,
                endblock=end_block,
                sort=check_sort_direction(sort) if sort is not None else None,
                page=page,
                offset=offset,
            )
            return list(result)

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
        try:
            from aiochainscan import get_internal_transactions  # lazy

            return cast(
                list[dict[str, Any]],
                await get_internal_transactions(
                    address=address,
                    start_block=start_block,
                    end_block=end_block,
                    sort=check_sort_direction(sort) if sort is not None else None,
                    page=page,
                    offset=offset,
                    txhash=txhash,
                    api_kind=self._client.api_kind,
                    network=self._client.network,
                    api_key=self._client.api_key,
                ),
            )
        except Exception:
            result = await self._get(
                action='txlistinternal',
                address=address,
                startblock=start_block,
                endblock=end_block,
                sort=check_sort_direction(sort) if sort is not None else None,
                page=page,
                offset=offset,
                txhash=txhash,
            )
            return list(result)

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
        try:
            from aiochainscan import get_token_transfers  # lazy

            return cast(
                list[dict[str, Any]],
                await get_token_transfers(
                    address=address,
                    contract_address=contract_address,
                    start_block=start_block,
                    end_block=end_block,
                    sort=check_sort_direction(sort) if sort is not None else None,
                    page=page,
                    offset=offset,
                    token_standard=token_standard,
                    api_kind=self._client.api_kind,
                    network=self._client.network,
                    api_key=self._client.api_key,
                ),
            )
        except Exception:
            actions = {'erc20': 'tokentx', 'erc721': 'tokennfttx', 'erc1155': 'token1155tx'}
            result = await self._get(
                action=actions.get(token_standard),
                address=address,
                startblock=start_block,
                endblock=end_block,
                sort=check_sort_direction(sort) if sort is not None else None,
                page=page,
                offset=offset,
                contractaddress=contract_address,
            )
            return list(result)

    async def mined_blocks(
        self,
        address: str,
        blocktype: str = 'blocks',
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get list of Blocks Validated by Address"""
        try:
            from aiochainscan import get_mined_blocks  # lazy

            return cast(
                list[dict[str, Any]],
                await get_mined_blocks(
                    address=address,
                    blocktype=check_blocktype(blocktype),
                    page=page,
                    offset=offset,
                    api_kind=self._client.api_kind,
                    network=self._client.network,
                    api_key=self._client.api_key,
                ),
            )
        except Exception:
            result = await self._get(
                action='getminedblocks',
                address=address,
                blocktype=check_blocktype(blocktype),
                page=page,
                offset=offset,
            )
            return list(result)

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
        try:
            from aiochainscan import get_beacon_chain_withdrawals  # lazy

            return cast(
                list[dict[str, Any]],
                await get_beacon_chain_withdrawals(
                    address=address,
                    start_block=start_block,
                    end_block=end_block,
                    sort=check_sort_direction(sort) if sort is not None else None,
                    page=page,
                    offset=offset,
                    api_kind=self._client.api_kind,
                    network=self._client.network,
                    api_key=self._client.api_key,
                ),
            )
        except Exception:
            result = await self._get(
                action='txsBeaconWithdrawal',
                address=address,
                startblock=start_block,
                endblock=end_block,
                sort=check_sort_direction(sort) if sort is not None else None,
                page=page,
                offset=offset,
            )
            return list(result)

    async def account_balance_by_blockno(self, address: str, blockno: int) -> str:
        """Get Historical Ether Balance for a Single Address By BlockNo"""
        try:
            from aiochainscan import get_account_balance_by_blockno  # lazy

            return cast(
                str,
                await get_account_balance_by_blockno(
                    address=address,
                    blockno=blockno,
                    api_kind=self._client.api_kind,
                    network=self._client.network,
                    api_key=self._client.api_key,
                ),
            )
        except Exception:
            result = await self._get(
                module='account', action='balancehistory', address=address, blockno=blockno
            )
            return str(result)

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
        try:
            from aiochainscan import get_token_transfers  # lazy

            return cast(
                list[dict[str, Any]],
                await get_token_transfers(
                    address=address,
                    contract_address=None,
                    start_block=startblock,
                    end_block=endblock,
                    page=page,
                    offset=offset,
                    sort=None,
                    token_standard='erc20',
                    api_kind=self._client.api_kind,
                    network=self._client.network,
                    api_key=self._client.api_key,
                ),
            )
        except Exception:
            result = await self._get(
                action='tokentx',
                address=address,
                startblock=startblock,
                endblock=endblock,
                page=page,
                offset=offset,
            )
            return list(result)
