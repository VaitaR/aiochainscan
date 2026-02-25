"""
Blockscout REST API V2 scanner implementation.

Modern RESTful API with path parameters and rich JSON responses.
No API key required - public API.

Differences from V1 (Etherscan-compatible):
- Uses path parameters instead of query parameters
- Returns rich JSON objects directly (no status/message wrapper)
- Different response schemas with nested objects
- Pagination via next_page_params

Base URL example: https://eth.blockscout.com/api/v2/
"""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING, Any, ClassVar

from ..core.endpoint import EndpointSpec
from ..core.method import Method
from ..core.url_builder import UrlBuilder
from ..exceptions import ChainscanClientApiError, ChainscanNetworkError
from . import register_scanner
from .base import Scanner

if TYPE_CHECKING:
    from ..network import Network


# ============================================================================
# Response Parsers for Blockscout V2 API
# ============================================================================


def _parse_balance(response: dict[str, Any]) -> str:
    """
    Extract balance from V2 address response.

    Response format:
    {
        "hash": "0x...",
        "coin_balance": "32122885900610537215",
        "ens_domain_name": "vitalik.eth",
        ...
    }
    """
    result = response.get('coin_balance', '0')
    return str(result) if result else '0'


def _parse_token_portfolio(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract token list from V2 tokens response.

    Response format:
    {
        "items": [
            {
                "token": {"address_hash": "0x...", "name": "USDC", ...},
                "value": "5878047570"
            },
            ...
        ],
        "next_page_params": {...}
    }
    """
    items = response.get('items')
    return list(items) if items else []


def _parse_transactions(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract transactions from V2 transactions response.

    Response format:
    {
        "items": [...],
        "next_page_params": {...}
    }
    """
    items = response.get('items')
    return list(items) if items else []


def _parse_contract_abi(response: dict[str, Any]) -> list[dict[str, Any]] | None:
    """
    Extract ABI from V2 smart contract response.

    Response format:
    {
        "abi": [...],
        "name": "ContractName",
        "is_verified": true,
        ...
    }
    """
    abi = response.get('abi')
    return list(abi) if abi else None


def _parse_raw(response: dict[str, Any]) -> dict[str, Any]:
    """Return raw response without transformation."""
    return response


@register_scanner
class BlockScoutV2Scanner(Scanner):
    """
    Scanner for Blockscout REST API V2.

    Modern RESTful API with path parameters and rich JSON responses.
    No API key required - public API.

    Key features:
    - Path-based routing (e.g., /api/v2/addresses/{address})
    - Rich nested JSON responses
    - No API key required (public endpoints)
    - Automatic pagination support via next_page_params
    - ENS resolution included in address responses

    Example usage:
        scanner = BlockScoutV2Scanner(
            api_key="",  # Not required
            network="ethereum",
            url_builder=url_builder
        )
        balance = await scanner.call(Method.ACCOUNT_BALANCE, address="0x...")
        tokens = await scanner.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address="0x...")
    """

    name = 'blockscout'
    version = 'v2'

    # BlockScout V2 supports many networks through different instances
    supported_networks = {
        'ethereum',
        'eth',  # Alias for ethereum
        'sepolia',
        'gnosis',
        'polygon',
        'arbitrum',
        'optimism',
        'base',
        'scroll',
        'linea',
        'zksync',
    }

    # Network -> Base URL mapping for Blockscout instances
    BASE_URLS: ClassVar[dict[str, str]] = {
        'ethereum': 'https://eth.blockscout.com',
        'eth': 'https://eth.blockscout.com',
        'sepolia': 'https://eth-sepolia.blockscout.com',
        'gnosis': 'https://gnosis.blockscout.com',
        'polygon': 'https://polygon.blockscout.com',
        'arbitrum': 'https://arbitrum.blockscout.com',
        'optimism': 'https://optimism.blockscout.com',
        'base': 'https://base.blockscout.com',
        'scroll': 'https://scroll.blockscout.com',
        'linea': 'https://linea.blockscout.com',
        'zksync': 'https://zksync.blockscout.com',
    }

    # No API key required for Blockscout V2
    auth_mode = 'query'
    auth_field = 'apikey'

    # Endpoint specifications
    # Note: path contains {address} placeholder for path parameter substitution
    SPECS = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method='GET',
            path='/api/v2/addresses/{address}',
            query={},
            param_map={'address': 'address'},
            parser=_parse_balance,
            requires_api_key=False,
        ),
        Method.ACCOUNT_TOKEN_PORTFOLIO: EndpointSpec(
            http_method='GET',
            path='/api/v2/addresses/{address}/tokens',
            query={'type': 'ERC-20'},
            param_map={'address': 'address'},
            parser=_parse_token_portfolio,
            requires_api_key=False,
        ),
        Method.ACCOUNT_TRANSACTIONS: EndpointSpec(
            http_method='GET',
            path='/api/v2/addresses/{address}/transactions',
            query={},
            param_map={'address': 'address'},
            parser=_parse_transactions,
            requires_api_key=False,
        ),
        Method.CONTRACT_ABI: EndpointSpec(
            http_method='GET',
            path='/api/v2/smart-contracts/{address}',
            query={},
            param_map={'address': 'address'},
            parser=_parse_contract_abi,
            requires_api_key=False,
        ),
    }

    def __init__(
        self,
        api_key: str,
        network: str,
        url_builder: UrlBuilder,
        chain_id: int | None = None,
        network_client: Network | None = None,
    ) -> None:
        """
        Initialize BlockScout V2 scanner with network-specific instance.

        Args:
            api_key: API key (not required for Blockscout V2)
            network: Network name (must be in supported_networks)
            url_builder: UrlBuilder instance (used for compatibility)
            chain_id: Chain ID (optional, will be resolved from network)
            network_client: Optional Network instance for connection pooling
        """
        super().__init__(api_key, network, url_builder, chain_id, network_client)

        # Get base URL for this network
        self.base_url = self.BASE_URLS.get(network)
        if not self.base_url:
            available = ', '.join(sorted(self.BASE_URLS.keys()))
            raise ValueError(
                f"Network '{network}' not mapped to Blockscout V2 instance. Available: {available}"
            )

    def _build_url(self, spec: EndpointSpec, **params: Any) -> str:
        """
        Build full URL with path parameter substitution.

        Replaces {address} placeholders in the path with actual values.

        Args:
            spec: Endpoint specification
            **params: Parameters including address

        Returns:
            Full URL with substituted path parameters
        """
        path = spec.path

        # Substitute path parameters (e.g., {address})
        for param_name, value in params.items():
            placeholder = f'{{{param_name}}}'
            if placeholder in path:
                path = path.replace(placeholder, urllib.parse.quote(str(value), safe=''))

        return f'{self.base_url}{path}'

    def _build_query_params(self, spec: EndpointSpec, **params: Any) -> dict[str, Any]:
        """
        Build query parameters, excluding path parameters.

        Args:
            spec: Endpoint specification
            **params: All parameters

        Returns:
            Query parameters dictionary
        """
        query_params: dict[str, Any] = {}

        # Add static query parameters from spec
        query_params.update(spec.query)

        # Add any additional params that are not path parameters
        for param_name, value in params.items():
            placeholder = f'{{{param_name}}}'
            # Skip if this is a path parameter
            if placeholder not in spec.path and value is not None:
                # Map to scanner-specific name if defined
                scanner_param = spec.param_map.get(param_name, param_name)
                query_params[scanner_param] = value

        return query_params

    async def call(self, method: Method, **params: Any) -> Any:
        """
        Execute a logical method call against Blockscout V2 API.

        Handles:
        - Path parameter substitution
        - Query parameter building
        - Response parsing

        Args:
            method: Logical method to execute
            **params: Parameters for the method

        Returns:
            Parsed response from the API

        Raises:
            ValueError: If method is not supported
            Exception: On API errors
        """
        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise ValueError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )

        spec = self.SPECS[method]

        # Build URL with path parameters substituted
        url = self._build_url(spec, **params)

        # Build query parameters (excluding path params)
        query_params = self._build_query_params(spec, **params)

        # Headers that disable brotli compression (not always supported)
        headers = {
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
        }

        if self._network_client is None:
            raise RuntimeError(
                f'{self.name} v{self.version}: network_client is required. '
                'Create scanner via ChainscanClient.from_config() which injects it automatically.'
            )

        try:
            if spec.http_method == 'GET':
                raw_response = await self._network_client.request(
                    method='GET',
                    url=url,
                    params=query_params if query_params else None,
                    headers=headers,
                )
            else:  # POST
                raw_response = await self._network_client.request(
                    method='POST',
                    url=url,
                    json_data=query_params if query_params else None,
                    headers={**headers, 'Content-Type': 'application/json'},
                )

            return spec.parse_response(raw_response)

        except ChainscanClientApiError:
            # Re-raise our own exceptions
            raise
        except ChainscanNetworkError:
            # Re-raise our own exceptions
            raise
        except Exception as e:
            raise ChainscanNetworkError(
                f'Blockscout V2 unexpected error for {self.base_url}: {e}',
                retryable=False,
            ) from e

    # ========================================================================
    # Convenience methods for common operations
    # ========================================================================

    async def get_balance(self, address: str) -> str:
        """
        Get native coin balance for an address.

        Args:
            address: Ethereum address

        Returns:
            Balance in wei as string
        """
        result = await self.call(Method.ACCOUNT_BALANCE, address=address)
        return str(result)

    async def get_token_portfolio(
        self, address: str, token_type: str = 'ERC-20'
    ) -> list[dict[str, Any]]:
        """
        Get all tokens held by an address.

        Args:
            address: Ethereum address
            token_type: Token type filter (default: ERC-20)

        Returns:
            List of token holdings with token info and balances
        """
        result = await self.call(
            Method.ACCOUNT_TOKEN_PORTFOLIO,
            address=address,
            type=token_type,
        )
        return list(result) if result else []

    async def get_transactions(self, address: str) -> list[dict[str, Any]]:
        """
        Get transactions for an address.

        Args:
            address: Ethereum address

        Returns:
            List of transactions
        """
        result = await self.call(Method.ACCOUNT_TRANSACTIONS, address=address)
        return list(result) if result else []

    async def get_contract_abi(self, address: str) -> list[dict[str, Any]] | None:
        """
        Get ABI for a verified smart contract.

        Args:
            address: Contract address

        Returns:
            ABI as list of dicts, or None if not verified
        """
        result = await self.call(Method.CONTRACT_ABI, address=address)
        return list(result) if result else None

    async def get_address_info(self, address: str) -> dict[str, Any]:
        """
        Get full address information including ENS, balance, contract status.

        Args:
            address: Ethereum address

        Returns:
            Full address info dict
        """
        if Method.ACCOUNT_BALANCE not in self.SPECS:
            raise ValueError('ACCOUNT_BALANCE method not supported')

        spec = self.SPECS[Method.ACCOUNT_BALANCE]
        url = self._build_url(spec, address=address)

        if self._network_client is None:
            raise RuntimeError(
                f'{self.name} v{self.version}: network_client is required. '
                'Create scanner via ChainscanClient.from_config() which injects it automatically.'
            )

        headers = {
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
        }

        result = await self._network_client.request(method='GET', url=url, headers=headers)
        if isinstance(result, dict):
            return dict(result)
        return {}

    def __str__(self) -> str:
        """String representation including instance info."""
        return f'BlockScout v{self.version} ({self.base_url})'

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"BlockScoutV2Scanner(network='{self.network}', "
            f"base_url='{self.base_url}', "
            f'methods={len(self.SPECS)})'
        )
