from __future__ import annotations

import asyncio
import time

from aiochainscan.ports.rate_limiter import RateLimiter


class SimpleRateLimiter(RateLimiter):
    """Naive per-key rate limiter enforcing a minimum interval between calls.

    This is cooperative and suitable for tests/single-process use only.
    """

    def __init__(self, *, min_interval_seconds: float = 0.0, burst: int = 1) -> None:
        self._min_interval: float = float(min_interval_seconds)
        self._last_call: dict[str, float] = {}
        # simple token bucket burst allowance (per-key). When >1, allow short bursts.
        self._burst: int = max(1, int(burst))
        self._slots: dict[str, int] = {}

    async def acquire(self, key: str) -> None:
        if self._min_interval <= 0.0:
            return
        now = time.monotonic()
        last = self._last_call.get(key)
        # initialize slots for this key
        slots = self._slots.get(key, self._burst)
        if last is None:
            # first call: spend one slot and record time
            self._slots[key] = max(0, slots - 1)
            self._last_call[key] = now
            return
        elapsed = now - last
        # regenerate slots based on elapsed time and min_interval
        regen = int(elapsed / self._min_interval) if self._min_interval > 0 else 0
        slots = min(self._burst, slots + regen)
        if slots <= 0 and elapsed < self._min_interval:
            remaining = self._min_interval - elapsed
            await asyncio.sleep(remaining)
            now = time.monotonic()
            elapsed = now - last
            regen = int(elapsed / self._min_interval) if self._min_interval > 0 else 0
            slots = min(self._burst, slots + regen)
        # spend a slot and record time
        self._slots[key] = max(0, slots - 1)
        self._last_call[key] = now

    @property
    def min_interval_seconds(self) -> float:
        return self._min_interval

    @property
    def burst(self) -> int:
        return self._burst
