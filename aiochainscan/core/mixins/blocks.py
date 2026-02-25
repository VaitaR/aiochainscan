"""Block-domain API mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import Any, Protocol

from ..method import Method
from ..types import JSONDict


class _BlockClientProtocol(Protocol):
    async def call(self, method: Method, **params: Any) -> Any: ...


class BlockMixin:
    """Block-focused typed convenience methods."""

    async def get_block(self: _BlockClientProtocol, block_number: int | str) -> JSONDict:
        """Get block information by number."""
        result: JSONDict = await self.call(Method.BLOCK_BY_NUMBER, blockno=block_number)
        return result

    async def get_block_reward(self: _BlockClientProtocol, block_number: int) -> JSONDict:
        """Get block mining reward information."""
        result: JSONDict = await self.call(Method.BLOCK_REWARD, blockno=block_number)
        return result

    async def get_block_countdown(self: _BlockClientProtocol, target_block: int) -> JSONDict:
        """Get estimated time to a target block number."""
        result: JSONDict = await self.call(Method.BLOCK_COUNTDOWN, blockno=target_block)
        return result

    async def get_block_by_timestamp(
        self: _BlockClientProtocol, timestamp: int, closest: str = 'before'
    ) -> JSONDict:
        """Get block number by Unix timestamp."""
        result: JSONDict = await self.call(
            Method.BLOCK_NUMBER_BY_TIMESTAMP, timestamp=timestamp, closest=closest
        )
        return result
