from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class Telemetry(Protocol):
    """Telemetry/observability port for recording events and errors."""

    async def record_event(self, name: str, attributes: Mapping[str, Any] | None = None) -> None:
        """Record an event with optional attributes."""

    async def record_error(
        self, name: str, error: BaseException, attributes: Mapping[str, Any] | None = None
    ) -> None:
        """Record an error with context."""
