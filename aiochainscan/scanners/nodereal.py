"""NodeReal MegaNode BSC scanner (JSON-RPC 2.0 + BscScan-compatible contract REST).

NodeReal operates the MegaNode BSC endpoint — the API behind the BSCTrace
explorer (https://bsctrace.com) and the only BSC analytics source in the
unified pipeline. Two transports live behind one scanner:

- JSON-RPC 2.0 (``POST https://bsc-{mainnet,testnet}.nodereal.io/v1/{key}``):
  standard ``eth_*`` methods plus NodeReal's ``nr_*`` Enhanced API
  (transfers by address, token/NFT holdings, token meta, contract creation).
- BscScan-compatible REST (``GET https://open-platform.nodereal.io/{key}/
  bsc-{mainnet,testnet}/contract/?action=getabi|getsourcecode``) for verified
  contracts.

Only BSC is wired up (mainnet + testnet).

Pagination notes (verified against BSC mainnet):
- ``nr_getTransactionByAddress`` serves at most 1000 blocks per request and
  *silently returns an empty page* for wider ranges, so :meth:`fetch_page`
  walks the requested block range in 1000-block windows. ``get_all_*`` /
  ``iter_*_streaming`` therefore see the complete history instead of a
  silently truncated window.
- An exhausted transfer page comes back as an *empty-string* ``pageKey``;
  a window that still has blocks left is followed by a synthetic window
  cursor instead.
- ``nr_getTokenHoldings`` / ``nr_getNFTHoldings`` use page/pageSize (≤100
  items) with a hex ``totalCount``; the cursor advances the page number.
- API exhaustion surfaces as JSON-RPC error ``-32005`` and is translated to
  :class:`~aiochainscan.exceptions.ChainscanRateLimitError` so the transport
  retry policy applies.

Data contract: hex quantities are normalized to decimal Wei strings
(``value``, balances, supplies) and hex block numbers to ints, matching the
library-wide "Wei strings" convention; unknown provider fields are preserved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import orjson

from ..constants import MAX_BLOCK_NUMBER
from ..core.endpoint import EndpointSpec
from ..core.method import Method
from ..core.url_builder import UrlBuilder
from ..exceptions import (
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
    MethodNotDeclaredError,
)
from . import register_scanner
from .base import Scanner

if TYPE_CHECKING:
    from ..network import Network

# Wire-level (JSON-RPC) limits of nr_getTransactionByAddress.
_TRANSFER_WINDOW = 1000
_TRANSFER_MAX_COUNT = 1000
_HISTORICAL_TRANSFER_WINDOW = 100_000  # nr_getAssetTransfers limit (unused here, documented)
_HOLDINGS_PAGE_SIZE = 100  # nr_get*Holdings pageSize cap ("should be less equal than 100")
_RATE_LIMIT_JSONRPC_CODE = -32005

# Cursor keys threaded through fetch_page params (must not collide with wire params).
_WINDOW_CURSOR = '__nr_window'
_TIP_CURSOR = '__nr_tip'


# ---------------------------------------------------------------------------
# Hex helpers — NodeReal returns hex quantities; the library contract is
# decimal Wei strings.
# ---------------------------------------------------------------------------


def _hex_qty_to_decimal_str(value: Any) -> Any:
    """Convert a hex quantity (``'0x2a'``) to a decimal string; pass through others."""
    if isinstance(value, str) and value.startswith(('0x', '0X')):
        try:
            return str(int(value, 16))
        except ValueError:
            return value
    return value


def _int_to_hex_quantity(value: int) -> str:
    return hex(value)


def _parse_hex_int(value: Any, default: int = 0) -> int:
    """Parse a hex quantity or int; fall back to ``default`` for None/invalid."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return (
            int(value, 16)
            if isinstance(value, str) and value.startswith(('0x', '0X'))
            else int(value)
        )
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Response parsers (call() path). fetch_page consumes raw envelopes instead.
# ---------------------------------------------------------------------------


def _parse_balance(result: Any) -> str:
    """``eth_getBalance`` hex Wei → decimal Wei string."""
    return str(_parse_hex_int(result))


def _parse_transfer_items(result: Any) -> list[dict[str, Any]]:
    """Normalize ``nr_getTransactionByAddress`` transfers.

    Adds unified aliases (``block_number`` int, decimal ``value``, ...) while
    preserving the provider fields for fidelity.
    """
    if not isinstance(result, dict):
        return []
    items: list[dict[str, Any]] = []
    for transfer in result.get('transfers') or []:
        item = dict(transfer)
        item['block_number'] = _parse_hex_int(transfer.get('blockNum'))
        item['value'] = _hex_qty_to_decimal_str(transfer.get('value'))
        items.append(item)
    return items


def _filter_transfer_items(
    items: list[dict[str, Any]], params: dict[str, Any]
) -> list[dict[str, Any]]:
    """Apply token-contract filtering unsupported by the NodeReal wire API."""
    requested_contract = _param(params, 'contract_address', 'contractaddress')
    if not requested_contract:
        return items
    normalized_contract = str(requested_contract).lower()
    return [
        item
        for item in items
        if str(item.get('contractAddress') or '').lower() == normalized_contract
    ]


def _parse_holdings(result: Any) -> list[dict[str, Any]]:
    """``nr_getTokenHoldings`` / ``nr_getNFTHoldings`` → list of ``details``."""
    if not isinstance(result, dict):
        return []
    details = result.get('details') or []
    return [dict(item) for item in details]


def _parse_token_meta(result: Any) -> dict[str, Any]:
    """``nr_getTokenMeta`` → ``{'name', 'symbol', 'decimals', 'tokenType'}``.

    The live API spells the decimals field ``decimals``; some doc examples
    carry the ``decimails`` typo — accepted defensively.
    """
    if not isinstance(result, dict):
        return {}
    meta = dict(result)
    if 'decimals' not in meta and 'decimails' in meta:
        meta['decimals'] = meta['decimails']
    return meta


def _parse_contract_creation(result: Any) -> list[dict[str, Any]]:
    """``nr_getContractCreationTransaction`` receipt → creator listing."""
    if not isinstance(result, dict):
        return []
    return [
        {
            'contractAddress': result.get('contractAddress'),
            'contractCreator': result.get('from'),
            'txHash': result.get('hash'),
            'blockNumber': result.get('blockNumber'),
            'timestamp': result.get('timestamp'),
        }
    ]


def _parse_token_balance(result: Any) -> str:
    """32-byte-padded hex token balance → decimal string."""
    return str(_parse_hex_int(result))


def _parse_block_number_by_timestamp(result: Any) -> str:
    """Hex block number → decimal string (Etherscan ``getblocknobytime`` parity)."""
    return str(_parse_hex_int(result))


def _parse_status_check(result: Any) -> dict[str, Any]:
    """Receipt → Etherscan ``checktransactionstatus``-shaped verdict."""
    if not isinstance(result, dict) or result.get('status') is None:
        return {'status': '0', 'message': 'Transaction not found', 'result': ''}
    executed = str(_parse_hex_int(result.get('status')))
    return {
        'status': '1',
        'message': 'OK',
        'result': executed,
    }


def _parse_contract_abi(payload: Any) -> str:
    """Contract ABI payload → JSON string (``SmartContract`` contract).

    The open-platform endpoint unwraps (via Network) to ``{'abi': [...]}``;
    the documented Etherscan-style envelope unwraps to a JSON string.
    """
    if isinstance(payload, dict) and 'abi' in payload:
        abi: Any = payload['abi']
        if isinstance(abi, str):
            return abi
        return orjson.dumps(abi).decode()
    if isinstance(payload, str):
        return payload
    return orjson.dumps(payload).decode()


def _parse_logs(result: Any) -> list[dict[str, Any]]:
    """``eth_getLogs`` → raw log list."""
    if isinstance(result, list):
        return [dict(item) if isinstance(item, dict) else {'value': item} for item in result]
    return []


# ---------------------------------------------------------------------------
# Wire parameter builders. Public param names come from the mixins (see
# ``tests/test_method_consistency.py`` INVOCATIONS) and the streaming
# iterators (``startblock``/``endblock`` spellings).
# ---------------------------------------------------------------------------


def _param(params: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in params and params[name] is not None:
            return params[name]
    return default


def _build_transfer_filter(
    params: dict[str, Any],
    category: list[str],
    *,
    window: tuple[int, int] | None,
    page_key: str,
    end_block: int,
) -> dict[str, Any]:
    """Build the ``nr_getTransactionByAddress`` filter object.

    ``window`` is ``(start, end)`` inclusive; when ``None`` the most recent
    window ending at ``end_block`` is used (single-page "latest activity"
    semantics, matching the API's own ``toBlock − 1000`` default).
    """
    if window is None:
        window = (max(end_block - _TRANSFER_WINDOW + 1, 0), end_block)
    address = _param(params, 'address')
    if not address:
        raise ValueError('address is required')
    filter_: dict[str, Any] = {
        'category': category,
        'address': address,
        'fromBlock': _int_to_hex_quantity(window[0]),
        'toBlock': _int_to_hex_quantity(window[1]),
    }
    order = _param(params, 'sort', 'order')
    filter_['order'] = str(order).lower() if order else 'desc'
    offset = _param(params, 'offset')
    max_count = _parse_hex_int(offset, _TRANSFER_MAX_COUNT)
    filter_['maxCount'] = _int_to_hex_quantity(max(1, min(max_count, _TRANSFER_MAX_COUNT)))
    if page_key:
        filter_['pageKey'] = page_key
    return filter_


@register_scanner
class NodeRealScanner(Scanner):
    """Scanner for the NodeReal MegaNode BSC endpoint (BSCTrace backend).

    Example:
        client = await ChainscanClient.from_config('nodereal', 'bsc')
        balance = await client.get_balance('0x...')
        txs = await client.get_all_transactions('0x...')  # window-walking
    """

    name = 'nodereal'
    version = 'v1'

    supported_networks = {'bsc', 'bnb', 'binance', 'bsc-testnet'}

    auth_mode = 'query'  # informational; the key rides in the URL path
    auth_field = 'apikey'

    # Network -> JSON-RPC base (API key appended as the last path segment)
    RPC_BASE_URLS: ClassVar[dict[str, str]] = {
        'bsc': 'https://bsc-mainnet.nodereal.io/v1',
        'bnb': 'https://bsc-mainnet.nodereal.io/v1',
        'binance': 'https://bsc-mainnet.nodereal.io/v1',
        'bsc-testnet': 'https://bsc-testnet.nodereal.io/v1',
    }

    # Network -> open-platform path segment for the BscScan-compatible
    # verified-contract REST endpoints.
    CONTRACT_PATHS: ClassVar[dict[str, str]] = {
        'bsc': 'bsc-mainnet',
        'bnb': 'bsc-mainnet',
        'binance': 'bsc-mainnet',
        'bsc-testnet': 'bsc-testnet',
    }

    TRANSFER_CATEGORIES: ClassVar[dict[Method, list[str]]] = {
        Method.ACCOUNT_TRANSACTIONS: ['external'],
        Method.ACCOUNT_INTERNAL_TXS: ['internal'],
        Method.ACCOUNT_ERC20_TRANSFERS: ['20'],
        Method.ACCOUNT_ERC721_TRANSFERS: ['721'],
        Method.ACCOUNT_ERC1155_TRANSFERS: ['1155'],
    }

    _TRANSFER_METHODS: ClassVar[frozenset[Method]] = frozenset(TRANSFER_CATEGORIES)
    _HOLDINGS_METHODS: ClassVar[frozenset[Method]] = frozenset(
        {Method.ACCOUNT_TOKEN_PORTFOLIO, Method.ACCOUNT_NFT_PORTFOLIO}
    )
    _REST_METHODS: ClassVar[frozenset[Method]] = frozenset(
        {Method.CONTRACT_ABI, Method.CONTRACT_SOURCE}
    )

    # JSON-RPC wire method per logical method (transfers share one wire method)
    _WIRE_METHODS: ClassVar[dict[Method, str]] = {
        Method.ACCOUNT_BALANCE: 'eth_getBalance',
        Method.ACCOUNT_TRANSACTIONS: 'nr_getTransactionByAddress',
        Method.ACCOUNT_INTERNAL_TXS: 'nr_getTransactionByAddress',
        Method.ACCOUNT_ERC20_TRANSFERS: 'nr_getTransactionByAddress',
        Method.ACCOUNT_ERC721_TRANSFERS: 'nr_getTransactionByAddress',
        Method.ACCOUNT_ERC1155_TRANSFERS: 'nr_getTransactionByAddress',
        Method.ACCOUNT_TOKEN_PORTFOLIO: 'nr_getTokenHoldings',
        Method.ACCOUNT_NFT_PORTFOLIO: 'nr_getNFTHoldings',
        Method.TX_BY_HASH: 'eth_getTransactionByHash',
        Method.TX_RECEIPT_STATUS: 'eth_getTransactionReceipt',
        Method.TX_STATUS_CHECK: 'eth_getTransactionReceipt',
        Method.BLOCK_BY_NUMBER: 'eth_getBlockByNumber',
        Method.BLOCK_NUMBER_BY_TIMESTAMP: 'nr_getBlockNumberByTimeStamp',
        Method.CONTRACT_CREATION: 'nr_getContractCreationTransaction',
        Method.TOKEN_BALANCE: 'nr_getTokenBalance20',
        Method.TOKEN_SUPPLY: 'nr_getTotalSupply20',
        Method.TOKEN_INFO: 'nr_getTokenMeta',
        Method.EVENT_LOGS: 'eth_getLogs',
        Method.PROXY_ETH_CALL: 'eth_call',
        Method.PROXY_GET_BALANCE: 'eth_getBalance',
    }

    SPECS: dict[Method, EndpointSpec] = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'address': 'address', 'tag': 'tag'},
            parser=_parse_balance,
        ),
        Method.ACCOUNT_TRANSACTIONS: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={
                'address': 'address',
                'start_block': 'fromBlock',
                'end_block': 'toBlock',
                'startblock': 'fromBlock',
                'endblock': 'toBlock',
                'sort': 'order',
                'offset': 'maxCount',
                'page': 'page',  # accepted for mixin parity; pageKey cursors supersede it
            },
            parser=_parse_transfer_items,
        ),
        Method.ACCOUNT_INTERNAL_TXS: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={
                'address': 'address',
                'start_block': 'fromBlock',
                'end_block': 'toBlock',
                'page': 'page',
                'offset': 'maxCount',
                'sort': 'order',
            },
            parser=_parse_transfer_items,
        ),
        Method.ACCOUNT_ERC20_TRANSFERS: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={
                'address': 'address',
                'start_block': 'fromBlock',
                'end_block': 'toBlock',
                # Accepted by the public API and enforced client-side.
                'contract_address': 'contract_address',
                'page': 'page',
                'offset': 'maxCount',
                'sort': 'order',
            },
            parser=_parse_transfer_items,
        ),
        Method.ACCOUNT_ERC721_TRANSFERS: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={
                'address': 'address',
                'start_block': 'fromBlock',
                'end_block': 'toBlock',
                # Accepted by the public API and enforced client-side.
                'contract_address': 'contract_address',
                'page': 'page',
                'offset': 'maxCount',
                'sort': 'order',
            },
            parser=_parse_transfer_items,
        ),
        Method.ACCOUNT_ERC1155_TRANSFERS: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={
                'address': 'address',
                'start_block': 'fromBlock',
                'end_block': 'toBlock',
                # Accepted by the public API and enforced client-side.
                'contract_address': 'contract_address',
                'page': 'page',
                'offset': 'maxCount',
                'sort': 'order',
            },
            parser=_parse_transfer_items,
        ),
        Method.ACCOUNT_TOKEN_PORTFOLIO: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'address': 'address', 'page': 'page', 'page_size': 'pageSize'},
            parser=_parse_holdings,
        ),
        Method.ACCOUNT_NFT_PORTFOLIO: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={
                'address': 'address',
                'page': 'page',
                'page_size': 'pageSize',
                'token_type': 'tokenType',
            },
            parser=_parse_holdings,
        ),
        Method.TX_BY_HASH: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'txhash': 'txhash'},
        ),
        Method.TX_RECEIPT_STATUS: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'txhash': 'txhash'},
        ),
        Method.TX_STATUS_CHECK: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'txhash': 'txhash'},
            parser=_parse_status_check,
        ),
        Method.BLOCK_BY_NUMBER: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'block_number': 'block_number'},
        ),
        Method.BLOCK_NUMBER_BY_TIMESTAMP: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'timestamp': 'timestamp', 'closest': 'closest'},
            parser=_parse_block_number_by_timestamp,
        ),
        Method.CONTRACT_CREATION: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'contract_addresses': 'contractAddress'},
            parser=_parse_contract_creation,
        ),
        Method.TOKEN_BALANCE: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={
                'address': 'address',
                'contract_address': 'contractAddress',
                'tag': 'tag',
            },
            parser=_parse_token_balance,
        ),
        Method.TOKEN_SUPPLY: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'contract_address': 'contractAddress'},
            parser=_parse_token_balance,
        ),
        Method.TOKEN_INFO: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'contract_address': 'contractAddress'},
            parser=_parse_token_meta,
        ),
        Method.CONTRACT_ABI: EndpointSpec(
            http_method='GET',
            path='/contract/',
            param_map={'address': 'address'},
            parser=_parse_contract_abi,
        ),
        Method.CONTRACT_SOURCE: EndpointSpec(
            http_method='GET',
            path='/contract/',
            param_map={'address': 'address'},
        ),
        Method.EVENT_LOGS: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={
                'address': 'address',
                'from_block': 'fromBlock',
                'to_block': 'toBlock',
                'topic0': 'topic0',
                'topic1': 'topic1',
                'topic2': 'topic2',
                'topic3': 'topic3',
            },
            parser=_parse_logs,
        ),
        Method.PROXY_ETH_CALL: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'to': 'to', 'data': 'data', 'tag': 'tag'},
        ),
        Method.PROXY_GET_BALANCE: EndpointSpec(
            http_method='POST',
            path='/v1/{api_key}',
            param_map={'address': 'address', 'tag': 'tag'},
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
        """Initialize the NodeReal scanner.

        Args:
            api_key: MegaNode API key (``NODEREAL_KEY``); required, rides in
                the URL path.
            network: One of :attr:`supported_networks` (aliases of BSC mainnet
                included).
            url_builder: UrlBuilder instance (unused for requests; required by
                the Scanner port).
            chain_id: Optional chain id (resolved from the network otherwise).
            network_client: Injected Network transport.
            base_url: Not supported — NodeReal's endpoints embed the API key
                in the URL path and are not self-hostable; raises
                ``ValueError`` when provided.
        """
        if base_url is not None:
            raise ValueError(
                'NodeReal does not support custom base_url: its JSON-RPC endpoints '
                'embed the API key in the URL path and are not self-hostable'
            )
        super().__init__(api_key, network, url_builder, chain_id, network_client)
        self.rpc_base_url = self.RPC_BASE_URLS.get(network)
        self.contract_path = self.CONTRACT_PATHS.get(network)
        if self.rpc_base_url is None or self.contract_path is None:
            available = ', '.join(sorted(self.RPC_BASE_URLS))
            raise ValueError(
                f"Network '{network}' not mapped to a NodeReal endpoint. Available: {available}"
            )

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _rpc_url(self) -> str:
        if not self.api_key:
            raise ChainscanClientError(
                'NodeReal MegaNode requires an API key. Set NODEREAL_KEY '
                '(or pass api_key= to ChainscanClient.from_config).'
            )
        return f'{self.rpc_base_url}/{self.api_key}'

    def _require_network_client(self) -> Network:
        """Return the injected Network or raise the standard RuntimeError."""
        if self._network_client is None:
            raise RuntimeError(
                f'{self.name} v{self.version}: network_client is required. '
                'Create scanner via ChainscanClient.from_config() which injects it automatically.'
            )
        return self._network_client

    async def _rpc(self, wire_method: str, rpc_params: list[Any]) -> Any:
        """POST a JSON-RPC 2.0 request; return the unwrapped ``result``.

        ``Network._handle_response`` unwraps the JSON-RPC ``result`` and maps
        ``error`` objects to :class:`ChainscanClientProxyError`; the -32005
        usage-limit code is re-raised as a retryable rate-limit error.
        """
        envelope = {'jsonrpc': '2.0', 'method': wire_method, 'params': rpc_params, 'id': 1}
        network = self._require_network_client()
        try:
            return await network.request(
                method='POST',
                url=self._rpc_url(),
                json_data=envelope,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )
        except ChainscanClientProxyError as exc:
            if exc.code == _RATE_LIMIT_JSONRPC_CODE:
                raise ChainscanRateLimitError(exc.message, 'usage limit reached') from exc
            raise
        except (ChainscanClientApiError, ChainscanNetworkError):
            raise
        except Exception as e:
            raise ChainscanNetworkError(
                f'NodeReal unexpected error for {self.rpc_base_url}: {e}', retryable=False
            ) from e

    async def _rest_contract(self, action: str, address: str) -> Any:
        """GET a BscScan-compatible verified-contract endpoint."""
        network = self._require_network_client()
        url = f'https://open-platform.nodereal.io/{self.api_key}/{self.contract_path}/contract/'
        return await network.request(
            method='GET',
            url=url,
            params={'action': action, 'address': address},
            headers={'Accept': 'application/json'},
        )

    # ------------------------------------------------------------------
    # Wire parameter builders
    # ------------------------------------------------------------------

    def _build_rpc_params(self, method: Method, params: dict[str, Any]) -> list[Any]:
        """Translate public call params into positional JSON-RPC params."""
        if method in self._TRANSFER_METHODS:
            window = params.get(_WINDOW_CURSOR)
            window_tuple = (int(window[0]), int(window[1])) if window else None
            page_key = str(params.get('pageKey') or '')
            end_block = _parse_hex_int(params.get(_TIP_CURSOR), 0)
            filter_ = _build_transfer_filter(
                params,
                self.TRANSFER_CATEGORIES[method],
                window=window_tuple,
                page_key=page_key,
                end_block=end_block,
            )
            return [filter_]
        if method == Method.ACCOUNT_TOKEN_PORTFOLIO:
            page = _parse_hex_int(params.get('page'), 1)
            size = min(
                _parse_hex_int(params.get('page_size'), _HOLDINGS_PAGE_SIZE), _HOLDINGS_PAGE_SIZE
            )
            return [
                params['address'],
                _int_to_hex_quantity(max(page, 1)),
                _int_to_hex_quantity(max(size, 1)),
            ]
        if method == Method.ACCOUNT_NFT_PORTFOLIO:
            page = _parse_hex_int(params.get('page'), 1)
            size = min(
                _parse_hex_int(params.get('page_size'), _HOLDINGS_PAGE_SIZE), _HOLDINGS_PAGE_SIZE
            )
            token_type = str(_param(params, 'token_type', default='erc721')).lower()
            return [
                params['address'],
                token_type,
                _int_to_hex_quantity(max(page, 1)),
                _int_to_hex_quantity(max(size, 1)),
            ]
        if method == Method.ACCOUNT_BALANCE:
            return [params['address'], str(_param(params, 'tag', default='latest'))]
        if method in (Method.TX_BY_HASH, Method.TX_RECEIPT_STATUS, Method.TX_STATUS_CHECK):
            return [params['txhash']]
        if method == Method.BLOCK_BY_NUMBER:
            block = params['block_number']
            if isinstance(block, int) or (isinstance(block, str) and block.isdigit()):
                block = _int_to_hex_quantity(int(block))
            return [block, False]
        if method == Method.BLOCK_NUMBER_BY_TIMESTAMP:
            closest = str(_param(params, 'closest', default='before')).upper()
            if closest not in ('BEFORE', 'AFTER'):
                raise ValueError(f"closest must be 'before' or 'after', got {closest!r}")
            return [int(_param(params, 'timestamp')), closest]
        if method == Method.CONTRACT_CREATION:
            addresses = str(params['contract_addresses']).split(',')
            if len(addresses) > 1:
                raise ValueError(
                    'NodeReal supports one contract address per '
                    f'CONTRACT_CREATION call, got {len(addresses)}'
                )
            return [addresses[0]]
        if method == Method.TOKEN_BALANCE:
            return [
                params['contract_address'],
                params['address'],
                str(_param(params, 'tag', default='latest')),
            ]
        if method == Method.TOKEN_SUPPLY:
            return [params['contract_address'], 'latest']
        if method == Method.TOKEN_INFO:
            return [params['contract_address']]
        if method == Method.EVENT_LOGS:
            return [self._build_log_filter(params)]
        if method == Method.PROXY_ETH_CALL:
            return [
                {'to': params['to'], 'data': params['data']},
                str(_param(params, 'tag', default='latest')),
            ]
        if method == Method.PROXY_GET_BALANCE:
            return [params['address'], str(_param(params, 'tag', default='latest'))]
        raise ValueError(f'Method {method} has no NodeReal wire mapping')  # pragma: no cover

    @staticmethod
    def _build_log_filter(params: dict[str, Any]) -> dict[str, Any]:
        from_block = _param(params, 'from_block', 'fromBlock', default=0)
        from_block_hex = (
            from_block if isinstance(from_block, str) else _int_to_hex_quantity(int(from_block))
        )
        to_block = _param(params, 'to_block', 'toBlock', default='latest')
        to_block_hex = (
            to_block if isinstance(to_block, str) else _int_to_hex_quantity(int(to_block))
        )
        log_filter: dict[str, Any] = {'fromBlock': from_block_hex, 'toBlock': to_block_hex}
        address = params.get('address')
        if address:
            log_filter['address'] = address
        topics = [params.get(topic) for topic in ('topic0', 'topic1', 'topic2', 'topic3')]
        while topics and topics[-1] is None:
            topics.pop()
        if topics:
            log_filter['topics'] = topics
        return log_filter

    # ------------------------------------------------------------------
    # Scanner port
    # ------------------------------------------------------------------

    async def call(self, method: Method, **params: Any) -> Any:
        """Execute a logical method against NodeReal (JSON-RPC or contract REST)."""
        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise MethodNotDeclaredError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )
        if self._network_client is None:
            raise RuntimeError(
                f'{self.name} v{self.version}: network_client is required. '
                'Create scanner via ChainscanClient.from_config() which injects it automatically.'
            )

        spec = self.SPECS[method]
        try:
            if method in self._REST_METHODS:
                address = str(params['address'])
                action = 'getabi' if method == Method.CONTRACT_ABI else 'getsourcecode'
                raw_response = await self._rest_contract(action, address)
            else:
                if method in self._TRANSFER_METHODS:
                    # Single-page semantics: without explicit bounds, serve the
                    # most recent window; with start_block, the window at start.
                    params = dict(params)
                    tip = params.get(_TIP_CURSOR)
                    if tip is None:
                        requested_end = _param(params, 'end_block', 'endblock')
                        if isinstance(requested_end, int) and requested_end < MAX_BLOCK_NUMBER:
                            tip = requested_end
                        else:
                            tip = await self._resolve_tip()
                    params[_TIP_CURSOR] = int(tip)
                    start = _param(params, 'start_block', 'startblock')
                    if params.get(_WINDOW_CURSOR) is None and start is not None:
                        start = _parse_hex_int(start, 0)
                        params[_WINDOW_CURSOR] = [
                            start,
                            min(start + _TRANSFER_WINDOW - 1, int(tip)),
                        ]
                rpc_params = self._build_rpc_params(method, params)
                raw_response = await self._rpc(self._WIRE_METHODS[method], rpc_params)
            parsed_response = spec.parse_response(raw_response)
            if method in self._TRANSFER_METHODS and isinstance(parsed_response, list):
                return _filter_transfer_items(parsed_response, params)
            return parsed_response
        except ChainscanClientApiError:
            raise
        except ChainscanNetworkError:
            raise
        except (ChainscanClientProxyError, ChainscanRateLimitError):
            raise
        except ChainscanClientError:
            raise
        except Exception as e:
            raise ChainscanNetworkError(
                f'NodeReal unexpected error for {method.name}: {e}', retryable=False
            ) from e

    async def fetch_page(
        self,
        method: Method,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Fetch one page plus the next cursor.

        Cursor contract (see :meth:`Scanner.fetch_page`):
        - transfer methods: ``{'__nr_window': [start, end], 'pageKey': str}``
          continues a window; ``{'__nr_window': [...], 'pageKey': ''}`` opens
          the next 1000-block window; ``None`` ends pagination. The resolved
          chain tip rides along as ``__nr_tip`` so later windows need no extra
          ``eth_blockNumber`` round-trip.
        - holdings methods: ``{'page': n, 'page_size': s}`` until
          ``page * page_size >= totalCount``.
        - everything else: single page, ``None``.
        """
        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise MethodNotDeclaredError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )
        if self._network_client is None:
            raise RuntimeError(
                f'{self.name} v{self.version}: network_client is required. '
                'Create scanner via ChainscanClient.from_config() which injects it automatically.'
            )

        if method in self._TRANSFER_METHODS:
            return await self._fetch_transfer_page(method, params)
        if method in self._HOLDINGS_METHODS:
            return await self._fetch_holdings_page(method, params)
        result = await self.call(method, **params)
        return Scanner._coerce_items(result), None

    async def _resolve_tip(self) -> int:
        """Current chain tip via ``eth_blockNumber`` (hex → int)."""
        return _parse_hex_int(await self._rpc('eth_blockNumber', []))

    async def _fetch_transfer_page(
        self,
        method: Method,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        window = params.get(_WINDOW_CURSOR)
        page_key = str(params.get('pageKey') or '')
        raw_tip = params.get(_TIP_CURSOR)
        tip: int
        if isinstance(raw_tip, int):
            tip = raw_tip
        elif window is not None:
            # Every cursor carries the resolved tip; resolve defensively if lost.
            tip = await self._resolve_tip()
        else:
            requested_end = _param(params, 'end_block', 'endblock')
            # The streaming iterators pass MAX_BLOCK_NUMBER as an "unbounded"
            # sentinel; resolve the real chain tip for it.
            if isinstance(requested_end, int) and requested_end < MAX_BLOCK_NUMBER:
                tip = requested_end
            else:
                tip = await self._resolve_tip()

        if window is not None:
            window_start, window_end = int(window[0]), int(window[1])
        else:
            start = _parse_hex_int(_param(params, 'start_block', 'startblock'), 0)
            window_start, window_end = start, min(start + _TRANSFER_WINDOW - 1, tip)

        # Call the wire method directly (window bounds live in the cursor,
        # not in wire params, so call()'s builder defaults don't apply).
        filter_ = _build_transfer_filter(
            params,
            self.TRANSFER_CATEGORIES[method],
            window=(window_start, window_end),
            page_key=page_key,
            end_block=tip,
        )
        raw = await self._rpc('nr_getTransactionByAddress', [filter_])
        if not isinstance(raw, dict):
            return [], None

        next_page_key = str(raw.get('pageKey') or '')
        items = _filter_transfer_items(_parse_transfer_items(raw), params)

        if next_page_key:
            cursor: dict[str, Any] = {
                _WINDOW_CURSOR: [window_start, window_end],
                'pageKey': next_page_key,
                _TIP_CURSOR: tip,
            }
        else:
            next_start = window_end + 1
            if window_end >= tip or next_start > tip:
                return items, None
            cursor = {
                _WINDOW_CURSOR: [next_start, min(next_start + _TRANSFER_WINDOW - 1, tip)],
                'pageKey': '',
                _TIP_CURSOR: tip,
            }
        return items, cursor

    async def _fetch_holdings_page(
        self,
        method: Method,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        page = max(_parse_hex_int(params.get('page'), 1), 1)
        page_size = max(
            min(_parse_hex_int(params.get('page_size'), _HOLDINGS_PAGE_SIZE), _HOLDINGS_PAGE_SIZE),
            1,
        )
        rpc_params = self._build_rpc_params(
            method, {**params, 'page': page, 'page_size': page_size}
        )
        raw = await self._rpc(self._WIRE_METHODS[method], rpc_params)
        if not isinstance(raw, dict):
            return [], None
        total = _parse_hex_int(raw.get('totalCount'), 0)
        items = _parse_holdings(raw)
        if page * page_size >= total:
            return items, None
        return items, {'page': page + 1, 'page_size': page_size}

    def __str__(self) -> str:
        """String representation including endpoint info."""
        return f'NodeReal v{self.version} ({self.rpc_base_url})'

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"NodeRealScanner(network='{self.network}', "
            f"rpc_base_url='{self.rpc_base_url}', "
            f'methods={len(self.SPECS)})'
        )
