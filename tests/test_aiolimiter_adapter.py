"""Tests for AioLimiterAdapter."""

from __future__ import annotations

import asyncio
import time

import pytest

from aiochainscan.adapters.aiolimiter_adapter import AioLimiterAdapter
from aiochainscan.adapters.simple_rate_limiter import SimpleRateLimiter


class TestAioLimiterAdapter:
    """Tests for the AioLimiterAdapter class."""

    @pytest.mark.asyncio
    async def test_basic_acquire_works(self) -> None:
        """Test that basic acquire completes without error."""
        limiter = AioLimiterAdapter(max_rate=10.0, time_period=1.0)
        # Should complete without raising
        await limiter.acquire('test_key')

    @pytest.mark.asyncio
    async def test_default_key_uses_default_limiter(self) -> None:
        """Test that default key parameter uses the default limiter."""
        limiter = AioLimiterAdapter(max_rate=10.0, time_period=1.0)
        # Both should work without error
        await limiter.acquire()
        await limiter.acquire()
        # Check internal state - should have 'default' key
        assert 'default' in limiter._limiters

    @pytest.mark.asyncio
    async def test_key_isolation(self) -> None:
        """Test that different keys have isolated rate limiters."""
        # Create a limiter with very restrictive rate (1 request per second)
        limiter = AioLimiterAdapter(max_rate=1.0, time_period=1.0)

        # Acquire for key_a
        await limiter.acquire('key_a')

        # key_b should not be blocked by key_a's acquisition
        start = time.monotonic()
        await limiter.acquire('key_b')
        elapsed = time.monotonic() - start

        # key_b should acquire almost immediately (not waiting for key_a's rate limit)
        assert elapsed < 0.1, f'key_b was blocked for {elapsed}s, expected < 0.1s'

        # Verify both limiters exist
        assert 'key_a' in limiter._limiters
        assert 'key_b' in limiter._limiters

    @pytest.mark.asyncio
    async def test_rate_limiting_throttles_requests(self) -> None:
        """Test that rate limiting actually throttles rapid requests."""
        # 2 requests per second max, with higher burst to test rate limiting
        limiter = AioLimiterAdapter(max_rate=2.0, time_period=1.0, max_burst=2.0)

        start = time.monotonic()

        # Make 4 requests - should take at least 1 second due to rate limiting
        for _ in range(4):
            await limiter.acquire('throttle_test')

        elapsed = time.monotonic() - start

        # With max_rate=2 per second and burst=2, 4 requests should take ~1 second
        # (first 2 immediate, then wait ~1s for next 2)
        assert elapsed >= 0.9, f'Expected >= 0.9s for 4 requests at 2/s, got {elapsed}s'

    @pytest.mark.asyncio
    async def test_multiple_keys_concurrent(self) -> None:
        """Test concurrent acquisition across multiple keys."""
        limiter = AioLimiterAdapter(max_rate=5.0, time_period=1.0)

        async def acquire_multiple(key: str, count: int) -> None:
            for _ in range(count):
                await limiter.acquire(key)

        # Run concurrent acquisitions on different keys
        await asyncio.gather(
            acquire_multiple('key_1', 3),
            acquire_multiple('key_2', 3),
            acquire_multiple('key_3', 3),
        )

        # All keys should have their own limiters
        assert len(limiter._limiters) == 3

    @pytest.mark.asyncio
    async def test_properties(self) -> None:
        """Test that properties return correct values."""
        limiter = AioLimiterAdapter(max_rate=7.5, time_period=2.0, max_burst=3.0)
        assert limiter.max_rate == 7.5
        assert limiter.time_period == 2.0
        assert limiter.max_burst == 3.0

    @pytest.mark.asyncio
    async def test_default_values(self) -> None:
        """Test default constructor values."""
        limiter = AioLimiterAdapter()
        assert limiter.max_rate == 5.0
        assert limiter.time_period == 1.0
        assert limiter.max_burst == 1.0  # Default burst=1 for WAF compatibility

    @pytest.mark.asyncio
    async def test_max_burst_prevents_simultaneous_requests(self) -> None:
        """Test that max_burst=1 prevents burst requests.

        This is critical for API stability with Cloudflare WAF.
        With max_burst=1, only 1 request can fire at a time.
        """
        # max_burst=1 means only 1 request can proceed immediately
        limiter = AioLimiterAdapter(max_rate=10.0, time_period=1.0, max_burst=1.0)

        start = time.monotonic()

        # Try to make 3 requests - with burst=1, they should be serialized
        for _ in range(3):
            await limiter.acquire('burst_test')

        elapsed = time.monotonic() - start

        # With rate=10/s and burst=1, 3 requests should take ~0.2s (2 waits of 0.1s)
        # Allow some margin for timing variance
        assert elapsed >= 0.15, f'Expected >= 0.15s for 3 requests with burst=1, got {elapsed}s'

    @pytest.mark.asyncio
    async def test_high_burst_allows_immediate_requests(self) -> None:
        """Test that high max_burst allows burst of requests.

        With max_burst > 1, multiple requests can proceed immediately
        before rate limiting kicks in.
        """
        # max_burst=5 means 5 requests can proceed immediately
        limiter = AioLimiterAdapter(max_rate=5.0, time_period=1.0, max_burst=5.0)

        start = time.monotonic()

        # Make 3 requests - with burst=5, they should all proceed quickly
        for _ in range(3):
            await limiter.acquire('high_burst_test')

        elapsed = time.monotonic() - start

        # With burst=5, first 3 requests should complete almost instantly
        assert elapsed < 0.3, f'Expected < 0.3s for 3 requests with burst=5, got {elapsed}s'

    @pytest.mark.asyncio
    async def test_double_checked_locking(self) -> None:
        """Test that concurrent first-time acquisitions for same key work correctly."""
        limiter = AioLimiterAdapter(max_rate=100.0, time_period=1.0)

        # Create many concurrent tasks that all try to acquire the same key
        # This tests the double-checked locking pattern
        async def acquire_once(key: str) -> None:
            await limiter.acquire(key)

        # 20 concurrent acquisitions for the same new key
        tasks = [acquire_once('concurrent_key') for _ in range(20)]
        await asyncio.gather(*tasks)

        # Should only have one limiter for the key
        assert 'concurrent_key' in limiter._limiters
        assert len([k for k in limiter._limiters if k == 'concurrent_key']) == 1


@pytest.mark.asyncio
async def test_simple_limiter_serializes_same_key_without_cross_key_locking() -> None:
    limiter = SimpleRateLimiter(min_interval_seconds=0.05)
    start = time.monotonic()
    await asyncio.gather(limiter.acquire('same'), limiter.acquire('same'))
    same_key_elapsed = time.monotonic() - start

    start = time.monotonic()
    await asyncio.gather(limiter.acquire('one'), limiter.acquire('two'))
    different_key_elapsed = time.monotonic() - start

    assert same_key_elapsed >= 0.04
    assert different_key_elapsed < 0.04
