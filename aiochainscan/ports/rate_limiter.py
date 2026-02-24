from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar('T')


@runtime_checkable
class RateLimiter(Protocol):
    """Rate limiter port supporting keyed acquisition."""

    async def acquire(self, key: str = 'default') -> None:
        """Acquire permission to perform an operation identified by key."""


@runtime_checkable
class RetryPolicy(Protocol):
    """Retry policy port to wrap async callables with retry semantics."""

    async def run(self, func: Callable[[], Awaitable[T]]) -> T:  # pragma: no cover - protocol
        """Execute func with retries and return its result."""
