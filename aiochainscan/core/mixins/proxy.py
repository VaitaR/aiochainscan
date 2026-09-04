"""JSON-RPC proxy API mixin for ``ChainscanClient``."""

from __future__ import annotations

from ...domain.method import Method
from ..host import ClientHost


class ProxyMixin:
    """Proxy-focused typed convenience methods."""

    async def eth_call(self: ClientHost, to: str, data: str, tag: str = 'latest') -> str:
        result: str = await self.call(Method.PROXY_ETH_CALL, to=to, data=data, tag=tag)
        return str(result)

    async def eth_get_balance(self: ClientHost, address: str, tag: str = 'latest') -> str:
        result: str = await self.call(Method.PROXY_GET_BALANCE, address=address, tag=tag)
        return str(result)
