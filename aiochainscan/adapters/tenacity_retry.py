"""Tenacity-based retry adapter for transport-agnostic retry logic.

This adapter solves the problem of retrying on business-logic errors
that are hidden inside HTTP 200 responses (e.g., Etherscan's rate limit
messages in JSON body).

Unlike aiohttp-retry which only handles HTTP status codes, tenacity
allows retrying on any exception type, including ChainscanRateLimitError.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from aiochainscan.exceptions import ChainscanRateLimitError
from aiochainscan.ports.rate_limiter import RetryPolicy

T = TypeVar('T')

logger = logging.getLogger(__name__)


# Default exceptions to retry on - transport errors and rate limits
DEFAULT_RETRY_EXCEPTIONS: tuple[type[Exception], ...] = (ChainscanRateLimitError,)


def _default_before_sleep_callback(retry_state: RetryCallState) -> None:
    """Default callback invoked before sleeping between retries.

    Logs retry information at WARNING level.
    """
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    wait_time = retry_state.next_action.sleep if retry_state.next_action else 0

    logger.warning(
        'Retry attempt %d/%s failed with %s: %s. Waiting %.2f seconds before next attempt.',
        retry_state.attempt_number,
        retry_state.retry_object.stop.max_attempt_number  # type: ignore[union-attr]
        if hasattr(retry_state.retry_object.stop, 'max_attempt_number')
        else '?',
        type(exception).__name__ if exception else 'unknown',
        str(exception) if exception else 'unknown error',
        wait_time,
    )


class TenacityRetryAdapter(RetryPolicy):
    """Transport-agnostic retry mechanism using tenacity.

    This adapter implements the RetryPolicy port and can be used to wrap
    any async function with retry logic. It supports:

    - Retrying on specific exception types (including ChainscanRateLimitError)
    - Exponential backoff with jitter to prevent thundering herd
    - Configurable max attempts, min/max wait times
    - Custom callbacks for logging/telemetry on retry

    Example usage:

        retry_adapter = TenacityRetryAdapter(
            max_attempts=5,
            min_wait=1.0,
            max_wait=30.0,
            retry_exceptions=(ChainscanRateLimitError, aiohttp.ClientError),
        )

        # Method 1: Using run() method (implements RetryPolicy interface)
        result = await retry_adapter.run(lambda: client.fetch_data())

        # Method 2: Using wrap() decorator
        @retry_adapter.wrap
        async def fetch_with_retry():
            return await client.fetch_data()

        result = await fetch_with_retry()

        # Method 3: Using async context manager
        async with retry_adapter.retrying() as retrying:
            async for attempt in retrying:
                with attempt:
                    result = await client.fetch_data()
    """

    def __init__(
        self,
        max_attempts: int = 5,
        min_wait: float = 1.0,
        max_wait: float = 30.0,
        jitter: float = 1.0,
        retry_exceptions: tuple[type[Exception], ...] = DEFAULT_RETRY_EXCEPTIONS,
        before_sleep_callback: Callable[[RetryCallState], None] | None = None,
        reraise: bool = True,
    ) -> None:
        """Initialize the retry adapter.

        Args:
            max_attempts: Maximum number of retry attempts (default: 5)
            min_wait: Minimum wait time in seconds between retries (default: 1.0)
            max_wait: Maximum wait time in seconds between retries (default: 30.0)
            jitter: Maximum jitter to add to wait time in seconds (default: 1.0)
            retry_exceptions: Tuple of exception types to retry on
                (default: (ChainscanRateLimitError,))
            before_sleep_callback: Optional callback invoked before each retry sleep.
                Receives RetryCallState with attempt info. Useful for logging/telemetry.
            reraise: Whether to reraise the last exception after all attempts fail
                (default: True)
        """
        self.max_attempts = max(1, int(max_attempts))
        self.min_wait = max(0.0, float(min_wait))
        self.max_wait = max(self.min_wait, float(max_wait))
        self.jitter = max(0.0, float(jitter))
        self.retry_exceptions = retry_exceptions
        self.before_sleep_callback = before_sleep_callback or _default_before_sleep_callback
        self.reraise = reraise

    def _create_retrying(self) -> AsyncRetrying:
        """Create a new AsyncRetrying instance with configured settings."""
        return AsyncRetrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential_jitter(
                initial=self.min_wait,
                max=self.max_wait,
                jitter=self.jitter,
            ),
            retry=retry_if_exception_type(self.retry_exceptions),
            before_sleep=self.before_sleep_callback,
            reraise=self.reraise,
        )

    async def run(self, func: Callable[[], Awaitable[T]]) -> T:
        """Execute func with retries and return its result.

        This method implements the RetryPolicy protocol interface.

        Args:
            func: A zero-argument async callable to execute with retries.

        Returns:
            The result of the successful function call.

        Raises:
            The last exception if all retry attempts fail and reraise=True.
        """
        retrying = self._create_retrying()
        async for attempt in retrying:
            with attempt:
                return await func()
        # This should never be reached due to reraise=True, but satisfies type checker
        raise RuntimeError('Retry exhausted without result')  # pragma: no cover

    def wrap(self, func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        """Wrap an async function with retry logic.

        This method returns a new function that will automatically retry
        on configured exceptions.

        Args:
            func: An async function to wrap with retry logic.

        Returns:
            A wrapped async function with retry behavior.

        Example:
            @retry_adapter.wrap
            async def fetch_data():
                return await client.get('/api/data')
        """

        @wraps(func)
        async def wrapped(*args: Any, **kwargs: Any) -> T:
            retrying = self._create_retrying()
            async for attempt in retrying:
                with attempt:
                    return await func(*args, **kwargs)
            # This should never be reached due to reraise=True
            raise RuntimeError('Retry exhausted without result')  # pragma: no cover

        return wrapped

    def retrying(self) -> AsyncRetrying:
        """Return an AsyncRetrying instance for manual retry control.

        This allows for fine-grained control over retry logic using
        tenacity's async iteration pattern.

        Returns:
            An AsyncRetrying instance configured with this adapter's settings.

        Example:
            async for attempt in retry_adapter.retrying():
                with attempt:
                    result = await client.fetch_data()
        """
        return self._create_retrying()

    def with_exceptions(self, *additional_exceptions: type[Exception]) -> TenacityRetryAdapter:
        """Create a new adapter with additional exception types to retry on.

        This is useful for adding transport-specific exceptions without
        modifying the original adapter.

        Args:
            *additional_exceptions: Additional exception types to retry on.

        Returns:
            A new TenacityRetryAdapter with the combined exception types.

        Example:
            import aiohttp

            # Add aiohttp-specific exceptions
            http_retry = retry_adapter.with_exceptions(
                aiohttp.ClientError,
                aiohttp.ServerTimeoutError,
            )
        """
        combined_exceptions = self.retry_exceptions + additional_exceptions
        return TenacityRetryAdapter(
            max_attempts=self.max_attempts,
            min_wait=self.min_wait,
            max_wait=self.max_wait,
            jitter=self.jitter,
            retry_exceptions=combined_exceptions,
            before_sleep_callback=self.before_sleep_callback,
            reraise=self.reraise,
        )

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}('
            f'max_attempts={self.max_attempts}, '
            f'min_wait={self.min_wait}, '
            f'max_wait={self.max_wait}, '
            f'retry_exceptions={self.retry_exceptions!r})'
        )
