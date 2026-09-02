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
from ..crypto import to_checksum_address
from ..exceptions import ChainscanClientError, ChainscanNetworkError, MethodNotDeclaredError
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


def _checksummed_holder_address(value: Any) -> Any:
    """Checksum a holder address, passing through values EIP-55 cannot digest."""
    if isinstance(value, str):
        try:
            return to_checksum_address(value)
        except ValueError:
            return value
    return value


def _normalize_token_holder_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Flatten one ``/tokens/{address}/holders`` entry to the unified shape.

    BlockScout nests the holder address inside an ``address`` object (with
    ``hash`` plus metadata); the unified item keeps only the checksummed
    ``address`` and the raw-unit ``value`` string (Wei-like: never Int64).
    """
    holder = entry.get('address')
    address = holder.get('hash') if isinstance(holder, dict) else holder
    return {
        'address': _checksummed_holder_address(address),
        'value': str(entry.get('value') or '0'),
    }


def _parse_token_holders(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract token holders from the V2 holders response.

    Response format:
    {
        "items": [
            {"address": {"hash": "0x...", ...}, "token_id": null, "value": "123"},
            ...
        ],
        "next_page_params": {...}
    }
    """
    items = response.get('items')
    return [_normalize_token_holder_entry(entry) for entry in items] if items else []


def _parse_token_holder_count(response: dict[str, Any]) -> int:
    """
    Extract the holder count from the V2 token info response.

    Response format (abridged):
    {
        "address_hash": "0x...",
        "holders_count": 30506,     # current field name
        "holders": 30506,           # legacy field name on older instances
        ...
    }
    """
    count = response.get('holders_count')
    if count is None:
        count = response.get('holders')
    try:
        return int(count) if count is not None else 0
    except (TypeError, ValueError):
        return 0


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

    # ``fetch_page`` follows the server's ``next_page_params`` to exhaustion,
    # so there is no page/offset result window to overflow (see base class).
    result_window = None

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
            param_map={
                'address': 'address',
                # BlockScout returns these fields in next_page_params.
                'block_number': 'block_number',
                'index': 'index',
                'items_count': 'items_count',
            },
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
        Method.BLOCK_BY_NUMBER: EndpointSpec(
            http_method='GET',
            path='/api/v2/blocks/{block_number}',
            query={},
            param_map={'block_number': 'block_number'},
            parser=_parse_raw,
            requires_api_key=False,
        ),
        Method.TOKEN_HOLDERS: EndpointSpec(
            http_method='GET',
            path='/api/v2/tokens/{contract_address}/holders',
            query={},
            param_map={
                'contract_address': 'contract_address',
                # BlockScout returns these fields in next_page_params.
                'value': 'value',
                'address_hash': 'address_hash',
                'items_count': 'items_count',
            },
            parser=_parse_token_holders,
            requires_api_key=False,
        ),
        Method.TOKEN_HOLDER_COUNT: EndpointSpec(
            http_method='GET',
            path='/api/v2/tokens/{contract_address}',
            query={},
            param_map={'contract_address': 'contract_address'},
            parser=_parse_token_holder_count,
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
        base_url: str | None = None,
    ) -> None:
        """
        Initialize BlockScout V2 scanner with network-specific instance.

        Args:
            api_key: API key (not required for Blockscout V2)
            network: Network name (must be in supported_networks)
            url_builder: UrlBuilder instance (used for compatibility)
            chain_id: Chain ID (optional, will be resolved from network)
            network_client: Optional Network instance for connection pooling
            base_url: Custom base URL for self-hosted BlockScout instances
                (overrides the per-network instance mapping; no API key needed)
        """
        super().__init__(api_key, network, url_builder, chain_id, network_client, base_url)

        # Resolve the instance root: explicit self-hosted URL or the
        # per-network public instance mapping.
        if base_url is None:
            self.base_url = self.BASE_URLS.get(network)
            if not self.base_url:
                available = ', '.join(sorted(self.BASE_URLS.keys()))
                raise ValueError(
                    f"Network '{network}' not mapped to Blockscout V2 instance. "
                    f'Available: {available}'
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
                if param_name not in spec.param_map:
                    continue
                scanner_param = spec.param_map[param_name]
                query_params[scanner_param] = value

        return query_params

    async def _request_raw(self, spec: EndpointSpec, **params: Any) -> Any:
        """
        Perform the HTTP request for an endpoint spec and return the raw response.

        Shared by :meth:`call` (which applies the spec parser) and
        :meth:`fetch_page` (which needs the unparsed envelope to extract
        ``next_page_params``).

        Args:
            spec: Endpoint specification
            **params: Parameters for the method

        Returns:
            Raw (already JSON-parsed) response body

        Raises:
            RuntimeError: If no network client is injected
            ChainscanNetworkError: On network failures
        """
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

        if spec.http_method == 'GET':
            return await self._network_client.request(
                method='GET',
                url=url,
                params=query_params if query_params else None,
                headers=headers,
            )
        else:  # POST
            return await self._network_client.request(
                method='POST',
                url=url,
                json_data=query_params if query_params else None,
                headers={**headers, 'Content-Type': 'application/json'},
            )

    async def fetch_page(
        self,
        method: Method,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        Fetch one page, preserving BlockScout V2's ``next_page_params`` cursor.

        Follows the base cursor contract: merge a non-``None`` cursor into
        ``params`` for the next call; ``None`` terminates pagination.

        Args:
            method: Logical method to execute
            params: Parameters for the method (merged cursor included for
                subsequent pages)

        Returns:
            Tuple of (items, next_cursor)
        """
        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise MethodNotDeclaredError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )

        spec = self.SPECS[method]
        raw_response = await self._request_raw(spec, **params)

        if isinstance(raw_response, dict):
            items = raw_response.get('items', [])
            # TOKEN_HOLDERS items are flattened to the unified holder shape so
            # the pagination path (streaming/get_all) matches ``call()`` output.
            if method is Method.TOKEN_HOLDERS:
                items = [_normalize_token_holder_entry(entry) for entry in items]
            next_cursor = raw_response.get('next_page_params')
        elif isinstance(raw_response, list):
            # Fallback for list responses
            items = raw_response
            next_cursor = None
        else:
            items, next_cursor = [], None

        cursor = dict(next_cursor) if next_cursor else {}
        # A remote cursor is opaque pagination state, but it must never be
        # allowed to replace resource identity embedded in this endpoint's
        # path (for example, switching the requested address on page two).
        for public_name, scanner_name in spec.param_map.items():
            if f'{{{public_name}}}' in spec.path:
                cursor.pop(public_name, None)
                cursor.pop(scanner_name, None)

        return list(items) if items else [], cursor or None

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
            raise MethodNotDeclaredError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )

        spec = self.SPECS[method]

        if self._network_client is None:
            raise RuntimeError(
                f'{self.name} v{self.version}: network_client is required. '
                'Create scanner via ChainscanClient.from_config() which injects it automatically.'
            )

        try:
            raw_response = await self._request_raw(spec, **params)

            return spec.parse_response(raw_response)

        except ChainscanClientError:
            # Re-raise our own exceptions (transport, API and validation
            # errors such as the expected-chain guard) unchanged — never
            # mask them as opaque network failures.
            raise
        except Exception as e:
            raise ChainscanNetworkError(
                f'Blockscout V2 unexpected error for {self.base_url}: {e}',
                retryable=False,
            ) from e

    # ========================================================================
    # Scanner-port methods (explicit dependencies, see docstrings)
    # ========================================================================

    async def get_address_info(self, address: str) -> dict[str, Any]:
        """
        Get full address information including ENS, balance, contract status.

        This is a scanner-port method serving ENS reverse resolution: it is
        injected into :class:`~aiochainscan.services.ens_resolver.ENSResolver`
        (via its ``AddressInfoProvider`` port) so reverse lookups can read
        ``ens_domain_name`` directly from the BlockScout V2 address endpoint.
        It is not part of the generic ``call()``/``fetch_page()`` contract.

        Args:
            address: Ethereum address

        Returns:
            Full address info dict
        """
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
