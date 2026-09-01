"""
BlockScout API v1 scanner implementation.

BlockScout provides Etherscan-compatible API endpoints, making it easy
to integrate by inheriting from the shared Etherscan-like base with custom URL handling.

Supports multiple blockchain networks through different BlockScout instances:
- Ethereum Sepolia: eth-sepolia.blockscout.com
- Gnosis Chain: gnosis.blockscout.com
- Polygon: polygon.blockscout.com
- And many more...
"""

from typing import TYPE_CHECKING, Any

from ..core.endpoint import EndpointSpec
from ..core.method import Method
from ..core.url_builder import UrlBuilder
from ..exceptions import ChainscanClientError, ChainscanNetworkError
from . import register_scanner
from ._etherscan_like import EtherscanLikeScanner

if TYPE_CHECKING:
    from ..network import Network

#: Proxy-shaped methods the BlockScout compatibility REST answers with
#: ``"Unknown module"`` for ``module=proxy`` — served instead through the
#: instance's JSON-RPC endpoint (``POST {base_url}/api/eth-rpc``), the same
#: keyless transport the chain-info probe uses.
_JSON_RPC_ACTIONS: dict[Method, str] = {
    Method.TX_BY_HASH: 'eth_getTransactionByHash',
    Method.PROXY_ETH_CALL: 'eth_call',
    Method.PROXY_GET_BALANCE: 'eth_getBalance',
}


@register_scanner
class BlockScoutV1(EtherscanLikeScanner):
    """
    BlockScout API v1 implementation.

    Inherits all functionality from the shared Etherscan-like base since BlockScout provides
    Etherscan-compatible API endpoints. The main difference is in URL structure:
    - Etherscan: api.etherscan.io/api
    - BlockScout: {instance}.blockscout.com/api

    Key features:
    - Full Etherscan API compatibility
    - Multiple blockchain network support
    - No API key required (public endpoints)
    - Real-time blockchain data
    """

    name = 'blockscout'
    version = 'v1'

    # BlockScout supports many networks through different instances
    supported_networks = {
        'eth',  # Ethereum mainnet - ADDED!
        'sepolia',  # Ethereum Sepolia testnet
        'gnosis',  # Gnosis Chain
        'polygon',  # Polygon mainnet
        'optimism',  # Optimism mainnet
        'arbitrum',  # Arbitrum One
        'base',  # Base mainnet
        'scroll',  # Scroll mainnet
        'linea',  # Linea mainnet
        'bsc',  # BNB Smart Chain
    }

    # BlockScout typically doesn't require API keys
    auth_mode = 'query'
    auth_field = 'apikey'

    # Network to BlockScout instance mapping
    NETWORK_INSTANCES = {
        'eth': 'eth.blockscout.com',  # Ethereum mainnet - ADDED!
        'sepolia': 'eth-sepolia.blockscout.com',
        'gnosis': 'gnosis.blockscout.com',
        'polygon': 'polygon.blockscout.com',
        'optimism': 'optimism.blockscout.com',
        'arbitrum': 'arbitrum.blockscout.com',
        'base': 'base.blockscout.com',
        'scroll': 'scroll.blockscout.com',
        'linea': 'linea.blockscout.com',
        'bsc': 'bsc.blockscout.com',  # BNB Smart Chain
    }

    def __init__(
        self,
        api_key: str,
        network: str,
        url_builder: UrlBuilder,
        chain_id: int | None = None,
        network_client: 'Network | None' = None,
        base_url: str | None = None,
    ) -> None:
        """
        Initialize BlockScout scanner with network-specific instance.

        Args:
            api_key: API key (optional for BlockScout)
            network: Network name (must be in supported_networks)
            url_builder: UrlBuilder instance
            chain_id: Chain ID (optional, will be resolved from network)
            network_client: Optional Network instance for connection pooling
            base_url: Custom base URL for self-hosted BlockScout instances
                (overrides the per-network instance mapping; no API key needed)
        """
        super().__init__(api_key, network, url_builder, chain_id, network_client, base_url)

        # Custom self-hosted instance: no registry mapping to resolve.
        if base_url is not None:
            self.instance_domain: str | None = None
            return

        # Get BlockScout instance for this network
        self.instance_domain = self.NETWORK_INSTANCES.get(network)
        if not self.instance_domain:
            available = ', '.join(sorted(self.NETWORK_INSTANCES.keys()))
            raise ValueError(
                f"Network '{network}' not mapped to BlockScout instance. Available: {available}"
            )

    def _build_request(self, spec: EndpointSpec, **params: Any) -> dict[str, Any]:
        """
        Override to handle BlockScout-specific URL building.

        BlockScout uses different base URLs for each network instance,
        unlike Etherscan which uses subdomains.
        """
        # Get base request data from parent
        request_data: dict[str, Any] = super()._build_request(spec, **params)

        # BlockScout often works without API keys
        if not self.api_key:
            # Remove empty apikey parameter
            if spec.http_method == 'GET' and 'params' in request_data:
                request_data['params'].pop('apikey', None)
            elif spec.http_method == 'POST' and 'data' in request_data:
                request_data['data'].pop('apikey', None)

        return request_data

    async def call(self, method: Method, **params: Any) -> Any:
        """
        Override call to use proper BlockScout instance URL.

        BlockScout instances have different base URLs, so we need to
        construct the full URL manually. Proxy-shaped methods
        (``eth_call``/``eth_getBalance``/``eth_getTransactionByHash``) route
        through the instance's JSON-RPC endpoint because the compatibility
        REST does not implement ``module=proxy``.
        """
        rpc_action = _JSON_RPC_ACTIONS.get(method)
        if rpc_action is not None:
            return await self._call_json_rpc(rpc_action, params)

        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise ValueError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )

        spec = self.SPECS[method]
        request_data = self._build_request(spec, **params)

        # Build the complete BlockScout URL: custom self-hosted root or the
        # registry-mapped public instance.
        base_url = self.base_url or f'https://{self.instance_domain}'
        full_url = base_url + spec.path

        # Use Network layer for proper connection pooling, rate limiting, and retries
        if self._network_client is None:
            raise RuntimeError(
                f'{self.name} v{self.version}: network_client is required. '
                'Create scanner via ChainscanClient.from_config() which injects it automatically.'
            )

        try:
            if spec.http_method == 'GET':
                raw_response = await self._network_client.request(
                    method='GET',
                    url=full_url,
                    params=request_data.get('params'),
                    headers=request_data.get('headers', {}),
                )
            else:  # POST
                raw_response = await self._network_client.request(
                    method='POST',
                    url=full_url,
                    json_data=request_data.get('data'),
                    headers=request_data.get('headers', {}),
                )

            return spec.parse_response(raw_response)

        except ChainscanClientError:
            # Re-raise our own exceptions (transport, API and validation
            # errors such as the expected-chain guard) unchanged — never
            # mask them as opaque network failures.
            raise
        except Exception as e:
            # Unexpected errors
            raise ChainscanNetworkError(
                f'BlockScout unexpected error for {self.base_url or self.instance_domain}: {e}',
                retryable=False,
            ) from e

    async def _call_json_rpc(self, rpc_method: str, params: dict[str, Any]) -> Any:
        """Execute a proxy method via ``POST {base_url}/api/eth-rpc``.

        Works on every BlockScout deployment (public instances and
        self-hosted roots) without an API key. The Network layer unwraps the
        JSON-RPC envelope (``result`` payload returned directly) and raises
        :class:`ChainscanClientProxyError` for JSON-RPC errors such as
        reverted ``eth_call``\\s; a ``null`` result (e.g. transaction not
        found) comes back as ``None``.
        """
        if self._network_client is None:
            raise RuntimeError(
                f'{self.name} v{self.version}: network_client is required. '
                'Create scanner via ChainscanClient.from_config() which injects it automatically.'
            )

        if rpc_method == 'eth_call':
            rpc_params: list[Any] = [
                {'to': params.get('to', ''), 'data': params.get('data', '0x')},
                params.get('tag', 'latest'),
            ]
        elif rpc_method == 'eth_getBalance':
            rpc_params = [params.get('address', ''), params.get('tag', 'latest')]
        else:  # eth_getTransactionByHash
            rpc_params = [params.get('txhash', '')]

        base_url = self.base_url or f'https://{self.instance_domain}'
        return await self._network_client.request(
            method='POST',
            url=f'{base_url}/api/eth-rpc',
            json_data={'jsonrpc': '2.0', 'method': rpc_method, 'params': rpc_params, 'id': 1},
            headers={},
        )

    def __str__(self) -> str:
        """String representation including instance info."""
        root = self.base_url or self.instance_domain
        return f'BlockScout v{self.version} ({root})'

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f'BlockScoutV1(network={self.network!r}, '
            f'base_url={self.base_url!r}, '
            f'instance={self.instance_domain!r}, '
            f'methods={len(self.SPECS)})'
        )

    # All SPECS are inherited from the shared Etherscan-like implementation.
    # BlockScout supports the same endpoints:
    # - ACCOUNT_BALANCE, ACCOUNT_TRANSACTIONS, ACCOUNT_INTERNAL_TXS
    # - ACCOUNT_ERC20_TRANSFERS, TX_BY_HASH, TX_RECEIPT_STATUS
    # - BLOCK_BY_NUMBER, BLOCK_REWARD, CONTRACT_ABI, CONTRACT_SOURCE
    # - TOKEN_BALANCE, TOKEN_SUPPLY, GAS_ORACLE, EVENT_LOGS
    # - ETH_SUPPLY, ETH_PRICE, PROXY_ETH_CALL
