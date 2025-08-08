from __future__ import annotations

from typing import Any, Protocol


class Cache(Protocol):
    """Cache port for storing arbitrary values by string key.

    Implementations may apply TTL-based expiration.
    """

    async def get(self, key: str) -> Any | None:
        """Return cached value for key if present and not expired, else None."""

    async def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        """Store value under key with optional TTL (in seconds)."""

    async def delete(self, key: str) -> None:
        """Remove key from cache if present."""
