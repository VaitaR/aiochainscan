from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

T = TypeVar('T')


class RateLimiter(Protocol):
    """Rate limiter port supporting keyed acquisition."""

    async def acquire(self, key: str) -> None:
        """Acquire permission to perform an operation identified by key."""


class RetryPolicy(Protocol):
    """Retry policy port to wrap async callables with retry semantics."""

    async def run(self, func: Callable[[], Awaitable[T]]) -> T:  # pragma: no cover - protocol
        """Execute func with retries and return its result."""
