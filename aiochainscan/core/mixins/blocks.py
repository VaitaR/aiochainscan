"""Block-domain API mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import Any, Protocol, cast

from ...domain.normalize import normalize_block
from ...domain.normalized import Block
from ...exceptions import (
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanDataError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
)
from ..method import Method
from ..types import JSONDict
from ._waiting import api_error_text, poll_until_final


class _BlockClientProtocol(Protocol):
    async def call(self, method: Method, **params: Any) -> Any: ...

    def supports_method(self, method: Method) -> bool: ...


def _to_int(value: Any) -> int | None:
    """Best-effort coercion of a countdown snapshot field to ``int``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _countdown_reached(snapshot: Any, target: int) -> bool:
    """Whether a ``BLOCK_COUNTDOWN`` snapshot reports ``target`` as mined."""
    if not isinstance(snapshot, dict):
        return False
    remaining = _to_int(snapshot.get('RemainingBlock'))
    if remaining is not None and remaining <= 0:
        return True
    current = _to_int(snapshot.get('CurrentBlock'))
    return current is not None and current >= target


class BlockMixin:
    """Block-focused typed convenience methods."""

    async def get_block(self: _BlockClientProtocol, block_number: int | str) -> JSONDict:
        """Get block information by number."""
        result: JSONDict = await self.call(Method.BLOCK_BY_NUMBER, block_number=block_number)
        return result

    async def get_block_normalized(self: _BlockClientProtocol, block_number: int | str) -> Block:
        """Same response as ``get_block``, mapped onto ``domain.normalized.Block``."""
        raw = await BlockMixin.get_block(self, block_number)
        return normalize_block(raw)

    async def get_block_reward(self: _BlockClientProtocol, block_number: int) -> JSONDict:
        """Get block mining reward information."""
        result: JSONDict = await self.call(Method.BLOCK_REWARD, block_number=block_number)
        return result

    async def get_block_countdown(self: _BlockClientProtocol, target_block: int) -> JSONDict:
        """Get estimated time to a target block number."""
        result: JSONDict = await self.call(Method.BLOCK_COUNTDOWN, block_number=target_block)
        return result

    async def get_block_by_timestamp(
        self: _BlockClientProtocol, timestamp: int, closest: str = 'before'
    ) -> JSONDict:
        """Get block number by Unix timestamp."""
        result: JSONDict = await self.call(
            Method.BLOCK_NUMBER_BY_TIMESTAMP, timestamp=timestamp, closest=closest
        )
        return result

    async def wait_for_block(
        self: _BlockClientProtocol,
        block_number: int,
        timeout: float = 600.0,
        poll_interval: float = 10.0,
    ) -> JSONDict:
        """Wait until the chain reaches ``block_number``.

        Scanners that declare ``Method.BLOCK_COUNTDOWN`` (Etherscan-like) are
        polled via the countdown endpoint: the target is reached when the
        countdown reports zero blocks remaining or a current tip at/beyond
        the target — or, the common case since Etherscan only serves
        countdowns for future blocks, when the API answers with its
        documented ``Error! Block number already pass`` error. Scanners
        without countdown support (BlockScout V2) poll
        ``Method.BLOCK_BY_NUMBER`` until the explorer knows the block;
        "not mined yet" answers (404-style) keep the poll going.

        Pick ``timeout`` from a preliminary :meth:`get_block_countdown` call:
        its ``EstimateTimeInSec`` field is the explorer's own ETA for the
        target block.

        Args:
            block_number: Block to wait for.
            timeout: Total wait budget in seconds (default: 600).
            poll_interval: Delay between polls in seconds (default: 10).

        Returns:
            The last countdown snapshot when reached via a live countdown,
            ``{'CountdownBlock': str(block_number), 'RemainingBlock': '0'}``
            when the explorer reports the block as already mined, or the
            block dict itself on the ``BLOCK_BY_NUMBER`` path.

        Raises:
            ValueError: If ``block_number`` is negative or the timing
                arguments are negative.
            ChainscanClientApiError: On hard countdown errors other than the
                documented already-passed answer.
            ChainscanDataError: On the ``BLOCK_BY_NUMBER`` path, immediately
                when the provider reports a configuration/data-contract
                failure (e.g. a chain mismatch) — never polled away.
            ChainscanWaitTimeoutError: If the block is not reached within
                ``timeout`` seconds.
        """
        if block_number < 0:
            raise ValueError(f'block_number must be >= 0, got {block_number!r}')

        if self.supports_method(Method.BLOCK_COUNTDOWN):

            async def probe() -> tuple[bool, Any]:
                try:
                    result: Any = await self.call(
                        Method.BLOCK_COUNTDOWN, block_number=block_number
                    )
                except ChainscanClientApiError as exc:
                    # The sentence lives in ``message`` on live BlockScout v1
                    # (result is null) and in ``result`` on Etherscan —
                    # match both (shared api_error_text convention).
                    if 'already pass' in api_error_text(exc):
                        return True, {
                            'CountdownBlock': str(block_number),
                            'RemainingBlock': '0',
                        }
                    raise
                except ChainscanRateLimitError as exc:
                    return False, exc
                return _countdown_reached(result, block_number), result

        else:

            async def probe() -> tuple[bool, Any]:
                try:
                    result: Any = await self.call(
                        Method.BLOCK_BY_NUMBER, block_number=block_number
                    )
                except ChainscanRateLimitError as exc:
                    return False, exc
                except ChainscanNetworkError as exc:
                    if exc.retryable:
                        raise
                    return False, exc
                except ChainscanDataError:
                    # Configuration/data-contract failures (e.g. the
                    # expected-chain guard's chain mismatch) never heal by
                    # polling — surface immediately instead of timing out
                    # after the full budget.
                    raise
                except ChainscanClientError as exc:
                    return False, exc
                return isinstance(result, dict) and bool(result), result

        return cast(
            JSONDict,
            await poll_until_final(
                probe,
                what=f'block {block_number} to be mined',
                timeout=timeout,
                poll_interval=poll_interval,
            ),
        )
