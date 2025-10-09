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

from typing import Any

from ..core.endpoint import EndpointSpec
from ..core.method import Method
from ..url_builder import UrlBuilder
from . import register_scanner
from ._etherscan_like import EtherscanLikeScanner


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
    }

    def __init__(
        self, api_key: str, network: str, url_builder: UrlBuilder, chain_id: int | None = None
    ) -> None:
        """
        Initialize BlockScout scanner with network-specific instance.

        Args:
            api_key: API key (optional for BlockScout)
            network: Network name (must be in supported_networks)
            url_builder: UrlBuilder instance
            chain_id: Chain ID (optional, will be resolved from network)
        """
        super().__init__(api_key, network, url_builder, chain_id)

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
        construct the full URL manually.
        """
        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise ValueError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )

        spec = self.SPECS[method]
        request_data = self._build_request(spec, **params)

        # Build the complete BlockScout URL
        base_url = f'https://{self.instance_domain}'
        full_url = base_url + spec.path

        # Use aiohttp directly for BlockScout requests
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                if spec.http_method == 'GET':
                    async with session.get(
                        full_url,
                        params=request_data.get('params'),
                        headers=request_data.get('headers', {}),
                    ) as response:
                        raw_response = await response.json()
                else:  # POST
                    async with session.post(
                        full_url,
                        json=request_data.get('data'),
                        headers=request_data.get('headers', {}),
                    ) as response:
                        raw_response = await response.json()

            return spec.parse_response(raw_response)

        except Exception as e:
            # Enhanced error reporting for BlockScout
            raise Exception(f'BlockScout API error for {self.instance_domain}: {e}') from e

    def __str__(self) -> str:
        """String representation including instance info."""
        return f'BlockScout v{self.version} ({self.instance_domain})'

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"BlockScoutV1(network='{self.network}', "
            f"instance='{self.instance_domain}', "
            f'methods={len(self.SPECS)})'
        )

    # All SPECS are inherited from the shared Etherscan-like implementation.
    # BlockScout supports the same endpoints:
    # - ACCOUNT_BALANCE, ACCOUNT_TRANSACTIONS, ACCOUNT_INTERNAL_TXS
    # - ACCOUNT_ERC20_TRANSFERS, TX_BY_HASH, TX_RECEIPT_STATUS
    # - BLOCK_BY_NUMBER, BLOCK_REWARD, CONTRACT_ABI, CONTRACT_SOURCE
    # - TOKEN_BALANCE, TOKEN_SUPPLY, GAS_ORACLE, EVENT_LOGS
    # - ETH_SUPPLY, ETH_PRICE, PROXY_ETH_CALL
