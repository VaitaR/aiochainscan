from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

from aiochainscan.ports.cache import Cache


class InMemoryCache(Cache):
    """LRU in-memory cache with optional TTL per entry and max size limit.

    Implements Least Recently Used (LRU) eviction strategy:
    - When cache reaches max_size, oldest (least recently used) entries are evicted
    - Accessed items are moved to the end (most recently used position)
    - Expired items are cleaned up on access (lazy eviction)

    Not suitable for multi-process use. Intended for local composition/tests.
    For production use with multiple processes, consider Redis-based cache.

    Args:
        max_size: Maximum number of entries to store. When exceeded, oldest
                  entries are evicted. Default is 10000.
    """

    def __init__(self, max_size: int = 10000) -> None:
        if max_size <= 0:
            raise ValueError(f'max_size must be greater than 0, got {max_size}')
        self._store: OrderedDict[str, tuple[Any, float | None]] = OrderedDict()
        self._max_size = max_size

    async def get(self, key: str) -> Any | None:
        value_exp = self._store.get(key)
        if value_exp is None:
            return None
        value, expires_at = value_exp
        if expires_at is not None and time.time() >= expires_at:
            # expired - remove entry
            del self._store[key]
            return None
        # Move to end (most recently used) for LRU ordering
        self._store.move_to_end(key)
        return value

    async def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        # Only evict if adding a NEW key and at capacity
        if key not in self._store:
            while len(self._store) >= self._max_size:
                self._store.popitem(last=False)  # Remove oldest (first) item

        expires_at: float | None = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = time.time() + float(ttl_seconds)
        self._store[key] = (value, expires_at)
        # Move to end (most recently used) for LRU ordering
        self._store.move_to_end(key)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        """Remove all entries from the cache."""
        self._store.clear()

    def __len__(self) -> int:
        """Return the number of entries in the cache."""
        return len(self._store)
