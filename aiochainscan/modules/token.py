from typing import Any

from aiochainscan.common import ChainFeatures, require_feature_support
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
            from aiochainscan.modules.base import _facade_injection, _resolve_api_context
            from aiochainscan.services.token import (
                get_token_total_supply as _svc_token_total_supply,
            )

            http, endpoint = _facade_injection(self._client)
            api_kind, network, api_key = _resolve_api_context(self._client)
            return await _svc_token_total_supply(
                contract=contract,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=endpoint,
            )
        else:
            require_feature_support(self._client, ChainFeatures.TOKEN_SUPPLY_BY_BLOCK)
            from aiochainscan.modules.base import _facade_injection, _resolve_api_context
            from aiochainscan.services.token import (
                get_token_total_supply_by_block as _svc_token_total_supply_by_block,
            )

            http, endpoint = _facade_injection(self._client)
            api_kind, network, api_key = _resolve_api_context(self._client)
            return await _svc_token_total_supply_by_block(
                contract=contract,
                block_no=block_no,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=endpoint,
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
            from aiochainscan.modules.base import _facade_injection
            from aiochainscan.services.token import get_token_balance as _svc_get_token_balance

            http, endpoint = _facade_injection(self._client)
            from aiochainscan.modules.base import _resolve_api_context

            api_kind, network, api_key = _resolve_api_context(self._client)
            value: int = await _svc_get_token_balance(
                holder=address,
                token_contract=contract,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=endpoint,
            )
            return str(value)
        else:
            # Use historical balance endpoint via service
            require_feature_support(self._client, ChainFeatures.TOKEN_BALANCE_BY_BLOCK)
            from aiochainscan.modules.base import _facade_injection, _resolve_api_context
            from aiochainscan.services.token import (
                get_token_balance_history as _svc_token_balance_history,
            )

            http, endpoint = _facade_injection(self._client)
            api_kind, network, api_key = _resolve_api_context(self._client)
            return await _svc_token_balance_history(
                contract=contract,
                address=address,
                block_no=block_no,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=endpoint,
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

        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.token import get_token_balance as _svc_get_token_balance

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        value: int = await _svc_get_token_balance(
            holder=address,
            token_contract=contract_address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return str(value)

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
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.token import (
            get_token_holder_list as _svc_holder_list,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_holder_list(
            contract_address=contract_address,
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return list(data)

    async def token_info(
        self,
        contract_address: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get Token Info by ContractAddress"""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.token import get_token_info as _svc_token_info

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_token_info(
            contract_address=contract_address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return list(data)

    async def token_holding_erc20(
        self,
        address: str,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get Address ERC20 Token Holding"""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.token import (
            get_address_token_balance as _svc_address_token_balance,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_address_token_balance(
            address=address,
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return list(data)

    async def token_holding_erc721(
        self,
        address: str,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get Address ERC721 Token Holding"""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.token import (
            get_address_token_nft_balance as _svc_address_token_nft_balance,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_address_token_nft_balance(
            address=address,
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return list(data)

    async def token_inventory(
        self,
        address: str,
        contract_address: str,
        page: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get Address ERC721 Token Inventory By Contract Address"""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.token import (
            get_address_token_nft_inventory as _svc_address_token_nft_inventory,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_address_token_nft_inventory(
            address=address,
            contract_address=contract_address,
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return list(data)
