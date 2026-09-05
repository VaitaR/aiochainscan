"""Token Bucket rate limiter adapter using aiolimiter.

Network Reliability Notes:
- max_burst=1 prevents HTTP/2 GOAWAY/RST_STREAM from API gateways
- Cloudflare/Etherscan WAF interpret burst requests as Layer 7 DDoS
- With burst=1, requests are strictly serialized at rate limit speed
"""

from __future__ import annotations

import asyncio

from aiolimiter import AsyncLimiter

from aiochainscan.ports.rate_limiter import RateLimiter


class AioLimiterAdapter(RateLimiter):
    """Rate limiter using Token Bucket algorithm via aiolimiter.

    Supports multiple isolated rate limiters keyed by string identifier.
    Thread-safe lazy initialization of limiters using double-checked locking.

    The max_burst parameter is critical for API stability:
    - When max_burst > 1, that many requests can fire simultaneously
    - Cloudflare/Etherscan WAF interpret bursts as DDoS attacks
    - With max_burst=1 (default), requests are strictly rate-limited
    - This prevents GOAWAY/RST_STREAM protocol errors

    Args:
        max_rate: Maximum number of requests allowed per time period.
        time_period: Time period in seconds for the rate limit window.
        max_burst: Maximum requests allowed to burst through immediately.
            Default is 1 to prevent WAF/DDoS detection triggers.
            Set higher for non-rate-limited APIs (e.g., local nodes).

    Raises:
        ValueError: Any of the three is not strictly positive.
    """

    def __init__(
        self,
        max_rate: float = 5.0,
        time_period: float = 1.0,
        max_burst: float | None = None,
    ) -> None:
        # Every one of these divides or scales the derived bucket period, so a
        # non-positive value is refused here rather than surfacing later as a
        # bare ZeroDivisionError from ``acquire`` — which the scanner error
        # ladder would translate into a TRANSIENT network fault and cool a
        # perfectly healthy provider.
        if max_rate <= 0:
            raise ValueError(f'max_rate must be greater than 0, got {max_rate}')
        if time_period <= 0:
            raise ValueError(f'time_period must be greater than 0, got {time_period}')
        if max_burst is not None and max_burst <= 0:
            raise ValueError(f'max_burst must be greater than 0, got {max_burst}')

        self._max_rate = max_rate
        self._time_period = time_period
        # Default to 1.0 to prevent burst requests that trigger WAF blocks.
        # The aiolimiter library uses max_rate as bucket capacity by default,
        # but we want strict rate limiting for API gateways.
        self._max_burst = max_burst if max_burst is not None else 1.0
        self._limiters: dict[str, AsyncLimiter] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str = 'default') -> None:
        """Acquire a rate limit slot for the given key.

        Each unique key has its own isolated rate limiter.
        With max_burst=1 (default), this blocks until the rate limit allows.
        """
        effective_key = key

        # Fast path: limiter already exists
        if effective_key in self._limiters:
            await self._limiters[effective_key].acquire()
            return

        # Slow path: create limiter with lock (double-checked locking)
        async with self._lock:
            if effective_key not in self._limiters:
                # Use max_burst as the bucket capacity to control burst behavior.
                # With max_burst=1, only 1 request can proceed at a time.
                self._limiters[effective_key] = AsyncLimiter(
                    max_rate=self._max_burst,  # Bucket capacity (burst limit)
                    time_period=self._time_period / self._max_rate * self._max_burst,
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

    @property
    def max_burst(self) -> float:
        """Maximum requests allowed to burst through immediately."""
        return self._max_burst
