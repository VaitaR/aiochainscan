from __future__ import annotations

import asyncio
import time

from aiochainscan.ports.rate_limiter import RateLimiter


class SimpleRateLimiter(RateLimiter):
    """Naive per-key rate limiter enforcing a minimum interval between calls.

    This is cooperative and suitable for tests/single-process use only.
    """

    def __init__(self, *, min_interval_seconds: float = 0.0) -> None:
        self._min_interval: float = float(min_interval_seconds)
        self._last_call: dict[str, float] = {}

    async def acquire(self, key: str) -> None:
        if self._min_interval <= 0.0:
            return
        now = time.monotonic()
        last = self._last_call.get(key)
        if last is not None:
            elapsed = now - last
            remaining = self._min_interval - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_call[key] = time.monotonic()
