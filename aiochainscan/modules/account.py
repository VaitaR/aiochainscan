from collections.abc import Iterable

from aiochainscan.common import (
    check_blocktype,
    check_sort_direction,
    check_tag,
    check_token_standard,
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
        return await self._get(action='balance', address=address, tag=check_tag(tag))

    async def balances(self, addresses: Iterable[str], tag: str = 'latest') -> list[dict]:
        """Get Ether Balance for multiple Addresses in a single call."""
        return await self._get(
            action='balancemulti', address=','.join(addresses), tag=check_tag(tag)
        )

    async def normal_txs(
        self,
        address: str,
        start_block: int | None = None,
        end_block: int | None = None,
        sort: str | None = None,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        """Get a list of 'Normal' Transactions By Address."""
        return await self._get(
            action='txlist',
            address=address,
            startblock=start_block,
            endblock=end_block,
            sort=check_sort_direction(sort),
            page=page,
            offset=offset,
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
    ) -> list[dict]:
        """Get a list of 'Internal' Transactions by Address or Transaction Hash."""
        return await self._get(
            action='txlistinternal',
            address=address,
            startblock=start_block,
            endblock=end_block,
            sort=check_sort_direction(sort),
            page=page,
            offset=offset,
            txhash=txhash,
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
    ) -> list[dict]:
        """Get a list of "ERC20 - Token Transfer Events" by Address"""
        if not address and not contract_address:
            raise ValueError('At least one of address or contract_address must be specified.')

        token_standard = check_token_standard(token_standard)
        actions = {'erc20': 'tokentx', 'erc721': 'tokennfttx', 'erc1155': 'token1155tx'}

        return await self._get(
            action=actions.get(token_standard),
            address=address,
            startblock=start_block,
            endblock=end_block,
            sort=check_sort_direction(sort),
            page=page,
            offset=offset,
            contractaddress=contract_address,
        )

    async def mined_blocks(
        self,
        address: str,
        blocktype: str = 'blocks',
        page: int | None = None,
        offset: int | None = None,
    ) -> list:
        """Get list of Blocks Validated by Address"""
        return await self._get(
            action='getminedblocks',
            address=address,
            blocktype=check_blocktype(blocktype),
            page=page,
            offset=offset,
        )

    async def beacon_chain_withdrawals(
        self,
        address: str,
        start_block: int | None = None,
        end_block: int | None = None,
        sort: str | None = None,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        """Get Beacon Chain Withdrawals by Address and Block Range"""
        return await self._get(
            action='txsBeaconWithdrawal',
            address=address,
            startblock=start_block,
            endblock=end_block,
            sort=check_sort_direction(sort),
            page=page,
            offset=offset,
        )

    async def account_balance_by_blockno(self, address: str, blockno: int) -> str:
        """Get Historical Ether Balance for a Single Address By BlockNo"""
        return await self._get(
            module='account', action='balancehistory', address=address, blockno=blockno
        )
