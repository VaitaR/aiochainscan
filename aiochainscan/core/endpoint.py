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


# Common parsers for different response formats
def etherscan_parser(response: dict[str, Any]) -> Any:
    """Standard Etherscan API response parser."""
    if 'result' in response:
        return response['result']
    return response


def oklink_parser(response: dict[str, Any]) -> Any:
    """OKLink API response parser."""
    if 'data' in response and isinstance(response['data'], list) and response['data']:
        return response['data'][0]
    elif 'data' in response:
        return response['data']
    return response


def moralis_balance_parser(response: dict[str, Any]) -> int:
    """Moralis balance response parser."""
    # Moralis возвращает: {"balance": "123456789000000000000"} или в другом формате
    if 'balance' in response:
        return int(response['balance'])
    # Если структура отличается, попробуем извлечь из других полей
    elif isinstance(response, dict) and 'result' in response:
        return int(response['result'])
    # Если это строка
    elif isinstance(response, str):
        return int(response)
    # Fallback
    return 0


def moralis_transactions_parser(response: dict[str, Any]) -> Any:
    """Moralis transactions response parser."""
    # Moralis returns: {"page": 1, "page_size": 100, "result": [...]}
    return response.get('result', response)


def moralis_token_balances_parser(response: dict[str, Any]) -> Any:
    """Moralis token balances response parser."""
    # Moralis returns array directly or in result field
    if isinstance(response, list):
        return response
    return response.get('result', response)


def moralis_transaction_parser(response: dict[str, Any]) -> dict[str, Any]:
    """Moralis single transaction response parser."""
    # Moralis returns transaction object directly
    return response


# Pre-defined parsers for common use cases


def raw_parser(response: dict[str, Any]) -> Any:
    return response


PARSERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    'etherscan': etherscan_parser,
    'oklink': oklink_parser,
    'moralis_balance': moralis_balance_parser,
    'moralis_transactions': moralis_transactions_parser,
    'moralis_token_balances': moralis_token_balances_parser,
    'moralis_transaction': moralis_transaction_parser,
    'raw': raw_parser,
}
