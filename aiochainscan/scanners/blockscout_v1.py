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
from ..constants import API_MAX_OFFSET_ETHERSCAN, API_MAX_OFFSET_LOGS
from ..core.endpoint import EndpointSpec
from ..core.url_builder import UrlBuilder
from ..domain.method import Method
from . import register_scanner
from ._etherscan_like import EtherscanLikeScanner
from .base import checksummed_holder_address, hex_block_tag

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


def _parse_token_holders(response: Any) -> list[dict[str, Any]]:
    """Normalize BlockScout V1 ``token/getTokenHolders`` items.

    Unlike Etherscan's ``TokenHolderAddress``/``TokenHolderQuantity`` field
    names, BlockScout's own action already answers the unified field names
    (verified live 2026-09-02 against ``eth.blockscout.com``):
    ``{"status":"1","message":"OK","result":[{"address":"0x...","value":"..."}]}``.
    The parser runs at the post-unwrap seam (``Network._handle_response`` has
    already extracted ``result``), so only checksumming and str-coercion are
    needed to match the shape ``etherscan_v2``/``blockscout_v2`` produce.
    """
    if not isinstance(response, list):
        return []
    items: list[dict[str, Any]] = []
    for raw in response:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                'address': checksummed_holder_address(raw.get('address')),
                'value': str(raw.get('value') or '0'),
            }
        )
    return items


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

    # Unlike Etherscan, BlockScout V1 does serve a 10_000-item page — but it
    # clamps anything above that silently (``offset=10001`` → 10_000 items,
    # ``status=1``), so the page size still has to be declared. Verified live
    # 2026-09-02.
    max_page_size = API_MAX_OFFSET_ETHERSCAN

    # ``getLogs`` here is NOT a page/offset endpoint: it ignores both params and
    # answers at most API_MAX_OFFSET_LOGS logs with ``status=1`` "OK", so its
    # real window is 1000, not the account endpoints' 10_000. Verified live
    # 2026-09-02 against eth.blockscout.com (a 60-block USDT Transfer range
    # holding 1085 logs came back as 1000, identical on every page). Without
    # this the guarantee layer walked to 10_000 by re-fetching the same first
    # page ten times before splitting.
    #
    # ``token/getTokenHolders`` (BlockScout's own action, not Etherscan's
    # ``tokenholderlist``) has NO observed result window: ``page=11&offset=1000``
    # (11k deep) and ``page=5&offset=10000`` (50k deep) both answered
    # ``status=1`` with full pages, where the account endpoints reject
    # ``page=11&offset=1000`` outright. Verified live 2026-09-02, walking a
    # 33-holder token (Spiko EU T-Bills, 0xa0769f7a8fc65e47de93797b4e21c073c117fc80)
    # to exhaustion at offset=10: pages 1-3 returned 10 items each, page 4
    # returned 3 (a genuine short final page) and the total — 33 unique
    # addresses — matched BlockScout V2's independent ``holders_count`` field
    # for the same token exactly. ``None`` here is that positive claim of
    # completeness, not an absence of a cap.
    RESULT_WINDOW_OVERRIDES = {
        Method.EVENT_LOGS: API_MAX_OFFSET_LOGS,
        Method.TOKEN_HOLDERS: None,
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
            self._instance_root = base_url
            return

        # Get BlockScout instance for this network (shared unknown-network
        # ValueError shape lives on the base).
        self.instance_domain = self._require_mapped_network(
            self.NETWORK_INSTANCES, 'BlockScout instance'
        )
        self._instance_root = f'https://{self.instance_domain}'

    # ------------------------------------------------------------------
    # Provider dialect (the base owns the ladder, dispatch and params)
    # ------------------------------------------------------------------

    def _request_url(self, spec: EndpointSpec, params: dict[str, Any]) -> str:
        """Full per-instance URL: BlockScout instances live on their own
        hosts, unlike Etherscan's shared subdomain layout. The root is the
        ``_instance_root`` attribute set in ``__init__``."""
        return f'{self._instance_root}{spec.path}'

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
            url=f'{self._instance_root}/api/eth-rpc',
            json_data={'jsonrpc': '2.0', 'method': rpc_method, 'params': rpc_params, 'id': 1},
            headers={},
        )

    # Most SPECS are inherited from the shared Etherscan-like implementation.
    # BlockScout supports the same endpoints:
    # - ACCOUNT_BALANCE, ACCOUNT_TRANSACTIONS, ACCOUNT_INTERNAL_TXS
    # - ACCOUNT_ERC20_TRANSFERS, TX_BY_HASH, TX_RECEIPT_STATUS
    # - BLOCK_BY_NUMBER, BLOCK_REWARD, CONTRACT_ABI, CONTRACT_SOURCE
    # - TOKEN_BALANCE, TOKEN_SUPPLY, GAS_ORACLE, EVENT_LOGS
    # - ETH_SUPPLY, ETH_PRICE, PROXY_ETH_CALL
    #
    # TOKEN_HOLDERS is the one override below: Etherscan's action name
    # (``tokenholderlist``) really does answer "Unknown action" on
    # BlockScout's Etherscan-compat layer, but that is a naming mismatch, not
    # a missing capability — BlockScout's OWN action name
    # (``module=token&action=getTokenHolders``) works and paginates for real
    # (verified live 2026-09-02 against eth.blockscout.com).
    SPECS = {
        **EtherscanLikeScanner.SPECS,
        Method.TOKEN_HOLDERS: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'token', 'action': 'getTokenHolders'},
            param_map={
                'contract_address': 'contractaddress',
                'page': 'page',
                'offset': 'offset',
            },
            parser=_parse_token_holders,
        ),
    }
