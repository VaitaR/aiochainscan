"""Tests for InMemoryCache to verify eviction bug fixes."""
import pytest

from aiochainscan.adapters.memory_cache import InMemoryCache


@pytest.mark.asyncio
async def test_max_size_validation():
    """Test that max_size must be greater than 0."""
    # Should raise ValueError for max_size <= 0
    with pytest.raises(ValueError, match="max_size must be greater than 0"):
        InMemoryCache(max_size=0)
    
    with pytest.raises(ValueError, match="max_size must be greater than 0"):
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
