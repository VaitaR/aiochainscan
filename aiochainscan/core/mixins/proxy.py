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

    async def eth_get_storage_at(
        self: ClientHost, address: str, position: str, tag: str = 'latest'
    ) -> str:
        """Read one 32-byte storage slot.

        ``position`` is the slot key as a hex string; the result is the raw
        word, so a slot holding an address carries it in the low 20 bytes.
        This is what makes a proxy readable when the explorer has not flagged
        one — see ``domain/contract.py`` for the slot ladder built on it.
        """
        result: str = await self.call(
            Method.PROXY_GET_STORAGE_AT, address=address, position=position, tag=tag
        )
        return str(result)
