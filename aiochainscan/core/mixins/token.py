"""Token-domain API mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import Any, Protocol

from ...domain.models import Address
from ..method import Method
from ..types import JSONDict


class _TokenClientProtocol(Protocol):
    async def call(self, method: Method, **params: Any) -> Any: ...


class TokenMixin:
    """Token-focused typed convenience methods."""

    async def get_token_balance(
        self: _TokenClientProtocol, address: str, contract_address: str, tag: str = 'latest'
    ) -> str:
        result: str = await self.call(
            Method.TOKEN_BALANCE,
            address=str(Address(address)),
            contractaddress=str(Address(contract_address)),
            tag=tag,
        )
        return str(result)

    async def get_token_info(self: _TokenClientProtocol, contract_address: str) -> JSONDict:
        result: JSONDict = await self.call(
            Method.TOKEN_INFO, contractaddress=str(Address(contract_address))
        )
        return result

    async def get_token_supply(self: _TokenClientProtocol, contract_address: str) -> str:
        result: str = await self.call(Method.TOKEN_SUPPLY, contractaddress=contract_address)
        return str(result)
