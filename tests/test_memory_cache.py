"""Tests for InMemoryCache to verify eviction bug fixes."""

import pytest

from aiochainscan.adapters.memory_cache import InMemoryCache


@pytest.mark.asyncio
async def test_max_size_validation():
    """Test that max_size must be greater than 0."""
    # Should raise ValueError for max_size <= 0
    with pytest.raises(ValueError, match='max_size must be greater than 0'):
        InMemoryCache(max_size=0)

    with pytest.raises(ValueError, match='max_size must be greater than 0'):
        InMemoryCache(max_size=-1)

    # Should work for max_size > 0
    cache = InMemoryCache(max_size=1)
    assert cache._max_size == 1


@pytest.mark.asyncio
async def test_update_existing_key_does_not_evict():
    """Test that updating an existing key at max capacity does NOT evict entries."""
    cache = InMemoryCache(max_size=2)

    # Fill cache to max capacity
    await cache.set('a', 1)
    await cache.set('b', 2)
    assert len(cache) == 2

    # Update existing key 'a' - should NOT evict 'b'
    await cache.set('a', 3)
    assert len(cache) == 2

    # Verify both keys still exist
    assert await cache.get('a') == 3
    assert await cache.get('b') == 2


@pytest.mark.asyncio
async def test_add_new_key_evicts_oldest():
    """Test that adding a NEW key at max capacity evicts the oldest entry."""
    cache = InMemoryCache(max_size=2)

    # Fill cache to max capacity
    await cache.set('a', 1)
    await cache.set('b', 2)
    assert len(cache) == 2

    # Add NEW key 'c' - should evict oldest ('a')
    await cache.set('c', 3)
    assert len(cache) == 2

    # 'a' should be evicted, 'b' and 'c' should exist
    assert await cache.get('a') is None
    assert await cache.get('b') == 2
    assert await cache.get('c') == 3


@pytest.mark.asyncio
async def test_lru_order_preserved_on_update():
    """Test that LRU order is maintained correctly when updating keys."""
    cache = InMemoryCache(max_size=3)

    # Add three entries
    await cache.set('a', 1)
    await cache.set('b', 2)
    await cache.set('c', 3)

    # Access 'a' to make it most recently used
    await cache.get('a')

    # Update 'b' - should also move it to end
    await cache.set('b', 20)

    # Add new key 'd' - should evict 'c' (oldest)
    await cache.set('d', 4)

    assert await cache.get('a') == 1
    assert await cache.get('b') == 20
    assert await cache.get('c') is None  # Evicted
    assert await cache.get('d') == 4


@pytest.mark.asyncio
async def test_multiple_updates_at_capacity():
    """Test multiple updates at max capacity don't cause unexpected evictions."""
    cache = InMemoryCache(max_size=2)

    await cache.set('key1', 'value1')
    await cache.set('key2', 'value2')

    # Update both keys multiple times
    for i in range(5):
        await cache.set('key1', f'value1_{i}')
        await cache.set('key2', f'value2_{i}')

    # Both keys should still exist
    assert await cache.get('key1') == 'value1_4'
    assert await cache.get('key2') == 'value2_4'
    assert len(cache) == 2


@pytest.mark.asyncio
async def test_expired_keys_cleared_before_eviction():
    """Test that expired keys are cleared before LRU eviction.

    This is a regression test for Low Severity bug where expired keys
    were not cleared before eviction, causing valid entries to be evicted
    while expired entries remained in the cache.
    """
    import time

    cache = InMemoryCache(max_size=3)

    # Add entries with short TTL that will expire
    await cache.set('expired1', 'val1', ttl_seconds=1)
    await cache.set('expired2', 'val2', ttl_seconds=1)

    # Wait for them to expire
    time.sleep(1.1)

    # Add a valid entry - should clear expired keys first, not evict by LRU
    await cache.set('valid', 'valid_value')

    # Valid entry should exist
    assert await cache.get('valid') == 'valid_value'

    # Expired entries should be gone (cleared before eviction, not after)
    assert await cache.get('expired1') is None
    assert await cache.get('expired2') is None

    # Cache should only have 1 entry (valid), not 3
    assert len(cache) == 1


@pytest.mark.asyncio
async def test_concurrent_access_thread_safety():
    """Test that concurrent get/set operations don't cause race conditions.

    This is a regression test for the race condition bug where async methods
    used plain OrderedDict without locks, potentially causing inconsistent
    cache state during concurrent eviction operations.
    """
    import asyncio

    cache = InMemoryCache(max_size=10)

    # Concurrent writes to different keys
    async def write_task(key_prefix: str, count: int):
        for i in range(count):
            await cache.set(f'{key_prefix}_{i}', f'value_{i}')

    # Concurrent reads
    async def read_task(key: str, iterations: int):
        for _ in range(iterations):
            await cache.get(key)

    # Run concurrent operations
    tasks = [
        write_task('task1', 20),
        write_task('task2', 20),
        write_task('task3', 20),
        read_task('task1_5', 10),
        read_task('task2_5', 10),
    ]

    await asyncio.gather(*tasks)

    # Cache should be at max size due to evictions
    assert len(cache) == 10

    # All operations should complete without errors (lock prevents race conditions)
    # If there was a race condition, we might see:
    # - Inconsistent cache state
    # - KeyError during eviction
    # - Corrupted LRU ordering


@pytest.mark.asyncio
async def test_concurrent_eviction_safety():
    """Test that concurrent operations triggering eviction are safe.

    Specifically tests the eviction loop:
        while len(self._store) >= self._max_size:
            self._store.popitem(...)

    Without lock protection, this loop could be interrupted by another
    coroutine, causing inconsistent state.
    """
    import asyncio

    cache = InMemoryCache(max_size=5)

    # Fill cache to capacity
    for i in range(5):
        await cache.set(f'init_{i}', i)

    # Concurrent set operations that all trigger eviction
    async def concurrent_set(key: str):
        await cache.set(key, 'value')

    keys = [f'concurrent_{i}' for i in range(20)]
    await asyncio.gather(*[concurrent_set(k) for k in keys])

    # Cache should be at max size
    assert len(cache) == 5

    # No race condition errors should occur
    # Without lock, we might see KeyError or size > max_size
