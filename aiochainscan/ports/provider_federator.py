from __future__ import annotations

from typing import Protocol


class ProviderFederator(Protocol):
    """Decide whether to use REST or GraphQL for a given feature and provider."""

    def should_use_graphql(
        self,
        feature: str,
        *,
        api_kind: str,
        network: str,
        preferred: bool | None = None,
    ) -> bool:  # noqa: D401 - simple protocol
        """Return True if GraphQL should be used for `feature` with (api_kind, network)."""

    def report_success(self, feature: str, *, api_kind: str, network: str) -> None:
        """Record a successful GraphQL attempt (for health gating)."""

    def report_failure(self, feature: str, *, api_kind: str, network: str) -> None:
        """Record a failed GraphQL attempt (for health gating)."""
