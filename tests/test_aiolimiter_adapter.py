"""Tests for AioLimiterAdapter."""

from __future__ import annotations

import asyncio
import time

import pytest

from aiochainscan.adapters.aiolimiter_adapter import AioLimiterAdapter


class TestAioLimiterAdapter:
    """Tests for the AioLimiterAdapter class."""

    @pytest.mark.asyncio
    async def test_basic_acquire_works(self) -> None:
        """Test that basic acquire completes without error."""
        limiter = AioLimiterAdapter(max_rate=10.0, time_period=1.0)
        # Should complete without raising
        await limiter.acquire('test_key')

    @pytest.mark.asyncio
    async def test_none_key_uses_default_limiter(self) -> None:
        """Test that None key uses the default limiter."""
        limiter = AioLimiterAdapter(max_rate=10.0, time_period=1.0)
        # Both should work without error
        await limiter.acquire(None)
        await limiter.acquire(None)
        # Check internal state - should have __default__ key
        assert '__default__' in limiter._limiters

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
        # 2 requests per second max
        limiter = AioLimiterAdapter(max_rate=2.0, time_period=1.0)

        start = time.monotonic()

        # Make 4 requests - should take at least 1 second due to rate limiting
        for _ in range(4):
            await limiter.acquire('throttle_test')

        elapsed = time.monotonic() - start

        # With max_rate=2 per second, 4 requests should take ~1 second
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
        limiter = AioLimiterAdapter(max_rate=7.5, time_period=2.0)
        assert limiter.max_rate == 7.5
        assert limiter.time_period == 2.0

    @pytest.mark.asyncio
    async def test_default_values(self) -> None:
        """Test default constructor values."""
        limiter = AioLimiterAdapter()
        assert limiter.max_rate == 5.0
        assert limiter.time_period == 1.0

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
