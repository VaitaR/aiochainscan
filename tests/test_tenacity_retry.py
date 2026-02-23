"""Tests for TenacityRetryAdapter.

These tests verify the retry behavior of the tenacity-based retry adapter,
including exception handling, backoff timing, and custom callbacks.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest
from tenacity import RetryCallState

from aiochainscan.adapters.tenacity_retry import (
    DEFAULT_RETRY_EXCEPTIONS,
    TenacityRetryAdapter,
)
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanRateLimitError,
)


class TestTenacityRetryAdapterBasics:
    """Basic initialization and interface tests."""

    def test_implements_retry_policy_protocol(self) -> None:
        """Adapter should implement the RetryPolicy protocol (structural check)."""
        adapter = TenacityRetryAdapter()
        # Protocol conformance is structural in Python - we check the method exists
        # and has the correct signature rather than using isinstance
        assert hasattr(adapter, 'run')
        assert callable(adapter.run)

    def test_default_configuration(self) -> None:
        """Adapter should have sensible defaults."""
        adapter = TenacityRetryAdapter()
        assert adapter.max_attempts == 5
        assert adapter.min_wait == 1.0
        assert adapter.max_wait == 30.0
        assert adapter.jitter == 1.0
        assert adapter.retry_exceptions == DEFAULT_RETRY_EXCEPTIONS
        assert adapter.reraise is True

    def test_custom_configuration(self) -> None:
        """Adapter should accept custom configuration."""
        adapter = TenacityRetryAdapter(
            max_attempts=10,
            min_wait=0.5,
            max_wait=60.0,
            jitter=2.0,
            retry_exceptions=(ValueError, RuntimeError),
            reraise=False,
        )
        assert adapter.max_attempts == 10
        assert adapter.min_wait == 0.5
        assert adapter.max_wait == 60.0
        assert adapter.jitter == 2.0
        assert adapter.retry_exceptions == (ValueError, RuntimeError)
        assert adapter.reraise is False

    def test_min_values_clamped(self) -> None:
        """Adapter should clamp values to sensible minimums."""
        adapter = TenacityRetryAdapter(
            max_attempts=0,  # Should become 1
            min_wait=-1.0,  # Should become 0.0
            max_wait=-1.0,  # Should become min_wait
            jitter=-1.0,  # Should become 0.0
        )
        assert adapter.max_attempts == 1
        assert adapter.min_wait == 0.0
        assert adapter.max_wait >= adapter.min_wait
        assert adapter.jitter == 0.0

    def test_repr(self) -> None:
        """Adapter should have a useful repr."""
        adapter = TenacityRetryAdapter(max_attempts=3, min_wait=0.5, max_wait=10.0)
        repr_str = repr(adapter)
        assert 'TenacityRetryAdapter' in repr_str
        assert 'max_attempts=3' in repr_str
        assert 'min_wait=0.5' in repr_str
        assert 'max_wait=10.0' in repr_str


class TestRetryOnException:
    """Tests for retry behavior on exceptions."""

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit_error(self) -> None:
        """Should retry when ChainscanRateLimitError is raised."""
        call_count = 0

        async def failing_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ChainscanRateLimitError('NOTOK', 'Max rate limit reached')
            return 'success'

        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,  # Fast for testing
            max_wait=0.1,
            jitter=0.0,
        )

        result = await adapter.run(failing_func)

        assert result == 'success'
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_unhandled_exception(self) -> None:
        """Should not retry on exceptions not in retry_exceptions."""
        call_count = 0

        async def failing_func() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError('Not a retryable error')

        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,
            retry_exceptions=(ChainscanRateLimitError,),  # ValueError not included
        )

        with pytest.raises(ValueError, match='Not a retryable error'):
            await adapter.run(failing_func)

        assert call_count == 1  # Only called once, no retry

    @pytest.mark.asyncio
    async def test_max_attempts_reached(self) -> None:
        """Should raise exception after max attempts exhausted."""
        call_count = 0

        async def always_failing() -> str:
            nonlocal call_count
            call_count += 1
            raise ChainscanRateLimitError('NOTOK', 'Max rate limit reached')

        adapter = TenacityRetryAdapter(
            max_attempts=3,
            min_wait=0.01,
            max_wait=0.1,
            jitter=0.0,
        )

        with pytest.raises(ChainscanRateLimitError):
            await adapter.run(always_failing)

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_custom_exceptions(self) -> None:
        """Should retry on custom exception types."""
        call_count = 0

        async def failing_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError('Network error')
            return 'success'

        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,
            retry_exceptions=(ConnectionError, TimeoutError),
        )

        result = await adapter.run(failing_func)

        assert result == 'success'
        assert call_count == 2


class TestExponentialBackoff:
    """Tests for exponential backoff timing."""

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self) -> None:
        """Should use exponential backoff between retries."""
        timestamps: list[float] = []

        async def failing_func() -> str:
            timestamps.append(time.monotonic())
            if len(timestamps) < 4:
                raise ChainscanRateLimitError('NOTOK', 'Rate limit')
            return 'success'

        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.05,  # 50ms initial
            max_wait=1.0,
            jitter=0.0,  # No jitter for predictable timing
        )

        await adapter.run(failing_func)

        assert len(timestamps) == 4

        # Check that delays increase exponentially
        # First delay should be ~50ms, second ~100ms, third ~200ms
        delays = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]

        # Allow some tolerance for test execution overhead
        assert delays[0] >= 0.04, f'First delay {delays[0]} should be >= 0.04'
        assert delays[1] >= delays[0] * 1.5, f'Second delay {delays[1]} should be > first'
        assert delays[2] >= delays[1] * 1.5, f'Third delay {delays[2]} should be > second'

    @pytest.mark.asyncio
    async def test_max_wait_cap(self) -> None:
        """Should cap wait time at max_wait."""
        timestamps: list[float] = []

        async def failing_func() -> str:
            timestamps.append(time.monotonic())
            if len(timestamps) < 5:
                raise ChainscanRateLimitError('NOTOK', 'Rate limit')
            return 'success'

        adapter = TenacityRetryAdapter(
            max_attempts=6,
            min_wait=0.05,
            max_wait=0.1,  # Cap at 100ms
            jitter=0.0,
        )

        await adapter.run(failing_func)

        delays = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]

        # All delays should be <= max_wait + some tolerance
        for i, delay in enumerate(delays):
            assert delay <= 0.2, f'Delay {i} ({delay}) should be <= 0.2 (max_wait + tolerance)'


class TestCallbacks:
    """Tests for callback functionality."""

    @pytest.mark.asyncio
    async def test_before_sleep_callback_called(self) -> None:
        """Should call before_sleep_callback on each retry."""
        callback_attempts: list[int] = []
        call_count = 0

        def track_callback(retry_state: RetryCallState) -> None:
            callback_attempts.append(retry_state.attempt_number)

        async def failing_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ChainscanRateLimitError('NOTOK', 'Rate limit')
            return 'success'

        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,
            before_sleep_callback=track_callback,
        )

        await adapter.run(failing_func)

        # 2 failures = 2 callbacks (called before sleeping after each failure)
        assert len(callback_attempts) == 2
        # Attempts are numbered 1, 2 for the two failures before success on attempt 3
        assert callback_attempts == [1, 2]

    @pytest.mark.asyncio
    async def test_callback_receives_exception_info(self) -> None:
        """Callback should receive exception information."""
        captured_exception: Exception | None = None

        def capture_callback(retry_state: RetryCallState) -> None:
            nonlocal captured_exception
            if retry_state.outcome:
                captured_exception = retry_state.outcome.exception()

        call_count = 0

        async def failing_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ChainscanRateLimitError('NOTOK', 'Test rate limit message')
            return 'success'

        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,
            before_sleep_callback=capture_callback,
        )

        await adapter.run(failing_func)

        assert captured_exception is not None
        assert isinstance(captured_exception, ChainscanRateLimitError)
        assert 'Test rate limit message' in str(captured_exception)


class TestWrapDecorator:
    """Tests for the wrap() decorator method."""

    @pytest.mark.asyncio
    async def test_wrap_decorator_retries(self) -> None:
        """Wrapped function should retry on exception."""
        call_count = 0
        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,
            retry_exceptions=(ValueError,),
        )

        @adapter.wrap
        async def flaky_function(multiplier: int) -> int:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError('Temporary error')
            return 42 * multiplier

        result = await flaky_function(2)

        assert result == 84
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_wrap_preserves_function_metadata(self) -> None:
        """Wrapped function should preserve original function's metadata."""
        adapter = TenacityRetryAdapter()

        @adapter.wrap
        async def documented_function() -> str:
            """This is a documented function."""
            return 'result'

        assert documented_function.__name__ == 'documented_function'
        assert documented_function.__doc__ == 'This is a documented function.'

    @pytest.mark.asyncio
    async def test_wrap_with_args_and_kwargs(self) -> None:
        """Wrapped function should handle args and kwargs correctly."""
        adapter = TenacityRetryAdapter(
            max_attempts=2,
            min_wait=0.01,
            retry_exceptions=(RuntimeError,),
        )

        @adapter.wrap
        async def func_with_args(a: int, b: int, *, c: int = 0) -> int:
            return a + b + c

        result = await func_with_args(1, 2, c=3)
        assert result == 6


class TestWithExceptions:
    """Tests for the with_exceptions() method."""

    def test_with_exceptions_creates_new_adapter(self) -> None:
        """with_exceptions should return a new adapter instance."""
        original = TenacityRetryAdapter(
            max_attempts=3,
            retry_exceptions=(ChainscanRateLimitError,),
        )

        extended = original.with_exceptions(ConnectionError, TimeoutError)

        assert extended is not original
        assert original.retry_exceptions == (ChainscanRateLimitError,)
        assert extended.retry_exceptions == (
            ChainscanRateLimitError,
            ConnectionError,
            TimeoutError,
        )

    def test_with_exceptions_preserves_other_settings(self) -> None:
        """with_exceptions should preserve all other settings."""
        callback = MagicMock()
        original = TenacityRetryAdapter(
            max_attempts=7,
            min_wait=2.0,
            max_wait=45.0,
            jitter=3.0,
            before_sleep_callback=callback,
            reraise=False,
        )

        extended = original.with_exceptions(IOError)

        assert extended.max_attempts == 7
        assert extended.min_wait == 2.0
        assert extended.max_wait == 45.0
        assert extended.jitter == 3.0
        assert extended.before_sleep_callback is callback
        assert extended.reraise is False

    @pytest.mark.asyncio
    async def test_with_exceptions_retries_added_exceptions(self) -> None:
        """Extended adapter should retry on newly added exceptions."""
        call_count = 0
        original = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,
            retry_exceptions=(ChainscanRateLimitError,),
        )

        extended = original.with_exceptions(IOError)

        async def failing_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError('Temporary IO error')
            return 'success'

        result = await extended.run(failing_func)

        assert result == 'success'
        assert call_count == 2


class TestRetryingContextManager:
    """Tests for the retrying() method returning AsyncRetrying."""

    @pytest.mark.asyncio
    async def test_retrying_manual_control(self) -> None:
        """Should allow manual retry control with retrying()."""
        call_count = 0
        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,
            retry_exceptions=(ValueError,),
        )

        async for attempt in adapter.retrying():
            with attempt:
                call_count += 1
                if call_count < 3:
                    raise ValueError('Retry me')
                result = 'success'

        assert result == 'success'
        assert call_count == 3


class TestIntegrationWithRealExceptions:
    """Integration tests with real exception types from aiochainscan."""

    @pytest.mark.asyncio
    async def test_retry_chain_with_mixed_exceptions(self) -> None:
        """Should handle a chain of different retryable exceptions."""
        call_count = 0

        async def multi_failure_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ChainscanRateLimitError('NOTOK', 'Rate limit')
            if call_count == 2:
                raise ConnectionError('Connection reset')
            return 'success'

        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,
            retry_exceptions=(ChainscanRateLimitError, ConnectionError),
        )

        result = await adapter.run(multi_failure_func)

        assert result == 'success'
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_chainscan_error_not_retried(self) -> None:
        """Should not retry ChainscanClientApiError by default."""
        call_count = 0

        async def api_error_func() -> str:
            nonlocal call_count
            call_count += 1
            raise ChainscanClientApiError('Error', 'Invalid address')

        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,
            # Only retries ChainscanRateLimitError by default
        )

        with pytest.raises(ChainscanClientApiError):
            await adapter.run(api_error_func)

        assert call_count == 1  # No retry


class TestConcurrentRetries:
    """Tests for concurrent retry scenarios."""

    @pytest.mark.asyncio
    async def test_independent_retry_state(self) -> None:
        """Multiple concurrent calls should have independent retry state."""
        call_counts: dict[str, int] = {'a': 0, 'b': 0}

        async def failing_func(key: str) -> str:
            call_counts[key] += 1
            if call_counts[key] < 3:
                raise ChainscanRateLimitError('NOTOK', f'Rate limit for {key}')
            return f'success_{key}'

        adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=0.01,
            jitter=0.0,
        )

        # Run two retrying operations concurrently
        results = await asyncio.gather(
            adapter.run(lambda: failing_func('a')),
            adapter.run(lambda: failing_func('b')),
        )

        assert results == ['success_a', 'success_b']
        assert call_counts['a'] == 3
        assert call_counts['b'] == 3
