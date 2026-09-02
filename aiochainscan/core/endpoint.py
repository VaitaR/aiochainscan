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

    path: str = ''
    """Relative path for the endpoint (e.g., '/api', '/api/v5/explorer').

    Optional: dialect scanners whose URLs are built outside the spec (their
    ``_perform_request`` override owns the transport, e.g. JSON-RPC endpoints
    with the API key in the URL path) leave it empty rather than declare a
    path nothing reads.
    """

    query: dict[str, Any] = field(default_factory=dict)
    """Static parameters that are always included.

    ``query``-style specs: static query parameters. ``rpc-positional`` specs:
    static trailing positional constants, appended verbatim after the mapped
    values in declaration order (the key documents the value's meaning, e.g.
    ``{'include_full_tx_objects': False}``).
    """

    param_map: dict[str, str] = field(default_factory=dict)
    """Maps public parameter names to scanner-specific parameter names.

    For ``rpc-positional`` style the declaration order IS the positional wire
    order; for ``rpc-object`` style the values are the keys of the object
    argument. Alternate tolerated input spellings (aliases) are declared here
    too — first declared wins — so the executed builders, the block-range
    capability and the consistency sweep all read the same map. An empty
    wire name declares an accepted-but-inert input: something a dialect
    must tolerate (mixin parity) but that carries no wire parameter.
    """

    param_style: Literal['query', 'rpc-positional', 'rpc-object'] = 'query'
    """How the mapped parameters reach the wire.

    ``'query'`` (default): :meth:`map_params` builds the query string / JSON
    body — the classic explorer-REST contract.

    ``'rpc-positional'``: the wire call takes a positional parameter list
    (JSON-RPC); the declaring scanner's builder reads ``param_map`` for the
    public→wire sources in declared order and encodes the values.

    ``'rpc-object'``: the wire call takes a single object argument (a JSON-RPC
    filter object); the declaring scanner's object builder assembles it from
    the ``param_map`` sources.
    """

    parser: Callable[[Any], Any] | None = None
    """Optional function to transform raw API response to standardized format."""

    requires_api_key: bool = True
    """Whether this endpoint requires API key authentication."""

    unknown_params: Literal['pass', 'drop'] = 'pass'
    """Policy for public parameter names the ``param_map`` does not declare.

    ``'pass'`` (default) forwards them under their public name — the classic
    Etherscan contract, where any extra query parameter rides along.
    ``'drop'`` silently discards them — for strict path-parameter APIs
    (BlockScout V2) whose endpoints reject unknown query keys and where a
    server cursor must never smuggle undeclared state onto the wire.

    Path parameters are excluded from the mapped query regardless of this
    policy: a public name appearing as ``{name}`` in :attr:`path` is consumed
    by URL substitution, never sent as a query/body parameter.
    """

    def map_params(self, **params: Any) -> dict[str, Any]:
        """
        Map public parameters to scanner-specific parameter names.

        The ONE param-mapping implementation for ``query``-style specs: static
        :attr:`query` first (public params win on key collision), then the
        provided params — ``None`` values skipped, path placeholders
        excluded, names translated through :attr:`param_map`, unknown names
        handled per :attr:`unknown_params`. JSON-RPC styles
        (``rpc-positional`` / ``rpc-object``) are mapped by the declaring
        scanner's builders from the same :attr:`param_map` declaration.

        Args:
            **params: Public parameter names and values

        Returns:
            Dictionary with scanner-specific parameter names
        """
        mapped: dict[str, Any] = dict(self.query)

        for public_name, value in params.items():
            if value is None:
                continue
            # Path parameter: consumed by URL substitution, never the query.
            if f'{{{public_name}}}' in self.path:
                continue
            scanner_param = self.param_map.get(public_name)
            if scanner_param is None:
                if self.unknown_params == 'drop':
                    continue
                scanner_param = public_name
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
