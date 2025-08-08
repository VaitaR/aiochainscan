from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class EndpointSession(Protocol):
    @property
    def api_url(self) -> str:  # noqa: D401 - simple protocol
        """Return API base URL for requests (e.g., .../api)."""

    @property
    def base_url(self) -> str:  # noqa: D401 - simple protocol
        """Return base explorer URL (without /api)."""

    def filter_and_sign(
        self,
        params: Mapping[str, Any] | None,
        headers: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:  # noqa: D401 - simple protocol
        """Filter params and sign with API key if required; return (params, headers)."""


class EndpointBuilder(Protocol):
    def open(self, *, api_key: str, api_kind: str, network: str) -> EndpointSession:  # noqa: D401
        """Create an endpoint session bound to api_key/api_kind/network."""
