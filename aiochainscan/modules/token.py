from aiochainscan.common import ChainFeatures, check_tag, require_feature_support
from aiochainscan.modules.base import BaseModule


class Token(BaseModule):
    """Tokens

    https://docs.etherscan.io/api-endpoints/tokens
    """

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
            return await self._get(
                module='stats',
                action='tokensupply',
                contractaddress=contract,
            )
        else:
            # Use tokensupplyhistory for historical data
            require_feature_support(self._client, ChainFeatures.TOKEN_SUPPLY_BY_BLOCK)
            return await self._get(
                module='stats',
                action='tokensupplyhistory',
                contractaddress=contract,
                blockno=block_no,
            )

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
            # Use current balance endpoint
            return await self._get(
                module='account',
                action='tokenbalance',
                address=address,
                contractaddress=contract,
                tag='latest',
            )
        else:
            # Use historical balance endpoint
            require_feature_support(self._client, ChainFeatures.TOKEN_BALANCE_BY_BLOCK)
            return await self._get(
                module='account',
                action='tokenbalancehistory',
                address=address,
                contractaddress=contract,
                blockno=block_no,
            )

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

        return await self._get(
            module='account',
            action='tokenbalance',
            address=address,
            contractaddress=contract_address,
            tag=check_tag(tag),
        )

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
        page: int = None,
        offset: int = None,
    ) -> list[dict]:
        """Get Token Holder List by Contract Address"""
        return await self._get(
            action='tokenholderlist', contractaddress=contract_address, page=page, offset=offset
        )

    async def token_info(
        self,
        contract_address: str = None,
    ) -> list[dict]:
        """Get Token Info by ContractAddress"""
        return await self._get(
            action='tokeninfo',
            contractaddress=contract_address,
        )

    async def token_holding_erc20(
        self,
        address: str,
        page: int = None,
        offset: int = None,
    ) -> list[dict]:
        """Get Address ERC20 Token Holding"""
        return await self._get(
            module='account',
            action='addresstokenbalance',
            address=address,
            page=page,
            offset=offset,
        )

    async def token_holding_erc721(
        self,
        address: str,
        page: int = None,
        offset: int = None,
    ) -> list[dict]:
        """Get Address ERC721 Token Holding"""
        return await self._get(
            module='account',
            action='addresstokennftbalance',
            address=address,
            page=page,
            offset=offset,
        )

    async def token_inventory(
        self,
        address: str,
        contract_address: str,
        page: int = None,
        offset: int = None,
    ) -> list[dict]:
        """Get Address ERC721 Token Inventory By Contract Address"""
        return await self._get(
            module='account',
            action='addresstokennftinventory',
            address=address,
            contractaddress=contract_address,
            page=page,
            offset=offset,
        )
