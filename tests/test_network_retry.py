"""Tests for Network retry and rate limiting behavior with httpx/tenacity stack.

These tests verify that the Network class correctly integrates with:
- httpx for HTTP requests
- tenacity for retry logic
- aiolimiter for rate limiting
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import httpx
import pytest

from aiochainscan.adapters.aiolimiter_adapter import AioLimiterAdapter
from aiochainscan.adapters.tenacity_retry import TenacityRetryAdapter
from aiochainscan.exceptions import ChainscanRateLimitError
from aiochainscan.network import Network


class StubUrlBuilder:
    """Minimal UrlBuilder replacement pointing to a fixed endpoint."""

    def __init__(self, url: str) -> None:
        self.API_URL = url

    @staticmethod
    def filter_and_sign(
        params: dict[str, Any] | None, headers: dict[str, str] | None
    ) -> tuple[dict[str, Any], dict[str, str]]:
        return dict(params or {}), dict(headers or {})


class CountingRateLimiter(AioLimiterAdapter):
    """Rate limiter that tracks concurrent request count."""

    def __init__(
        self,
        max_rate: float = 2.0,
        time_period: float = 1.0,
        max_burst: float | None = None,
    ) -> None:
        super().__init__(max_rate=max_rate, time_period=time_period, max_burst=max_burst)
        self.acquire_count = 0
        self._active = 0
        self.max_seen = 0
        self._counting_lock = asyncio.Lock()

    async def acquire(self, key: str | None = None) -> None:
        async with self._counting_lock:
            self._active += 1
            self.max_seen = max(self.max_seen, self._active)
            self.acquire_count += 1
        try:
            await super().acquire(key)
        finally:
            async with self._counting_lock:
                self._active -= 1


@pytest.mark.asyncio
async def test_rate_limiter_integration() -> None:
    """Test that Network uses the rate limiter for requests."""
    rate_limiter = CountingRateLimiter(max_rate=10.0, time_period=1.0)
    builder = StubUrlBuilder('https://httpbin.org/get')

    # Use a retry policy with no retries for this test
    retry_policy = TenacityRetryAdapter(max_attempts=1)

    network = Network(
        builder,
        timeout=5.0,
        rate_limiter=rate_limiter,
        retry_policy=retry_policy,
    )

    try:
        # Make a single request - rate limiter should be called
        # Note: This hits a real endpoint, so it's an integration test
        with contextlib.suppress(Exception):
            await network.get()

        assert rate_limiter.acquire_count >= 1
    finally:
        await network.close()


@pytest.mark.asyncio
async def test_retry_policy_integration() -> None:
    """Test that Network uses the retry policy for transient failures."""
    call_count = 0

    class CountingRetryPolicy(TenacityRetryAdapter):
        def __init__(self) -> None:
            super().__init__(
                max_attempts=3,
                min_wait=0.01,
                max_wait=0.1,
                retry_exceptions=(ChainscanRateLimitError, httpx.TimeoutException),
            )

        async def run(self, func):
            nonlocal call_count
            # Track that run was called
            call_count += 1
            return await super().run(func)

    retry_policy = CountingRetryPolicy()
    builder = StubUrlBuilder('https://httpbin.org/get')

    network = Network(
        builder,
        timeout=5.0,
        retry_policy=retry_policy,
    )

    try:
        with contextlib.suppress(Exception):
            await network.get()

        assert call_count == 1  # run() should have been called
    finally:
        await network.close()


@pytest.mark.asyncio
async def test_custom_timeout() -> None:
    """Test that custom timeout is applied to httpx client."""
    builder = StubUrlBuilder('https://httpbin.org/delay/10')

    network = Network(
        builder,
        timeout=0.1,  # Very short timeout
        retry_policy=TenacityRetryAdapter(max_attempts=1, retry_exceptions=()),
    )

    try:
        with pytest.raises(httpx.TimeoutException):
            await network.get()
    finally:
        await network.close()


@pytest.mark.asyncio
async def test_network_close_idempotent() -> None:
    """Test that Network.close() can be called multiple times safely."""
    builder = StubUrlBuilder('https://example.com')
    network = Network(builder)

    # Close without ever making a request
    await network.close()
    assert network._client is None

    # Close again - should be a no-op
    await network.close()
    assert network._client is None

    # Initialize client
    await network._ensure_client()
    assert network._client is not None

    # Close with client
    await network.close()
    assert network._client is None

    # Close again after closing
    await network.close()
    assert network._client is None


@pytest.mark.asyncio
async def test_ensure_client_lazy_initialization() -> None:
    """Test that client is lazily initialized on first request."""
    builder = StubUrlBuilder('https://example.com')
    network = Network(builder)

    try:
        assert network._client is None

        # First call should initialize client
        client1 = await network._ensure_client()
        assert network._client is not None
        assert client1 is network._client

        # Second call should return same client
        client2 = await network._ensure_client()
        assert client2 is client1
    finally:
        await network.close()


@pytest.mark.asyncio
async def test_default_retry_includes_network_errors() -> None:
    """Test that default retry policy includes httpx network errors.

    This is critical for handling connection resets, DNS failures, and
    HTTP/2 protocol errors (GOAWAY, RST_STREAM) that occur when APIs
    behind Cloudflare WAF terminate connections.
    """
    builder = StubUrlBuilder('https://example.com')
    network = Network(builder)

    try:
        # Verify the default retry policy includes all necessary exceptions
        retry_policy = network._retry_policy
        assert hasattr(retry_policy, 'retry_exceptions')

        retry_exceptions = retry_policy.retry_exceptions
        assert ChainscanRateLimitError in retry_exceptions
        assert httpx.TimeoutException in retry_exceptions
        assert httpx.NetworkError in retry_exceptions
        assert httpx.RemoteProtocolError in retry_exceptions
    finally:
        await network.close()


@pytest.mark.asyncio
async def test_http2_disabled_by_default() -> None:
    """Test that HTTP/2 is disabled by default for WAF compatibility.

    HTTP/2 multiplexing causes Cloudflare WAF to interpret concurrent
    requests as Layer 7 DDoS attacks, resulting in GOAWAY/RST_STREAM
    instead of HTTP 429 responses.
    """
    builder = StubUrlBuilder('https://example.com')
    network = Network(builder)

    try:
        assert network._http2 is False
        assert network._max_connections == 10

        # Client should be created with http2=False
        client = await network._ensure_client()  # noqa: F841
        # httpx.AsyncClient doesn't expose http2 directly, but we verified
        # our config is correct
        assert network._http2 is False
    finally:
        await network.close()


@pytest.mark.asyncio
async def test_default_rate_limiter_has_burst_1() -> None:
    """Test that default rate limiter has max_burst=1 for WAF compatibility.

    With max_burst=1, requests are strictly serialized to prevent
    Cloudflare/Etherscan WAF from detecting burst patterns as DDoS.
    """
    builder = StubUrlBuilder('https://example.com')
    network = Network(builder)

    try:
        # Verify the default rate limiter has burst=1
        rate_limiter = network._rate_limiter
        assert hasattr(rate_limiter, 'max_burst')
        assert rate_limiter.max_burst == 1.0
        assert rate_limiter.max_rate == 5.0  # Default RPS
    finally:
        await network.close()


@pytest.mark.asyncio
async def test_network_error_subclasses() -> None:
    """Test that httpx.NetworkError covers all connection error types.

    This ensures that ConnectError, ReadError, WriteError are all caught
    by retrying on NetworkError.
    """
    # Verify the exception hierarchy
    assert issubclass(httpx.ConnectError, httpx.NetworkError)
    assert issubclass(httpx.ReadError, httpx.NetworkError)
    assert issubclass(httpx.WriteError, httpx.NetworkError)
    assert issubclass(httpx.CloseError, httpx.NetworkError)

    # RemoteProtocolError is separate and also needs explicit handling
    assert not issubclass(httpx.RemoteProtocolError, httpx.NetworkError)
