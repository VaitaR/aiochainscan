from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiochainscan.ports.rate_limiter import RetryPolicy

T = TypeVar('T')


class ExponentialBackoffRetry(RetryPolicy):
    """Simple exponential backoff retry adapter for idempotent GETs.

    Not production-hardened; suitable for tests/local runs.
    """

    def __init__(self, *, max_attempts: int = 3, base_delay_seconds: float = 0.2) -> None:
        self._max_attempts = max(1, int(max_attempts))
        self._base_delay = float(base_delay_seconds)

    async def run(self, func: Callable[[], Awaitable[T]]) -> T:  # pragma: no cover - thin wrapper
        attempt = 0
        while True:
            try:
                return await func()
            except Exception:  # noqa: BLE001
                attempt += 1
                if attempt >= self._max_attempts:
                    raise
                await asyncio.sleep(self._base_delay * (2 ** (attempt - 1)))
