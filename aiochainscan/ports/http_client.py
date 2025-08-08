from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class HttpClient(Protocol):
    async def aclose(self) -> None:  # noqa: D401 - simple protocol
        """Close any underlying resources."""

    async def get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:  # noqa: D401 - simple protocol
        """Perform an HTTP GET request and return parsed JSON or text."""

    async def post(
        self,
        url: str,
        *,
        data: Any | None = None,
        json: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:  # noqa: D401 - simple protocol
        """Perform an HTTP POST request and return parsed JSON or text."""
