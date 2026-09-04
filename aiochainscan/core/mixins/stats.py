"""Stats/gas supply API mixin for ``ChainscanClient``."""

from __future__ import annotations

from ...domain.method import Method
from ..host import ClientHost
from ..types import JSONDict


class StatsMixin:
    """Stats-focused typed convenience methods."""

    async def get_eth_price(self: ClientHost) -> JSONDict:
        result: JSONDict = await self.call(Method.ETH_PRICE)
        return result

    async def get_gas_oracle(self: ClientHost) -> JSONDict:
        result: JSONDict = await self.call(Method.GAS_ORACLE)
        return result

    async def get_gas_estimate(self: ClientHost, gas_price: int) -> str:
        result: str = await self.call(Method.GAS_ESTIMATE, gas_price=gas_price)
        return str(result)

    async def get_eth_supply(self: ClientHost) -> str:
        result: str = await self.call(Method.ETH_SUPPLY)
        return str(result)
