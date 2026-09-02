"""
Endpoint specification for different scanner implementations.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True, frozen=True)
class EndpointSpec:
    """
    Specification for how a logical method maps to a specific scanner endpoint.

    This allows different scanners to implement the same logical operation
    with different HTTP methods, paths, parameters, and response formats.
    """

    http_method: Literal['GET', 'POST']
    """HTTP method to use for the request."""

    path: str
    """Relative path for the endpoint (e.g., '/api', '/api/v5/explorer')."""

    query: dict[str, Any] = field(default_factory=dict)
    """Static query parameters that are always included."""

    param_map: dict[str, str] = field(default_factory=dict)
    """Maps public parameter names to scanner-specific parameter names."""

    parser: Callable[[Any], Any] | None = None
    """Optional function to transform raw API response to standardized format."""

    requires_api_key: bool = True
    """Whether this endpoint requires API key authentication."""

    def map_params(self, **params: Any) -> dict[str, Any]:
        """
        Map public parameters to scanner-specific parameter names.

        Args:
            **params: Public parameter names and values

        Returns:
            Dictionary with scanner-specific parameter names
        """
        mapped: dict[str, Any] = {}

        # Add static query parameters
        mapped.update(self.query)

        # Map provided parameters
        for public_name, value in params.items():
            if value is not None:
                scanner_param = self.param_map.get(public_name, public_name)
                mapped[scanner_param] = value

        return mapped

    def parse_response(self, raw_response: Any) -> Any:
        """
        Parse raw API response using the configured parser.

        Args:
            raw_response: Raw response from the API

        Returns:
            Parsed response or raw response if no parser configured
        """
        if self.parser:
            return self.parser(raw_response)
        return raw_response


def etherscan_parser(response: dict[str, Any]) -> Any:
    """Standard Etherscan API response parser."""
    if 'result' in response:
        return response['result']
    return response


def coerce_response_items(response: Any) -> list[dict[str, Any]]:
    """Coerce a parsed API response into a list of item dicts.

    Canonical implementation of the response→items coercion shared by
    ``Scanner._coerce_items`` (scanners layer) and
    ``services.pagination.normalize_items`` (services layer) — one coercion
    contract, maintained once. Core is imported by both layers, so it is the
    only legal shared home (services must not import scanners).

    Accepts the shapes explorers actually return: a plain list, an envelope
    dict with an ``'items'`` key, or anything else (treated as no data).
    """
    if isinstance(response, list):
        return list(response)
    if isinstance(response, dict):
        items = response.get('items')
        return list(items) if items else []
    return []
