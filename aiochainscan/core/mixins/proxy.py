"""JSON-RPC proxy API mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import Any, Protocol

from ..method import Method


class _ProxyClientProtocol(Protocol):
    async def call(self, method: Method, **params: Any) -> Any: ...


class ProxyMixin:
    """Proxy-focused typed convenience methods."""

    async def eth_call(self: _ProxyClientProtocol, to: str, data: str, tag: str = 'latest') -> str:
        result: str = await self.call(Method.PROXY_ETH_CALL, to=to, data=data, tag=tag)
        return str(result)

    async def eth_get_balance(
        self: _ProxyClientProtocol, address: str, tag: str = 'latest'
    ) -> str:
        result: str = await self.call(Method.PROXY_GET_BALANCE, address=address, tag=tag)
        return str(result)
