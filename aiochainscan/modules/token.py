from typing import Any

from aiochainscan.common import ChainFeatures, check_tag, require_feature_support
from aiochainscan.modules.base import BaseModule


class Token(BaseModule):
    """Tokens

    https://docs.etherscan.io/api-endpoints/tokens
    """

    # TODO: Deprecated in next major. Prefer facades in `aiochainscan.__init__`.

    @property
    def _module(self) -> str:
        return 'token'

    async def token_supply(self, contract: str, block_no: int | None = None) -> str:
        """Get ERC20-Token TotalSupply by ContractAddress.

        Args:
            contract: The contract address
            block_no: Block number for historical data (optional)

        Returns:
            Token total supply

        Raises:
            FeatureNotSupportedError: If block_no is specified but not supported by the scanner
        """
        if block_no is None:
            # Use stats module for current supply
            result = await self._get(
                module='stats',
                action='tokensupply',
                contractaddress=contract,
            )
            return str(result)
        else:
            # Use tokensupplyhistory for historical data
            require_feature_support(self._client, ChainFeatures.TOKEN_SUPPLY_BY_BLOCK)
            result = await self._get(
                module='stats',
                action='tokensupplyhistory',
                contractaddress=contract,
                blockno=block_no,
            )
            return str(result)

    async def token_balance(self, contract: str, address: str, block_no: int | None = None) -> str:
        """Get ERC20-Token Account Balance for TokenContractAddress.

        Args:
            contract: The token contract address
            address: The account address
            block_no: Block number for historical data (optional)

        Returns:
            Token balance for the address

        Raises:
            FeatureNotSupportedError: If block_no is specified but not supported by the scanner
        """
        if block_no is None:
            # Prefer new service path via facade for hexagonal migration
            try:
                from aiochainscan import get_token_balance  # lazy import to avoid cycles

                value: int = await get_token_balance(
                    holder=address,
                    token_contract=contract,
                    api_kind=self._client.api_kind,
                    network=self._client.network,
                    api_key=self._client.api_key,
                )
                return str(value)
            except Exception:
                # Fallback to legacy endpoint
                result = await self._get(
                    module='account',
                    action='tokenbalance',
                    address=address,
                    contractaddress=contract,
                    tag='latest',
                )
                return str(result)
        else:
            # Use historical balance endpoint
            require_feature_support(self._client, ChainFeatures.TOKEN_BALANCE_BY_BLOCK)
            result = await self._get(
                module='account',
                action='tokenbalancehistory',
                address=address,
                contractaddress=contract,
                blockno=block_no,
            )
            return str(result)

    # Keep existing methods for backwards compatibility
    async def total_supply(self, contract_address: str) -> str:
        """Get ERC20-Token TotalSupply by ContractAddress"""
        return await self.token_supply(contract_address)

    async def account_balance(
        self, address: str, contract_address: str, tag: str | int = 'latest'
    ) -> str:
        """Get ERC20-Token Account Balance for TokenContractAddress"""
        if tag != 'latest' and isinstance(tag, str | int):
            # Convert tag to block number if it's a hex value or integer
            try:
                if isinstance(tag, int):
                    block_no = tag
                elif isinstance(tag, str) and tag.startswith('0x'):
                    block_no = int(tag, 16)
                else:
                    block_no = int(tag)
                return await self.token_balance(contract_address, address, block_no)
            except ValueError:
                pass

        result = await self._get(
            module='account',
            action='tokenbalance',
            address=address,
            contractaddress=contract_address,
            tag=check_tag(tag),
        )
        return str(result)

    async def total_supply_by_blockno(self, contract_address: str, blockno: int) -> str:
        """Get Historical ERC20-Token TotalSupply by ContractAddress & BlockNo"""
        return await self.token_supply(contract_address, blockno)

    async def account_balance_by_blockno(
        self, address: str, contract_address: str, blockno: int
    ) -> str:
        """Get Historical ERC20-Token Account Balance for TokenContractAddress by BlockNo"""
        return await self.token_balance(contract_address, address, blockno)

    async def token_holder_list(
        self,
        contract_address: str,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get Token Holder List by Contract Address"""
        result = await self._get(
            action='tokenholderlist', contractaddress=contract_address, page=page, offset=offset
        )
        return list(result)

    async def token_info(
        self,
        contract_address: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get Token Info by ContractAddress"""
        result = await self._get(
            action='tokeninfo',
            contractaddress=contract_address,
        )
        return list(result)

    async def token_holding_erc20(
        self,
        address: str,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get Address ERC20 Token Holding"""
        result = await self._get(
            module='account',
            action='addresstokenbalance',
            address=address,
            page=page,
            offset=offset,
        )
        return list(result)

    async def token_holding_erc721(
        self,
        address: str,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get Address ERC721 Token Holding"""
        result = await self._get(
            module='account',
            action='addresstokennftbalance',
            address=address,
            page=page,
            offset=offset,
        )
        return list(result)

    async def token_inventory(
        self,
        address: str,
        contract_address: str,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get Address ERC721 Token Inventory By Contract Address"""
        result = await self._get(
            module='account',
            action='addresstokennftinventory',
            address=address,
            contractaddress=contract_address,
            page=page,
            offset=offset,
        )
        return list(result)
