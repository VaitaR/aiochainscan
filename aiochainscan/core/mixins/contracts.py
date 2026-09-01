"""Contract-domain API mixin for ``ChainscanClient``."""

from __future__ import annotations

import json
from typing import Any, Protocol, cast

from ...domain.contract import SmartContract
from ...domain.models import Address
from ..method import Method
from ..types import JSONDict, JSONList


class _ContractClientProtocol(Protocol):
    async def call(self, method: Method, **params: Any) -> Any: ...


class ContractMixin:
    """Contract-focused typed convenience methods."""

    async def get_contract_abi(self: _ContractClientProtocol, address: str) -> str:
        """Get contract ABI as JSON string."""
        result: Any = await self.call(Method.CONTRACT_ABI, address=str(Address(address)))
        return result if isinstance(result, str) else json.dumps(result)

    async def get_contract_source(self: _ContractClientProtocol, address: str) -> JSONDict:
        """Get verified contract source code."""
        result: Any = await self.call(Method.CONTRACT_SOURCE, address=str(Address(address)))
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return next((item for item in result if isinstance(item, dict)), {})
        return {}

    async def get_contract_creation(
        self: _ContractClientProtocol, addresses: list[str]
    ) -> JSONList:
        """Get contract creator and creation tx hash."""
        result: Any = await self.call(
            Method.CONTRACT_CREATION,
            contract_addresses=','.join(str(Address(address)) for address in addresses),
        )
        return result if isinstance(result, list) else []

    async def get_contract(self: _ContractClientProtocol, address: str) -> SmartContract:
        """Get a SmartContract instance with automatic ABI fetching."""
        return await SmartContract.from_address(address, cast(Any, self))
