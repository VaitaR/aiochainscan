from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any

from aiochainscan.constants import CACHE_DEFAULT_MAX_SIZE
from aiochainscan.ports.cache import Cache


class InMemoryCache(Cache):
    """LRU in-memory cache with optional TTL per entry and max size limit.

    Implements Least Recently Used (LRU) eviction strategy:
    - When cache reaches max_size, oldest (least recently used) entries are evicted
    - Accessed items are moved to the end (most recently used position)
    - Expired items are checked lazily on get() only (O(1) per access)

    Performance note: TTL expiration is intentionally lazy (checked only on get)
    to avoid O(N) scans that would block the event loop. This is critical for
    async performance with large caches (100K+ entries).

    Thread-safe for concurrent async access via asyncio.Lock protection
    around all cache state mutations.

    Not suitable for multi-process use. Intended for local composition/tests.
    For production use with multiple processes, consider Redis-based cache.

    Args:
        max_size: Maximum number of entries to store. When exceeded, oldest
                  entries are evicted. Default is CACHE_DEFAULT_MAX_SIZE (10,000).
    """

    def __init__(self, max_size: int | None = None) -> None:
        effective_max_size = max_size if max_size is not None else CACHE_DEFAULT_MAX_SIZE
        if effective_max_size <= 0:
            raise ValueError(f'max_size must be greater than 0, got {effective_max_size}')
        self._store: OrderedDict[str, tuple[Any, float | None]] = OrderedDict()
        self._max_size = effective_max_size
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
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
        async with self._lock:
            # LRU eviction only - NO O(N) expired keys scan!
            # TTL is checked lazily in get() to avoid blocking the event loop.
            # This is critical for async performance with large caches.
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
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        """Remove all entries from the cache."""
        async with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        """Return the number of entries in the cache.

        Note: This is a synchronous method and reads the dict without lock.
        While dict operations are atomic in CPython, this may return stale
        size during concurrent modifications. For production use cases
        requiring exact size guarantees, consider using an async size() method.
        """
        return len(self._store)
