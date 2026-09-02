"""Stats/gas supply API mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import Any, Protocol

from ...domain.method import Method
from ..types import JSONDict


class _StatsClientProtocol(Protocol):
    async def call(self, method: Method, **params: Any) -> Any: ...


class StatsMixin:
    """Stats-focused typed convenience methods."""

    async def get_eth_price(self: _StatsClientProtocol) -> JSONDict:
        result: JSONDict = await self.call(Method.ETH_PRICE)
        return result

    async def get_gas_oracle(self: _StatsClientProtocol) -> JSONDict:
        result: JSONDict = await self.call(Method.GAS_ORACLE)
        return result

    async def get_gas_estimate(self: _StatsClientProtocol, gas_price: int) -> str:
        result: str = await self.call(Method.GAS_ESTIMATE, gas_price=gas_price)
        return str(result)

    async def get_eth_supply(self: _StatsClientProtocol) -> str:
        result: str = await self.call(Method.ETH_SUPPLY)
        return str(result)
