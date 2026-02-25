from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
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
