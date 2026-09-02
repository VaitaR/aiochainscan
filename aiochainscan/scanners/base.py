"""
Base scanner class for implementing different blockchain explorer APIs.
"""

from abc import ABC
from typing import Any, Literal

from ..chain_registry import resolve_chain_id
from ..core.endpoint import EndpointSpec
from ..core.method import Method
from ..core.url_builder import UrlBuilder
from ..exceptions import MethodNotDeclaredError
from ..network import Network


class Scanner(ABC):
    """
    Abstract base class for blockchain scanner implementations.

    Each scanner represents a specific API provider (like Etherscan, BlockScout)
    with a specific version, supporting certain networks and providing
    specific endpoint implementations.
    """

    # These must be defined by subclasses
    name: str
    """Scanner name (e.g., 'etherscan', 'blockscout')"""

    version: str
    """Scanner API version (e.g., 'v1', 'v2')"""

    supported_networks: set[str]
    """Networks supported by this scanner (e.g., {'main', 'test'})"""

    auth_mode: Literal['query', 'header'] = 'query'
    """How to authenticate - 'query' for URL params, 'header' for HTTP headers"""

    auth_field: str = 'apikey'
    """Field name for authentication (e.g., 'apikey', 'OK-ACCESS-KEY')"""

    SPECS: dict[Method, EndpointSpec]
    """Mapping of logical methods to endpoint specifications"""

    result_window: int | None = None
    """Total results one page/offset query can reach before the provider stops.

    Etherscan-family REST APIs bound ``page * offset`` (see
    ``constants.API_MAX_OFFSET_ETHERSCAN``): once that many items have been
    walked, further pages return nothing more, which is *silent truncation*.
    A scanner that declares this window lets
    :func:`services.pagination.iter_pages` split the requested block range and
    keep the result complete (``guarantee_complete``).

    ``None`` means "no such window": the provider paginates by an opaque
    server-issued cursor that runs to exhaustion (BlockScout V2
    ``next_page_params``, NodeReal ``pageKey``), so a single query is already
    complete and nothing needs splitting.

    Declaring the window is opt-in. A third-party scanner that *has* a result
    window but leaves this ``None`` cannot be protected by
    ``guarantee_complete`` — the engine has no way to detect its cap.
    """

    chain_id: int | None
    """Numeric chain id; ``None`` for custom base URLs until probed/recorded."""

    def __init__(
        self,
        api_key: str,
        network: str,
        url_builder: UrlBuilder,
        chain_id: int | None = None,
        network_client: Network | None = None,
        base_url: str | None = None,
    ) -> None:
        """
        Initialize scanner instance.

        Args:
            api_key: API key for authentication
            network: Network name (must be in supported_networks; arbitrary
                when ``base_url`` is given — the registry is bypassed)
            url_builder: UrlBuilder instance for URL construction
            chain_id: Chain ID (optional, will be resolved from network)
            network_client: Network instance for connection pooling.
                Scanner uses it for requests (client owns lifecycle).
                Required at call time; raises RuntimeError if None when call() is invoked.
            base_url: Custom base URL (self-hosted instance / proxy). When
                set, the supported-networks check is skipped and the scanner
                must build all request URLs from this value instead of the
                registry mappings. ``chain_id`` stays ``None`` unless given
                explicitly (the chain is unknown until probed — see
                ``ChainscanClient.get_chain_info``).

        Raises:
            ValueError: If network is not supported
        """
        # A custom base URL bypasses the registry: the instance is not one of
        # the built-in per-network deployments, so the supported-networks set
        # does not apply. Scanners that cannot honor a base URL reject it.
        if base_url is None and network not in self.supported_networks:
            available = ', '.join(sorted(self.supported_networks))
            raise ValueError(
                f"Network '{network}' not supported by {self.name} v{self.version}. "
                f'Available: {available}'
            )

        self.api_key = api_key
        self.network = network
        self.url_builder = url_builder
        self.base_url = base_url
        if chain_id is not None:
            self.chain_id = chain_id
        elif base_url is not None:
            # Custom instance: the served chain is unknown until probed.
            self.chain_id = None
        else:
            self.chain_id = resolve_chain_id(network)
        self._network_client = network_client
        self._owns_network = False  # Scanner doesn't own injected client

    async def fetch_page(
        self,
        method: Method,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        Fetch a single page of results plus the cursor to the next page.

        This is the pagination seam of the Scanner port: page cursors flow
        *through* this interface, so callers never reach into scanner
        internals (``SPECS`` / ``_build_url`` / ``_build_query_params``).

        Cursor contract:
        - Returns ``(items, next_cursor)``.
        - ``next_cursor is None`` means "no more pages"; callers must stop.
        - ``next_cursor`` is opaque to callers. To fetch the next page, merge
          it into ``params`` (``params = {**params, **next_cursor}``) and call
          ``fetch_page`` again. Callers must not inspect or modify its contents.
        - Exceptions from the underlying request machinery propagate
          unchanged; this method adds no retry or wrapping of its own.

        The default implementation routes through :meth:`call` and always
        terminates after a single page (cursor is ``None``). Scanners with
        native pagination override this method to surface their cursor
        (e.g. BlockScout V2 ``next_page_params``, Etherscan page/offset).

        Args:
            method: Logical method to execute
            params: Parameters for the method (include the previous cursor
                via merge when fetching subsequent pages)

        Returns:
            Tuple of (items, next_cursor) where ``next_cursor is None``
            signals the end of pagination

        Raises:
            ValueError: If method is not supported
            Various network/API errors
        """
        result = await self.call(method, **params)
        return self._coerce_items(result), None

    @staticmethod
    def _coerce_items(result: Any) -> list[dict[str, Any]]:
        """Best-effort coercion of a parsed response into a list of items."""
        if isinstance(result, list):
            return list(result)
        if isinstance(result, dict):
            items = result.get('items')
            return list(items) if items else []
        return []

    async def call(self, method: Method, **params: Any) -> Any:
        """
        Execute a logical method call.

        Args:
            method: Logical method to execute
            **params: Parameters for the method

        Returns:
            Parsed response from the API

        Raises:
            ValueError: If method is not supported
            Various network/API errors
        """
        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise MethodNotDeclaredError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )

        spec = self.SPECS[method]
        request_data = self._build_request(spec, **params)

        if self._network_client is None:
            raise RuntimeError(
                f'{self.name} v{self.version}: network_client is required. '
                'Create scanner via ChainscanClient.from_config() which injects it automatically.'
            )
        network = self._network_client

        if spec.http_method == 'GET':
            raw_response = await network.get(
                params=request_data.get('params'), headers=request_data.get('headers')
            )
        else:  # POST
            raw_response = await network.post(
                data=request_data.get('data'), headers=request_data.get('headers')
            )

        return spec.parse_response(raw_response)

    def _build_request(self, spec: EndpointSpec, **params: Any) -> dict[str, Any]:
        """
        Build request data from endpoint spec and parameters.

        Args:
            spec: Endpoint specification
            **params: Method parameters

        Returns:
            Dictionary with request data (params/data and headers)
        """
        # Map parameters using the spec
        mapped_params = spec.map_params(**params)

        # Substitute chain_id placeholders
        if hasattr(self, 'chain_id'):
            for key, value in mapped_params.items():
                if isinstance(value, str) and value == '{chain_id}':
                    mapped_params[key] = self.chain_id

        # Set up authentication
        headers = {}
        if spec.requires_api_key and self.api_key:
            if self.auth_mode == 'query':
                mapped_params[self.auth_field] = self.api_key
            else:  # header
                headers[self.auth_field] = self.api_key

        # Build request data
        request_data = {'headers': headers}

        if spec.http_method == 'GET':
            request_data['params'] = mapped_params
        else:  # POST
            request_data['data'] = mapped_params

        return request_data

    async def close(self) -> None:
        """
        Close network client if owned by this scanner.

        Note: If a network_client was injected, this is a no-op since
        the caller owns the lifecycle. Only closes self-created clients.
        """
        if self._owns_network and self._network_client is not None:
            await self._network_client.close()
            self._network_client = None
            self._owns_network = False

    def supports_method(self, method: Method) -> bool:
        """
        Check if this scanner supports a logical method.

        Args:
            method: Method to check

        Returns:
            True if supported, False otherwise
        """
        return method in self.SPECS

    def get_supported_methods(self) -> list[Method]:
        """
        Get list of all supported methods.

        Returns:
            List of supported Method enum values
        """
        return list(self.SPECS.keys())

    def __str__(self) -> str:
        """String representation of the scanner."""
        networks = ', '.join(sorted(self.supported_networks))
        return f'{self.name} v{self.version} (networks: {networks})'

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"{self.__class__.__name__}(name='{self.name}', version='{self.version}', "
            f"networks={self.supported_networks}, auth_mode='{self.auth_mode}')"
        )
