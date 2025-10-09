"""
Base scanner class for implementing different blockchain explorer APIs.
"""

from abc import ABC
from typing import Any, Literal

from ..chain_registry import resolve_chain_id
from ..core.endpoint import EndpointSpec
from ..core.method import Method
from ..network import Network
from ..url_builder import UrlBuilder


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

    def __init__(
        self, api_key: str, network: str, url_builder: UrlBuilder, chain_id: int | None = None
    ) -> None:
        """
        Initialize scanner instance.

        Args:
            api_key: API key for authentication
            network: Network name (must be in supported_networks)
            url_builder: UrlBuilder instance for URL construction
            chain_id: Chain ID (optional, will be resolved from network)

        Raises:
            ValueError: If network is not supported
        """
        if network not in self.supported_networks:
            available = ', '.join(sorted(self.supported_networks))
            raise ValueError(
                f"Network '{network}' not supported by {self.name} v{self.version}. "
                f'Available: {available}'
            )

        self.api_key = api_key
        self.network = network
        self.url_builder = url_builder
        self.chain_id = chain_id or resolve_chain_id(network)

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
            raise ValueError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )

        spec = self.SPECS[method]
        request_data = self._build_request(spec, **params)

        # Create temporary Network instance for this request
        # Note: In production, this would be injected or cached
        network = Network(self.url_builder)

        try:
            if spec.http_method == 'GET':
                raw_response = await network.get(
                    params=request_data.get('params'), headers=request_data.get('headers')
                )
            else:  # POST
                raw_response = await network.post(
                    data=request_data.get('data'), headers=request_data.get('headers')
                )

            return spec.parse_response(raw_response)

        finally:
            await network.close()

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
