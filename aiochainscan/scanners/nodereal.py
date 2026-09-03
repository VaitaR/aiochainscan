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
- ``nr_getTokenHolders`` (``TOKEN_HOLDERS``) pages via an opaque ``PageKey``
  (empty for the first page; an empty ``pageKey`` in the response ends
  pagination) with a hex-encoded ``PageSize`` capped at 100 — the same cap
  NodeReal documents for the holdings endpoints, reused rather than a new
  page-numbered mechanism since this endpoint has no page number at all.
  ``nr_getTokenHolderCount`` (``TOKEN_HOLDER_COUNT``) returns a hex-encoded
  scalar. Both are documented "Supported on BSC and ETH mainnet only" —
  narrower than this scanner's own ``supported_networks`` (BSC only); see
  AGENTS.md for the discrepancy. The list shape was live-verified
  (2026-09-02, bsc-mainnet); the count envelope accepts both the documented
  and the live-nested shape.
- API exhaustion surfaces as JSON-RPC error ``-32005`` and is translated to
  :class:`~aiochainscan.exceptions.ChainscanRateLimitError` so the transport
  retry policy applies.

Data contract: hex quantities are normalized to decimal Wei strings
(``value``, balances, supplies) and hex block numbers to ints, matching the
library-wide "Wei strings" convention; unknown provider fields are preserved.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

import orjson

from ..constants import MAX_BLOCK_NUMBER
from ..convert import hex_to_int
from ..core.endpoint import EndpointSpec
from ..core.url_builder import UrlBuilder
from ..domain.method import Method
from ..exceptions import (
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanDataError,
    ChainscanRateLimitError,
    ScannerArgumentError,
)
from . import register_scanner
from .base import (
    Scanner,
    checksummed_holder_address,
    hex_block_tag,
    translate_unexpected_errors,
)

if TYPE_CHECKING:
    from ..network import Network

# Wire-level (JSON-RPC) limits of nr_getTransactionByAddress.
_TRANSFER_WINDOW = 1000
_TRANSFER_MAX_COUNT = 1000
_HOLDINGS_PAGE_SIZE = 100  # nr_get*Holdings pageSize cap ("should be less equal than 100")
_RATE_LIMIT_JSONRPC_CODE = -32005

# Cursor keys threaded through fetch_page params (must not collide with wire params).
_WINDOW_CURSOR = '__nr_window'
_TIP_CURSOR = '__nr_tip'


# ---------------------------------------------------------------------------
# Hex helpers — NodeReal returns hex quantities; the library contract is
# decimal Wei strings. Parsing semantics are ``convert.hex_to_int``; the
# wrapper exists because the wire/cursor values here are optional and must
# default on absence/corruption, where ``hex_to_int`` raises.
# ---------------------------------------------------------------------------


def _hex_qty_to_decimal_str(value: Any) -> Any:
    """Convert a hex quantity (``'0x2a'``) to a decimal string; pass through others."""
    if isinstance(value, str) and value.startswith(('0x', '0X')):
        try:
            return str(int(value, 16))
        except ValueError:
            return value
    return value


def _parse_hex_int(value: Any, default: int = 0) -> int:
    """Tolerant quantity parse (hex/decimal/int) falling back to ``default``."""
    if value is None:
        return default
    try:
        return hex_to_int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Response parsers (call() path). fetch_page consumes raw envelopes instead.
# ---------------------------------------------------------------------------


def _parse_balance(result: Any) -> str:
    """``eth_getBalance`` hex Wei → decimal Wei string.

    Deliberately NOT shared with ``blockscout_v2._parse_balance``: this one
    normalizes a bare JSON-RPC hex quantity, while BlockScout V2 reads a dict
    envelope whose ``coin_balance`` is already a decimal Wei string.
    """
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
    spec: EndpointSpec,
    items: list[dict[str, Any]],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply token-contract filtering unsupported by the NodeReal wire API.

    The accepted public spellings are the spec's declared ``contract_address``
    sources — the same declaration every other builder reads.
    """
    requested_contract = _param(params, *_declared_sources(spec, 'contract_address'))
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


def _parse_token_holders(result: Any) -> list[dict[str, Any]]:
    """``nr_getTokenHolders`` ``details`` → unified holder shape.

    Each entry is ``{'accountAddress': str, 'tokenBalance': hex str}``
    (https://docs.nodereal.io/reference/nr_gettokenholders). Normalized to
    the library-wide ``{'address': EIP-55 str, 'value': str}`` shape, matching
    ``etherscan_v2._parse_token_holders`` / ``blockscout_v2._normalize_token_holder_entry``
    exactly.
    """
    if not isinstance(result, dict):
        return []
    details = result.get('details') or []
    items: list[dict[str, Any]] = []
    for raw in details:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                'address': checksummed_holder_address(raw.get('accountAddress')),
                'value': str(_parse_hex_int(raw.get('tokenBalance'))),
            }
        )
    return items


def _parse_token_holder_count(result: Any) -> str:
    """``nr_getTokenHolderCount`` hex-encoded ``count`` → decimal string.

    The docs show a bare scalar — ``{"result": "0x123"}``, i.e. the JSON-RPC
    ``result`` IS the hex count
    (https://docs.nodereal.io/reference/nr_gettokenholdercount). The live API
    nests it one level deeper instead: ``{"result": {"result": "0x46b3f99"}}``
    (verified 2026-09-02 on ``bsc-mainnet``, BSC-USD and CAKE). Both shapes are
    accepted, since the doc-shaped one is what the provider promises.

    An unrecognized shape raises rather than counting zero: a token has holders,
    so "0" is never the honest reading of a response this parser cannot read —
    that answer looks exactly like a token nobody holds.
    """
    value = result.get('result', result.get('count')) if isinstance(result, dict) else result
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        try:
            return str(int(value, 16) if value.startswith(('0x', '0X')) else int(value))
        except ValueError:
            pass
    raise ChainscanDataError(
        'nr_getTokenHolderCount returned no readable count',
        details={'result': result},
    )


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
# Wire parameter builders. Every public→wire name comes from the method's
# ``EndpointSpec.param_map`` (first declared source wins) and the shape from
# its ``param_style`` — the same declarations ``supports_block_range`` and
# the consistency sweep read. Public param names come from the mixins (see
# ``tests/test_method_consistency.py`` INVOCATIONS), the streaming builders
# (``start_block``/``end_block``) and Etherscan-style direct callers (the
# ``startblock``/``endblock`` aliases).
# ---------------------------------------------------------------------------


def _param(params: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in params and params[name] is not None:
            return params[name]
    return default


def _declared_sources(spec: EndpointSpec, wire_name: str) -> tuple[str, ...]:
    """Public names declared to feed one wire parameter, in declaration order.

    The alias tolerance is the spec's own business: every public name whose
    declared wire name matches ``wire_name`` is accepted (alternate input
    spellings are declared in ``param_map`` too), first declared wins.
    """
    return tuple(public for public, wire in spec.param_map.items() if wire == wire_name)


def _take(params: dict[str, Any], public: str) -> Any:
    """Required public scalar, passed through (a missing one is a caller bug)."""
    return params[public]


def _tag_param(params: dict[str, Any], public: str) -> Any:
    """Block tag: quoted ``'latest'`` when absent."""
    value = params.get(public)
    return str(value) if value is not None else 'latest'


def _block_number_param(params: dict[str, Any], public: str) -> Any:
    """Block identifier → JSON-RPC hex-quantity tag (``'latest'`` passes through)."""
    return hex_block_tag(params[public])


def _timestamp_param(params: dict[str, Any], public: str) -> Any:
    """Timestamp as an int (the wire wants a number, not a quoted string)."""
    raw = _param(params, public)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ScannerArgumentError(
            f'{public} must be a unix timestamp (int or numeric string), got {raw!r}'
        ) from exc


def _closest_param(params: dict[str, Any], public: str) -> Any:
    """``before``/``after`` hint, uppercased; anything else is a caller bug."""
    closest = str(_param(params, public, default='before')).upper()
    if closest not in ('BEFORE', 'AFTER'):
        raise ScannerArgumentError(f"closest must be 'before' or 'after', got {closest!r}")
    return closest


def _contract_creation_param(params: dict[str, Any], public: str) -> Any:
    """First address of the public comma-separated list (NodeReal takes one)."""
    addresses = str(params[public]).split(',')
    if len(addresses) > 1:
        raise ScannerArgumentError(
            'NodeReal supports one contract address per '
            f'CONTRACT_CREATION call, got {len(addresses)}'
        )
    return addresses[0]


def _page_hex_param(params: dict[str, Any], public: str) -> Any:
    """1-based holdings page → hex quantity."""
    return hex(max(_parse_hex_int(params.get(public), 1), 1))


def _page_size_hex_param(params: dict[str, Any], public: str) -> Any:
    """Holder-family page size, clamped to the wire's 100 cap, → hex quantity.

    One clamp rule for every ``PageSize`` the wire takes: the holdings
    methods declare it as ``page_size``, the holder list/top-N as
    ``offset``/``top_n`` — the same documented "should be less equal than
    100" cap behind all of them.
    """
    size = min(_parse_hex_int(params.get(public), _HOLDINGS_PAGE_SIZE), _HOLDINGS_PAGE_SIZE)
    return hex(max(size, 1))


def _top_n_param(params: dict[str, Any], public: str) -> Any:
    """``topN``, sourced from ``offset`` when no explicit ``top_n`` is given.

    ``get_top_token_holders(limit=N)`` reaches the scanner as ``offset=N`` (the
    Etherscan-dialect spelling the mixin uses for every provider), and the wire
    takes the size twice: once as ``PageSize``, once as ``topN``. Without the
    fallback ``topN`` silently defaults to the 100 cap, so a caller asking for
    the top 5 receives 100 holders — the response is a valid page, so nothing
    downstream can notice.
    """
    return _page_size_hex_param(params, public if public in params else 'offset')


def _empty_page_key_param(params: dict[str, Any], public: str) -> Any:
    """The wire's PageKey placeholder for a single-shot call: always ``''``."""
    return ''


def _page_key_param(params: dict[str, Any], public: str) -> Any:
    """Opaque PageKey cursor as a string; ``''`` when absent (the first page)."""
    return str(params.get(public) or '')


def _token_type_param(params: dict[str, Any], public: str) -> Any:
    """NFT holdings token type, lowercased, ``'erc721'`` when absent."""
    return str(_param(params, public, default='erc721')).lower()


#: Value encoders for ``rpc-positional`` specs, keyed by public name (each
#: name carries one dialect rule, reused across methods). Names not listed
#: are required scalars passed through unchanged.
_PositionalEncoder = Callable[[dict[str, Any], str], Any]
_POSITIONAL_ENCODERS: dict[str, _PositionalEncoder] = {
    'tag': _tag_param,
    'block_number': _block_number_param,
    'timestamp': _timestamp_param,
    'closest': _closest_param,
    'contract_addresses': _contract_creation_param,
    'page': _page_hex_param,
    'page_size': _page_size_hex_param,
    'offset': _page_size_hex_param,  # holder list: offset IS the PageSize
    'top_n': _top_n_param,  # top-N: same 100-capped size as PageSize
    'page_key': _empty_page_key_param,
    'pageKey': _page_key_param,
    'token_type': _token_type_param,
}


def _build_transfer_filter(
    spec: EndpointSpec,
    category: list[str],
    params: dict[str, Any],
    *,
    window: tuple[int, int] | None,
    page_key: str,
    end_block: int,
) -> dict[str, Any]:
    """Build the ``nr_getTransactionByAddress`` filter object.

    All names come from ``spec.param_map``; ``window`` is ``(start, end)``
    inclusive, or ``None`` for the most recent window ending at ``end_block``
    (single-page "latest activity" semantics, matching the API's own
    ``toBlock − 1000`` default).
    """
    if window is None:
        window = (max(end_block - _TRANSFER_WINDOW + 1, 0), end_block)
    address = _param(params, *_declared_sources(spec, 'address'))
    if not address:
        raise ScannerArgumentError('address is required')
    filter_: dict[str, Any] = {
        'category': category,
        'address': address,
        'fromBlock': hex(window[0]),
        'toBlock': hex(window[1]),
    }
    order = _param(params, *_declared_sources(spec, 'order'))
    filter_['order'] = str(order).lower() if order else 'desc'
    offset = _param(params, *_declared_sources(spec, 'maxCount'))
    max_count = _parse_hex_int(offset, _TRANSFER_MAX_COUNT)
    filter_['maxCount'] = hex(max(1, min(max_count, _TRANSFER_MAX_COUNT)))
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

    # ``fetch_page`` already walks the block range in 1000-block windows and
    # follows ``pageKey`` inside each one, so no result window is exposed to
    # the pagination engine (see base class).
    result_window = None

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

    # Cursor vocabulary per paginated method, reusing the module-level key
    # constants (``_WINDOW_CURSOR``/``_TIP_CURSOR``) so the private names are
    # spelled exactly once. Declared here — where the cursors are produced —
    # so the MCP cursor whitelist derives them instead of hand-copying
    # (``Scanner.cursor_keys`` stays empty: the dialect differs per endpoint).
    CURSOR_KEYS: ClassVar[dict[Method, frozenset[str]]] = {
        **{
            method: frozenset({_WINDOW_CURSOR, _TIP_CURSOR, 'pageKey'})
            for method in TRANSFER_CATEGORIES
        },
        Method.ACCOUNT_TOKEN_PORTFOLIO: frozenset({'page', 'page_size'}),
        Method.ACCOUNT_NFT_PORTFOLIO: frozenset({'page', 'page_size'}),
        Method.TOKEN_HOLDERS: frozenset({'pageKey'}),
    }

    _TRANSFER_METHODS: ClassVar[frozenset[Method]] = frozenset(TRANSFER_CATEGORIES)
    _HOLDINGS_METHODS: ClassVar[frozenset[Method]] = frozenset(
        {Method.ACCOUNT_TOKEN_PORTFOLIO, Method.ACCOUNT_NFT_PORTFOLIO}
    )
    # nr_getTokenHolders pages by opaque PageKey (see fetch_page docstring) —
    # distinct from _HOLDINGS_METHODS' page-numbered totalCount mechanism.
    _HOLDER_METHODS: ClassVar[frozenset[Method]] = frozenset({Method.TOKEN_HOLDERS})
    _REST_METHODS: ClassVar[frozenset[Method]] = frozenset(
        {Method.CONTRACT_ABI, Method.CONTRACT_SOURCE}
    )

    # The public→wire mapping, declared once and executed by the builders
    # below. ``param_style`` selects the wire shape; ``param_map`` declares
    # every accepted public name (alternate input spellings included — first
    # declared wins) and, for ``rpc-positional`` methods, the positional wire
    # order; ``wire_method`` names the JSON-RPC method the spec dispatches to
    # (every rpc-dialect spec declares one — query-style contract-REST specs
    # have no wire method and leave it None). URLs are built by the dialect
    # hooks (_rpc_url / _rest_contract), so no spec declares a decorative
    # path. Block-range capability (``supports_block_range``) is read from
    # these same maps.
    SPECS: dict[Method, EndpointSpec] = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='eth_getBalance',
            param_map={'address': 'address', 'tag': 'tag'},
            parser=_parse_balance,
        ),
        Method.ACCOUNT_TRANSACTIONS: EndpointSpec(
            http_method='POST',
            param_style='rpc-object',
            wire_method='nr_getTransactionByAddress',
            param_map={
                'address': 'address',
                'start_block': 'fromBlock',
                'end_block': 'toBlock',
                # Tolerated Etherscan-style input spellings (window resolver
                # and filter builder read their sources from this map).
                'startblock': 'fromBlock',
                'endblock': 'toBlock',
                'sort': 'order',
                'order': 'order',
                'offset': 'maxCount',
                'page': 'page',  # accepted for mixin parity; pageKey cursors supersede it
            },
            parser=_parse_transfer_items,
        ),
        Method.ACCOUNT_INTERNAL_TXS: EndpointSpec(
            http_method='POST',
            param_style='rpc-object',
            wire_method='nr_getTransactionByAddress',
            param_map={
                'address': 'address',
                'start_block': 'fromBlock',
                'end_block': 'toBlock',
                'startblock': 'fromBlock',
                'endblock': 'toBlock',
                'page': 'page',
                'offset': 'maxCount',
                'sort': 'order',
                'order': 'order',
            },
            parser=_parse_transfer_items,
        ),
        Method.ACCOUNT_ERC20_TRANSFERS: EndpointSpec(
            http_method='POST',
            param_style='rpc-object',
            wire_method='nr_getTransactionByAddress',
            param_map={
                'address': 'address',
                'start_block': 'fromBlock',
                'end_block': 'toBlock',
                'startblock': 'fromBlock',
                'endblock': 'toBlock',
                # Accepted by the public API and enforced client-side
                # (`_filter_transfer_items` reads its sources from this map;
                # the Etherscan-style spelling is a tolerated alias).
                'contract_address': 'contract_address',
                'contractaddress': 'contract_address',
                'page': 'page',
                'offset': 'maxCount',
                'sort': 'order',
                'order': 'order',
            },
            parser=_parse_transfer_items,
        ),
        Method.ACCOUNT_ERC721_TRANSFERS: EndpointSpec(
            http_method='POST',
            param_style='rpc-object',
            wire_method='nr_getTransactionByAddress',
            param_map={
                'address': 'address',
                'start_block': 'fromBlock',
                'end_block': 'toBlock',
                'startblock': 'fromBlock',
                'endblock': 'toBlock',
                # Accepted by the public API and enforced client-side
                # (`_filter_transfer_items` reads its sources from this map;
                # the Etherscan-style spelling is a tolerated alias).
                'contract_address': 'contract_address',
                'contractaddress': 'contract_address',
                'page': 'page',
                'offset': 'maxCount',
                'sort': 'order',
                'order': 'order',
            },
            parser=_parse_transfer_items,
        ),
        Method.ACCOUNT_ERC1155_TRANSFERS: EndpointSpec(
            http_method='POST',
            param_style='rpc-object',
            wire_method='nr_getTransactionByAddress',
            param_map={
                'address': 'address',
                'start_block': 'fromBlock',
                'end_block': 'toBlock',
                'startblock': 'fromBlock',
                'endblock': 'toBlock',
                # Accepted by the public API and enforced client-side
                # (`_filter_transfer_items` reads its sources from this map;
                # the Etherscan-style spelling is a tolerated alias).
                'contract_address': 'contract_address',
                'contractaddress': 'contract_address',
                'page': 'page',
                'offset': 'maxCount',
                'sort': 'order',
                'order': 'order',
            },
            parser=_parse_transfer_items,
        ),
        Method.ACCOUNT_TOKEN_PORTFOLIO: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='nr_getTokenHoldings',
            param_map={'address': 'address', 'page': 'page', 'page_size': 'pageSize'},
            parser=_parse_holdings,
        ),
        Method.ACCOUNT_NFT_PORTFOLIO: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='nr_getNFTHoldings',
            param_map={
                'address': 'address',
                'token_type': 'tokenType',
                'page': 'page',
                'page_size': 'pageSize',
            },
            parser=_parse_holdings,
        ),
        Method.TX_BY_HASH: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='eth_getTransactionByHash',
            param_map={'txhash': 'txhash'},
        ),
        Method.TX_RECEIPT_STATUS: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='eth_getTransactionReceipt',
            param_map={'txhash': 'txhash'},
        ),
        Method.TX_STATUS_CHECK: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='eth_getTransactionReceipt',
            param_map={'txhash': 'txhash'},
            parser=_parse_status_check,
        ),
        Method.BLOCK_BY_NUMBER: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='eth_getBlockByNumber',
            param_map={'block_number': 'block_number'},
            # The wire's second positional: full-tx-objects flag, always False.
            query={'include_full_tx_objects': False},
        ),
        Method.BLOCK_NUMBER_BY_TIMESTAMP: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='nr_getBlockNumberByTimeStamp',
            param_map={'timestamp': 'timestamp', 'closest': 'closest'},
            parser=_parse_block_number_by_timestamp,
        ),
        Method.CONTRACT_CREATION: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='nr_getContractCreationTransaction',
            param_map={'contract_addresses': 'contractAddress'},
            parser=_parse_contract_creation,
        ),
        Method.TOKEN_BALANCE: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='nr_getTokenBalance20',
            param_map={'contract_address': 'contractAddress', 'address': 'address', 'tag': 'tag'},
            parser=_parse_token_balance,
        ),
        Method.TOKEN_SUPPLY: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='nr_getTotalSupply20',
            param_map={'contract_address': 'contractAddress'},
            # The wire takes a trailing block tag; no public param carries it.
            query={'tag': 'latest'},
            parser=_parse_token_balance,
        ),
        Method.TOKEN_INFO: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='nr_getTokenMeta',
            param_map={'contract_address': 'contractAddress'},
            parser=_parse_token_meta,
        ),
        Method.TOKEN_HOLDERS: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='nr_getTokenHolders',
            param_map={
                'contract_address': 'contract_address',
                # The wire's PageSize (hex, clamped to the documented 100 cap).
                'offset': 'PageSize',
                # Opaque PageKey cursor; '' opens the first page.
                'pageKey': 'pageKey',
                # Accepted for mixin parity, carries no positional — this
                # endpoint has no page number; the PageKey cursor supersedes
                # it (wire name '' = declared-inert input).
                'page': '',
            },
            parser=_parse_token_holders,
        ),
        Method.TOKEN_TOP_HOLDERS: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='nr_getTokenHolders',
            param_map={
                'contract_address': 'contract_address',
                'offset': 'PageSize',
                # Single non-paginated call: the wire's PageKey placeholder is
                # always the empty string, and topN repeats the clamped PageSize.
                'page_key': 'PageKey',
                'top_n': 'topN',
            },
            parser=_parse_token_holders,
        ),
        Method.TOKEN_HOLDER_COUNT: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='nr_getTokenHolderCount',
            param_map={'contract_address': 'contract_address'},
            parser=_parse_token_holder_count,
        ),
        Method.CONTRACT_ABI: EndpointSpec(
            http_method='GET',
            param_map={'address': 'address'},
            parser=_parse_contract_abi,
        ),
        Method.CONTRACT_SOURCE: EndpointSpec(
            http_method='GET',
            param_map={'address': 'address'},
        ),
        Method.EVENT_LOGS: EndpointSpec(
            http_method='POST',
            param_style='rpc-object',
            wire_method='eth_getLogs',
            param_map={
                'address': 'address',
                'from_block': 'fromBlock',
                'to_block': 'toBlock',
                'fromBlock': 'fromBlock',
                'toBlock': 'toBlock',
                'topic0': 'topic0',
                'topic1': 'topic1',
                'topic2': 'topic2',
                'topic3': 'topic3',
            },
            parser=_parse_logs,
        ),
        Method.PROXY_ETH_CALL: EndpointSpec(
            http_method='POST',
            param_style='rpc-object',
            wire_method='eth_call',
            # 'to'/'data' assemble eth_call's single call object; 'tag' is the
            # trailing block tag positional.
            param_map={'to': 'to', 'data': 'data', 'tag': 'tag'},
        ),
        Method.PROXY_GET_BALANCE: EndpointSpec(
            http_method='POST',
            param_style='rpc-positional',
            wire_method='eth_getBalance',
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
        # Shared unknown-network ValueError shape lives on the base.
        self.rpc_base_url = self._require_mapped_network(self.RPC_BASE_URLS, 'NodeReal endpoint')
        self.contract_path = self._require_mapped_network(self.CONTRACT_PATHS, 'NodeReal endpoint')

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

    async def _rpc(self, wire_method: str, rpc_params: list[Any]) -> Any:
        """POST a JSON-RPC 2.0 request; return the unwrapped ``result``.

        ``Network._handle_response`` unwraps the JSON-RPC ``result`` and maps
        ``error`` objects to :class:`ChainscanClientProxyError`; the -32005
        usage-limit code is re-raised as a retryable rate-limit error —
        provider-dialect translation composing with the shared error ladder
        (this ladder also covers the ``fetch_page`` paths that call ``_rpc``
        directly, outside :meth:`Scanner.call`).
        """
        envelope = {'jsonrpc': '2.0', 'method': wire_method, 'params': rpc_params, 'id': 1}
        network = self._require_network_client()
        with translate_unexpected_errors(f'NodeReal unexpected error for {self.rpc_base_url}'):
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
    # Wire parameter builders (driven by the SPECS declarations)
    # ------------------------------------------------------------------

    def _build_rpc_params(self, method: Method, params: dict[str, Any]) -> list[Any]:
        """Translate public call params into positional JSON-RPC params.

        The method's spec declares the shape (``param_style``) and every
        public→wire name (``param_map``); this builder only executes them.
        """
        spec = self._spec_for(method)
        if spec.param_style == 'rpc-positional':
            return self._build_positional_params(spec, params)
        if spec.param_style == 'rpc-object':
            return self._build_object_params(spec, method, params)
        # 'query' style on NodeReal is the contract-REST dialect, dispatched
        # by _perform_request before any RPC params are built.
        raise ValueError(f'Method {method} has no NodeReal wire mapping')  # pragma: no cover

    def _build_positional_params(self, spec: EndpointSpec, params: dict[str, Any]) -> list[Any]:
        """Public params → the positional JSON-RPC list the spec declares.

        ``param_map`` declaration order IS the positional wire order; each
        declared public name is fetched and encoded by
        ``_POSITIONAL_ENCODERS`` (required scalars pass through unchanged).
        Static values declared in ``spec.query`` ride as trailing positional
        constants (e.g. ``eth_getBlockByNumber``'s full-objects flag). A
        name declared with the empty wire name is accepted-but-inert
        (mixin-parity inputs the wire takes no positional for) and is
        skipped.
        """
        encoded = [
            _POSITIONAL_ENCODERS.get(public, _take)(params, public)
            for public, wire_name in spec.param_map.items()
            if wire_name
        ]
        return [*encoded, *spec.query.values()]

    def _build_object_params(
        self, spec: EndpointSpec, method: Method, params: dict[str, Any]
    ) -> list[Any]:
        """Object-argument methods: the filter/call object from declared sources."""
        if method in self._TRANSFER_METHODS:
            window = params.get(_WINDOW_CURSOR)
            window_tuple = (int(window[0]), int(window[1])) if window else None
            page_key = str(params.get('pageKey') or '')
            end_block = _parse_hex_int(params.get(_TIP_CURSOR), 0)
            return [
                _build_transfer_filter(
                    spec,
                    self.TRANSFER_CATEGORIES[method],
                    params,
                    window=window_tuple,
                    page_key=page_key,
                    end_block=end_block,
                )
            ]
        if method == Method.EVENT_LOGS:
            return [self._build_log_filter(params)]
        if method == Method.PROXY_ETH_CALL:
            call_object: dict[str, Any] = {}
            tag: Any = 'latest'
            for public, wire in spec.param_map.items():
                if wire == 'tag':
                    tag = _POSITIONAL_ENCODERS['tag'](params, public)
                else:  # 'to' / 'data': members of eth_call's single call object
                    call_object[wire] = params[public]
            return [call_object, tag]
        raise ValueError(
            f'Method {method} has no NodeReal object-param mapping'
        )  # pragma: no cover

    def _build_log_filter(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build the ``eth_getLogs`` filter object from the EVENT_LOGS declaration."""
        spec = self._spec_for(Method.EVENT_LOGS)
        from_block = _param(params, *_declared_sources(spec, 'fromBlock'), default=0)
        from_block_hex = from_block if isinstance(from_block, str) else hex(int(from_block))
        to_block = _param(params, *_declared_sources(spec, 'toBlock'), default='latest')
        to_block_hex = to_block if isinstance(to_block, str) else hex(int(to_block))
        log_filter: dict[str, Any] = {'fromBlock': from_block_hex, 'toBlock': to_block_hex}
        address = _param(params, *_declared_sources(spec, 'address'))
        if address:
            log_filter['address'] = address
        topics = [
            _param(params, *_declared_sources(spec, wire_name))
            for wire_name in ('topic0', 'topic1', 'topic2', 'topic3')
            if _declared_sources(spec, wire_name)
        ]
        while topics and topics[-1] is None:
            topics.pop()
        if topics:
            log_filter['topics'] = topics
        return log_filter

    # ------------------------------------------------------------------
    # Scanner port
    # ------------------------------------------------------------------

    def _error_context(self, method: Method) -> str:
        return f'NodeReal unexpected error for {method.name}'

    async def _perform_request(
        self,
        spec: EndpointSpec,
        method: Method,
        params: dict[str, Any],
    ) -> Any:
        """Provider dialect: JSON-RPC envelopes and the contract REST.

        The public→wire mapping IS declared in ``SPECS`` (``param_style`` +
        ``param_map`` + ``wire_method``, executed by the builders below); what
        no spec can express is the transport — JSON-RPC envelopes with the API
        key in the URL path. This override replaces the default transport
        dispatch while the error ladder and the missing-client guard stay on
        the base :meth:`Scanner.call`. The spec parser still applies to the
        raw JSON-RPC/REST payload, followed by the client-side token-contract
        filter for transfer methods (the ONE application on the ``call()``
        path; the ``fetch_page`` window walk applies it at its own parse site).
        """
        if method in self._REST_METHODS:
            address = str(params[_declared_sources(spec, 'address')[0]])
            action = 'getabi' if method == Method.CONTRACT_ABI else 'getsourcecode'
            raw_response = await self._rest_contract(action, address)
        else:
            if method in self._TRANSFER_METHODS:
                # Single-page semantics: without explicit bounds, serve the
                # most recent window; with start_block, the window at start.
                tip, window = await self._resolve_window(spec, params)
                params = dict(params)
                params[_TIP_CURSOR] = tip
                if window is not None and params.get(_WINDOW_CURSOR) is None:
                    params[_WINDOW_CURSOR] = [window[0], window[1]]
            rpc_params = self._build_rpc_params(method, params)
            raw_response = await self._rpc(self._wire_method(spec), rpc_params)
        result = spec.parse_response(raw_response)
        if method in self._TRANSFER_METHODS and isinstance(result, list):
            return _filter_transfer_items(spec, result, params)
        return result

    def _wire_method(self, spec: EndpointSpec) -> str:
        """The spec's declared JSON-RPC wire method.

        Every rpc-dialect spec declares one (enforced by the SPECS sweep in
        ``tests/test_nodereal.py``); ``None`` here would mean a query-style
        spec reached an RPC transport, which the REST branch above makes
        unreachable.
        """
        if spec.wire_method is None:  # pragma: no cover
            raise ChainscanDataError(f'{spec} declares no JSON-RPC wire method')
        return spec.wire_method

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
        - token holder list (``TOKEN_HOLDERS``): ``{'pageKey': str}`` while
          the response carries a non-empty ``pageKey``; ``None`` ends
          pagination. Opaque cursor, no page number and no block range —
          ``page``/``offset``/``sort`` page controls are inertly ignored
          except ``offset``, which is read once as the (100-capped) page
          size and re-clamped identically on every page.
        - everything else: single page, ``None``.

        The request runs under the shared error ladder (the ``call()`` path
        gets it from :meth:`Scanner.call`), so the exceptions-through-the-
        ladder contract of :meth:`Scanner.fetch_page` holds on every branch:
        every ``Chainscan*`` and capability error propagates unchanged,
        anything unexpected is masked as a non-retryable
        :class:`ChainscanNetworkError`.
        """
        self._spec_for(method)
        # Missing-client guard before the ladder: a missing Network is a
        # programming error (RuntimeError), never a network failure.
        self._require_network_client()

        with translate_unexpected_errors(self._error_context(method)):
            if method in self._TRANSFER_METHODS:
                return await self._fetch_transfer_page(method, params)
            if method in self._HOLDINGS_METHODS:
                return await self._fetch_holdings_page(method, params)
            if method in self._HOLDER_METHODS:
                return await self._fetch_holder_page(params)
            result = await self.call(method, **params)
            return Scanner._coerce_items(result), None

    async def _resolve_tip(self) -> int:
        """Current chain tip via ``eth_blockNumber`` (hex → int)."""
        return _parse_hex_int(await self._rpc('eth_blockNumber', []))

    async def _resolve_window(
        self,
        spec: EndpointSpec,
        params: dict[str, Any],
    ) -> tuple[int, tuple[int, int] | None]:
        """Resolve the chain tip and the current transfer window.

        Shared by :meth:`call` (single-page semantics) and
        :meth:`_fetch_transfer_page` (window-walking pagination); both used
        to carry their own copy of this resolution.

        Tip precedence:

        1. an ``int`` ``__nr_tip`` already in params (a previous page's
           resolved tip riding along);
        2. a window cursor without its tip (defensive: every cursor carries
           the tip — resolve it again if it was lost);
        3. an explicit bounded end (the public names declared to feed the
           wire's ``toBlock``; ``MAX_BLOCK_NUMBER`` is the streaming
           iterators' "unbounded" sentinel, so only a *bounded* end wins);
        4. the live chain tip via ``eth_blockNumber``.

        Window: the ``__nr_window`` cursor parsed to ints, else the window
        rooted at the declared ``fromBlock`` sources — or ``None`` when no
        start is known (the caller decides what that means: ``call()`` leaves
        the wire filter on most-recent-window semantics,
        ``_fetch_transfer_page`` roots the walk at block 0).
        """
        raw_tip = params.get(_TIP_CURSOR)
        window = params.get(_WINDOW_CURSOR)
        tip: int
        if isinstance(raw_tip, int):
            tip = raw_tip
        elif window is not None:
            tip = await self._resolve_tip()
        else:
            requested_end = _param(params, *_declared_sources(spec, 'toBlock'))
            if isinstance(requested_end, int) and requested_end < MAX_BLOCK_NUMBER:
                tip = requested_end
            else:
                tip = await self._resolve_tip()

        if window is not None:
            return tip, (int(window[0]), int(window[1]))
        start = _param(params, *_declared_sources(spec, 'fromBlock'))
        if start is None:
            return tip, None
        start_int = _parse_hex_int(start, 0)
        return tip, (start_int, min(start_int + _TRANSFER_WINDOW - 1, tip))

    async def _fetch_transfer_page(
        self,
        method: Method,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        spec = self._spec_for(method)
        page_key = str(params.get('pageKey') or '')
        tip, window = await self._resolve_window(spec, params)
        if window is None:
            # No start block known: root the walk at block 0.
            window = (0, min(_TRANSFER_WINDOW - 1, tip))
        window_start, window_end = window

        # Call the wire method directly (window bounds live in the cursor,
        # not in wire params, so call()'s builder defaults don't apply).
        filter_ = _build_transfer_filter(
            spec,
            self.TRANSFER_CATEGORIES[method],
            params,
            window=(window_start, window_end),
            page_key=page_key,
            end_block=tip,
        )
        raw = await self._rpc(self._wire_method(spec), [filter_])
        if not isinstance(raw, dict):
            return [], None

        next_page_key = str(raw.get('pageKey') or '')
        items = _filter_transfer_items(spec, _parse_transfer_items(raw), params)

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
        raw = await self._rpc(self._wire_method(self._spec_for(method)), rpc_params)
        if not isinstance(raw, dict):
            return [], None
        total = _parse_hex_int(raw.get('totalCount'), 0)
        items = _parse_holdings(raw)
        if page * page_size >= total:
            return items, None
        return items, {'page': page + 1, 'page_size': page_size}

    async def _fetch_holder_page(
        self,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Walk ``nr_getTokenHolders`` by its opaque ``PageKey``.

        Doc: "It should be empty for the first page. If more results are
        available, a pageKey will be returned in the response."
        (https://docs.nodereal.io/reference/nr_gettokenholders). Unlike
        :meth:`_fetch_holdings_page` there is no ``totalCount``/page-number
        arithmetic — an empty response ``pageKey`` is the only end signal.
        """
        page_key = str(params.get('pageKey') or '')
        rpc_params = self._build_rpc_params(Method.TOKEN_HOLDERS, {**params, 'pageKey': page_key})
        raw = await self._rpc(self._wire_method(self._spec_for(Method.TOKEN_HOLDERS)), rpc_params)
        if not isinstance(raw, dict):
            return [], None
        items = _parse_token_holders(raw)
        next_page_key = str(raw.get('pageKey') or '')
        if not next_page_key:
            return items, None
        return items, {'pageKey': next_page_key}

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
