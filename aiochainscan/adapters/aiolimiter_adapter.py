"""Token Bucket rate limiter adapter using aiolimiter."""

from __future__ import annotations

import asyncio

from aiolimiter import AsyncLimiter

from aiochainscan.ports.rate_limiter import RateLimiter


class AioLimiterAdapter(RateLimiter):
    """Rate limiter using Token Bucket algorithm via aiolimiter.

    Supports multiple isolated rate limiters keyed by string identifier.
    Thread-safe lazy initialization of limiters using double-checked locking.

    Args:
        max_rate: Maximum number of requests allowed per time period.
        time_period: Time period in seconds for the rate limit window.
    """

    def __init__(self, max_rate: float = 5.0, time_period: float = 1.0) -> None:
        self._max_rate = max_rate
        self._time_period = time_period
        self._limiters: dict[str, AsyncLimiter] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str | None = None) -> None:
        """Acquire a rate limit slot for the given key.

        Each unique key has its own isolated rate limiter.
        If key is None, uses a default limiter.
        """
        effective_key = key or '__default__'

        # Fast path: limiter already exists
        if effective_key in self._limiters:
            await self._limiters[effective_key].acquire()
            return

        # Slow path: create limiter with lock (double-checked locking)
        async with self._lock:
            if effective_key not in self._limiters:
                self._limiters[effective_key] = AsyncLimiter(
                    max_rate=self._max_rate,
                    time_period=self._time_period,
                )

        await self._limiters[effective_key].acquire()

    @property
    def max_rate(self) -> float:
        """Maximum number of requests allowed per time period."""
        return self._max_rate

    @property
    def time_period(self) -> float:
        """Time period in seconds for the rate limit window."""
        return self._time_period
