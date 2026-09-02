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

from ..chain_registry import BLOCKSCOUT_INSTANCE_HOSTS
from ..core.endpoint import EndpointSpec
from ..core.url_builder import UrlBuilder
from ..domain.method import Method
from . import register_scanner
from ._etherscan_like import EtherscanLikeScanner
from .base import hex_block_tag

if TYPE_CHECKING:
    from ..network import Network

#: Proxy-shaped methods the BlockScout compatibility REST answers with
#: ``"Unknown module"`` for ``module=proxy`` — served instead through the
#: instance's JSON-RPC endpoint (``POST {base_url}/api/eth-rpc``), the same
#: keyless transport the chain-info probe uses. ``BLOCK_BY_NUMBER`` is in
#: the map because live BlockScout answers ``{"message": "Unknown module"}``
#: for ``module=proxy&action=eth_getBlockByNumber`` too; the JSON-RPC result
#: (raw hex-quantity block dict, full transactions) matches the shape the
#: Etherscan proxy module returns, so it is passed through like TX_BY_HASH.
_JSON_RPC_ACTIONS: dict[Method, str] = {
    Method.TX_BY_HASH: 'eth_getTransactionByHash',
    Method.BLOCK_BY_NUMBER: 'eth_getBlockByNumber',
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

    # Network to BlockScout instance mapping — the shared per-alias host
    # table from the chain registry (one table for BlockScout v1 and v2).
    NETWORK_INSTANCES = dict(BLOCKSCOUT_INSTANCE_HOSTS)

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

        # Get BlockScout instance for this network (shared unknown-network
        # ValueError shape lives on the base).
        self.instance_domain = self._require_mapped_network(
            self.NETWORK_INSTANCES, 'BlockScout instance'
        )

    # ------------------------------------------------------------------
    # Provider dialect (the base owns the ladder, dispatch and params)
    # ------------------------------------------------------------------

    def _instance_root(self) -> str:
        """Instance root for requests: custom self-hosted URL or the
        registry-mapped public instance."""
        return self.base_url or f'https://{self.instance_domain}'

    def _request_url(self, spec: EndpointSpec, params: dict[str, Any]) -> str:
        """Full per-instance URL: BlockScout instances live on their own
        hosts, unlike Etherscan's shared subdomain layout."""
        return f'{self._instance_root()}{spec.path}'

    def _error_context(self, method: Method) -> str:
        return f'BlockScout unexpected error for {self.base_url or self.instance_domain}'

    async def _perform_request(
        self,
        spec: EndpointSpec,
        method: Method,
        params: dict[str, Any],
    ) -> Any:
        """Route proxy-shaped methods through the instance's JSON-RPC endpoint.

        BlockScout instances have different base URLs (handled by the base
        dispatch via :meth:`_request_url`); the JSON-RPC detour below is the
        only v1-specific transport, because the compatibility REST does not
        implement ``module=proxy`` (``eth_call``/``eth_getBalance``/
        ``eth_getTransactionByHash``/``eth_getBlockByNumber``). The JSON-RPC
        result arrives already unwrapped to its final shape (the Network
        layer extracted the envelope), so the spec parser is skipped — same
        pass-through the Etherscan proxy module's results get.
        """
        rpc_action = _JSON_RPC_ACTIONS.get(method)
        if rpc_action is not None:
            return await self._call_json_rpc(rpc_action, params)
        return await super()._perform_request(spec, method, params)

    async def _call_json_rpc(self, rpc_method: str, params: dict[str, Any]) -> Any:
        """Execute a proxy method via ``POST {base_url}/api/eth-rpc``.

        Works on every BlockScout deployment (public instances and
        self-hosted roots) without an API key. The Network layer unwraps the
        JSON-RPC envelope (``result`` payload returned directly) and raises
        :class:`ChainscanClientProxyError` for JSON-RPC errors such as
        reverted ``eth_call``\\s; a ``null`` result (e.g. transaction not
        found) comes back as ``None``.
        """
        network = self._require_network_client()

        if rpc_method == 'eth_call':
            rpc_params: list[Any] = [
                {'to': params.get('to', ''), 'data': params.get('data', '0x')},
                params.get('tag', 'latest'),
            ]
        elif rpc_method == 'eth_getBalance':
            rpc_params = [params.get('address', ''), params.get('tag', 'latest')]
        elif rpc_method == 'eth_getBlockByNumber':
            # ``block_number`` arrives as int (convenience paths) or as a
            # JSON-RPC tag ('latest', '0x...'); numeric forms become hex
            # tags. Full transaction objects mirror the Etherscan-like
            # spec's static ``boolean=true``.
            rpc_params = [hex_block_tag(params.get('block_number', 'latest')), True]
        else:  # eth_getTransactionByHash
            rpc_params = [params.get('txhash', '')]

        return await network.request(
            method='POST',
            url=f'{self._instance_root()}/api/eth-rpc',
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
