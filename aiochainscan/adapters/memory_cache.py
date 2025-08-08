from __future__ import annotations

import time
from typing import Any

from aiochainscan.ports.cache import Cache


class InMemoryCache(Cache):
    """Simple in-memory cache with optional TTL per entry.

    Not suitable for multi-process use. Intended for local composition/tests.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float | None]] = {}

    async def get(self, key: str) -> Any | None:
        value_exp = self._store.get(key)
        if value_exp is None:
            return None
        value, expires_at = value_exp
        if expires_at is not None and time.time() >= expires_at:
            # expired
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        expires_at: float | None = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = time.time() + float(ttl_seconds)
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
