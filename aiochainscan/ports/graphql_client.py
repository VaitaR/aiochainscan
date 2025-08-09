from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class GraphQLClient(Protocol):
    async def aclose(self) -> None:  # noqa: D401 - simple protocol
        """Close any underlying resources."""

    async def execute(
        self,
        url: str,
        query: str,
        variables: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:  # noqa: D401 - simple protocol
        """Execute a GraphQL request and return parsed JSON `data` field.

        Implementations must raise a provider-specific error when the GraphQL
        response contains an `errors` array or the transport layer fails.
        """
