"""Agent-facing MCP tools as plain ``client -> ToolResponse`` functions.

Every tool is a read-only async function over a :class:`ChainscanClient`, so
the whole agent surface is testable offline with stub clients and free of any
``mcp`` import (the FastMCP wiring lives in :mod:`aiochainscan.mcp.server`).

House patterns (mirroring the Blockscout MCP reference, adapted to our
multi-scanner client):

- **Envelope contract**: structured ``data`` + ``notes`` (limits, caveats,
  partial failures) + ``instructions`` (bridges to the next tool) +
  ``content_text`` (compact summary).
- **Opaque cursors**: paginated tools wrap the scanner ``fetch_page`` cursor
  in a tool-bound, key-whitelisted Base64URL token (see
  :mod:`aiochainscan.mcp.cursors`) and return a ready-to-use ``next_call``.
- **Curation**: fixed item caps per response, curated field sets, long
  strings flagged-and-truncated, raw input dropped once decoded.
- **Honest degradation**: unsupported methods and best-effort sub-calls land
  in ``notes`` instead of crashing the tool.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import orjson

from ..chain_registry import list_supported_chains
from ..core.method import Method
from ..decode import decode_transaction_input
from ..domain.models import Address
from ..exceptions import ChainscanClientError
from .abi_codec import canonical_signature, decode_arguments, encode_arguments, selector
from .cursors import decode_tool_cursor, encode_cursor
from .envelope import (
    NextCall,
    Pagination,
    ToolResponse,
    build_tool_response,
    clamp_page_size,
    format_units,
    truncate_long_strings,
)

if TYPE_CHECKING:
    from ..core.client import ChainscanClient

__all__ = [
    'ClientPool',
    'DEFAULT_SCANNER_ENV',
    'DEFAULT_SCANNER',
    'get_address_overview',
    'get_contract_abi',
    'get_token_holders',
    'get_token_info',
    'get_token_portfolio',
    'get_top_token_holders',
    'get_transaction_info',
    'get_transactions',
    'get_wallet_balance',
    'list_chains',
    'read_contract',
    'resolve_default_scanner',
    'resolve_ens',
]

DEFAULT_SCANNER = 'blockscout'
"""Keyless default scanner (full Etherscan-like surface, no API key)."""

DEFAULT_SCANNER_ENV = 'AIOCHAINSCAN_MCP_SCANNER'
"""Environment override for the default MCP scanner."""

_OVERVIEW_TX_LIMIT = 5
_PORTFOLIO_TOKEN_LIMIT = 20
_NFT_COLLECTION_LIMIT = 10
_ABI_SIGNATURE_LIMIT = 100
_FUNCTION_NAME_LIMIT = 60

_SCANNER_HINTS: dict[Method, str] = {
    Method.TOKEN_HOLDERS: "scanners that serve it: 'etherscan' (needs ETHERSCAN_KEY) or 'blockscout_v2'",
    Method.TOKEN_TOP_HOLDERS: "only 'etherscan' serves it (needs ETHERSCAN_KEY)",
    Method.TOKEN_HOLDER_COUNT: "scanners that serve it: 'etherscan' or 'blockscout_v2'",
    Method.TX_BY_HASH: "scanners that serve it: 'blockscout' (default), 'etherscan' or 'nodereal'",
    Method.CONTRACT_ABI: "all built-in scanners serve it except 'nodereal'",
}


def resolve_default_scanner() -> str:
    """Default MCP scanner: ``AIOCHAINSCAN_MCP_SCANNER`` env or blockscout v1."""
    return os.environ.get(DEFAULT_SCANNER_ENV, DEFAULT_SCANNER)


# ---------------------------------------------------------------------------
# Client lifecycle
# ---------------------------------------------------------------------------

ClientFactory = Callable[[str, str], 'ChainscanClient']


class ClientPool:
    """Cache of live clients keyed by ``(scanner, network)``.

    Unlike per-call clients, the pool keeps one connection pool per target
    for the lifetime of the MCP server process (stdio servers are long
    lived). ``aclose_all`` releases everything on shutdown and in tests.
    """

    def __init__(self, factory: ClientFactory | None = None) -> None:
        if factory is None:
            from ..core.client import ChainscanClient

            def default_factory(scanner: str, network: str) -> ChainscanClient:
                return ChainscanClient.from_config(scanner, network)

            factory = default_factory
        self._factory = factory
        self._clients: dict[tuple[str, str], ChainscanClient] = {}

    def get(self, scanner: str | None, network: str) -> ChainscanClient:
        """Return the cached client for the target, creating it on first use."""
        resolved = scanner or resolve_default_scanner()
        key = (resolved, network)
        if key not in self._clients:
            self._clients[key] = self._factory(resolved, network)
        return self._clients[key]

    async def aclose_all(self) -> None:
        """Close every pooled client and drop the cache."""
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            await client.close()


# ---------------------------------------------------------------------------
# Curation helpers
# ---------------------------------------------------------------------------


def _flat_address(value: Any) -> str:
    """Flatten explorer address scalars/objects into a hash string."""
    if isinstance(value, dict):
        for key in ('hash', 'address_hash', 'address'):
            nested = value.get(key)
            if isinstance(nested, str):
                return nested
        return ''
    return value if isinstance(value, str) else ''


def _int_field(value: Any, default: int = 0) -> int:
    """Read decimal/hex explorer scalars as int."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value:
        try:
            return int(value, 16) if value.startswith(('0x', '0X')) else int(value)
        except ValueError:
            return default
    return default


def _str_field(value: Any) -> str:
    return value if isinstance(value, str) else ''


def _checksum(value: str) -> str:
    """Best-effort EIP-55 checksum; unparseable values pass through."""
    from ..crypto import to_checksum_address

    try:
        return to_checksum_address(value)
    except ValueError:
        return value


def _wei_field(value: Any) -> str:
    """Normalize a Wei-scale amount (decimal or 0x-hex explorer scalar) to a decimal string."""
    if value is None or value == '':
        return '0'
    if isinstance(value, int):
        return str(value)
    text = str(value)
    try:
        return str(int(text, 16)) if text.startswith(('0x', '0X')) else str(int(text))
    except ValueError:
        return text


def _curate_transaction(item: dict[str, Any], currency: str) -> dict[str, Any]:
    """Project one transaction onto the curated field set."""
    value_wei = _wei_field(item.get('value'))
    method_id = _str_field(item.get('input'))[:10]
    return {
        'hash': item.get('hash'),
        'from': _checksum(_flat_address(item.get('from'))),
        'to': _checksum(_flat_address(item.get('to'))),
        'value_wei': value_wei,
        'value': f'{format_units(value_wei, 18)} {currency}',
        'block_number': _int_field(item.get('blockNumber', item.get('block_number'))),
        'timestamp': item.get('timeStamp', item.get('timestamp')),
        'is_error': item.get('isError'),
        'method_id': method_id if method_id not in ('', '0x') else None,
    }


def _nested_dict(item: dict[str, Any], key: str) -> dict[str, Any]:
    """Read an explorer object field as a dict ({} when missing/malformed)."""
    value = item.get(key)
    return value if isinstance(value, dict) else {}


def _token_fields(item: dict[str, Any]) -> dict[str, Any]:
    """Unify Etherscan-shaped and BlockScout-V2-shaped token holdings."""
    nested = _nested_dict(item, 'token')
    contract = (
        item.get('contractAddress')
        or nested.get('address_hash')
        or nested.get('address')
        or item.get('address')
    )
    symbol = item.get('tokenSymbol') or nested.get('symbol')
    name = item.get('tokenName') or nested.get('name')
    raw_decimals = item.get('tokenDecimals', nested.get('decimals'))
    try:
        decimals: int | None = int(raw_decimals) if raw_decimals is not None else None
    except (TypeError, ValueError):
        decimals = None
    balance_raw = str(item.get('balance') or item.get('tokenBalance') or item.get('value') or '0')
    return {
        'contract_address': _checksum(_str_field(contract)),
        'symbol': symbol,
        'name': name,
        'decimals': decimals,
        'balance_raw': balance_raw,
        'balance': format_units(balance_raw, decimals) if decimals is not None else balance_raw,
    }


def _nft_collection(item: dict[str, Any]) -> dict[str, Any]:
    """Curate one NFT collection holding."""
    nested = _nested_dict(item, 'token')
    meta = _nested_dict(item, 'collection')
    contract = (
        meta.get('address_hash')
        or nested.get('address_hash')
        or item.get('contractAddress')
        or item.get('address')
    )
    name = meta.get('name') or nested.get('name') or item.get('tokenName')
    amount = str(item.get('value') or item.get('tokenBalance') or '0')
    return {
        'contract_address': _checksum(_str_field(contract)),
        'name': name,
        'amount': format_units(amount, 0),
    }


def _notes_from_exception(what: str, exc: BaseException) -> str:
    return f'Could not retrieve {what}: {type(exc).__name__}: {exc}'


def _unsupported_notes(scanner_name: str, method: Method) -> list[str]:
    hint = _SCANNER_HINTS.get(method, 'try another scanner')
    return [
        f'Scanner {scanner_name!r} does not expose {method.name}.',
        f'To get this data, pass a scanner that serves it — {hint}.',
    ]


def _next_call_params(
    tool_chain: str,
    scanner: str | None,
    **params: Any,
) -> dict[str, Any]:
    """Assemble the ``next_call.params`` payload (chain always, scanner only when explicit)."""
    merged: dict[str, Any] = {'chain': tool_chain, **params}
    if scanner is not None:
        merged['scanner'] = scanner
    return merged


# Scanner-cursor keys each paginated tool may merge back into request params
# (union across the scanners that can serve the tool). Anything else inside a
# cursor token — notably resource-identity params such as ``address``,
# ``contract_address``, ``module`` or ``action`` — is rejected by
# ``decode_tool_cursor``: a cursor may only advance pagination, never
# re-target the query (see ``aiochainscan.mcp.cursors`` for the model).
_TX_CURSOR_KEYS = frozenset(
    {
        'page',
        'offset',  # Etherscan-like page/offset walk
        'block_number',
        'index',
        'items_count',  # BlockScout V2 txlist cursor
        '__nr_window',
        '__nr_tip',
        'pageKey',  # NodeReal window/pageKey cursor
    }
)
_PORTFOLIO_CURSOR_KEYS = frozenset(
    {
        'page',
        'offset',  # Etherscan-like page/offset walk
        'page_size',  # NodeReal holdings cursor
        'fiat_value',
        'items_count',
        'token',
        'value',  # BlockScout V2 tokens cursor
    }
)
_HOLDERS_CURSOR_KEYS = frozenset(
    {
        'page',
        'offset',  # Etherscan-like page/offset walk
        'value',
        'address_hash',
        'items_count',  # BlockScout V2 holders cursor
    }
)


def _pagination(
    *,
    tool: str,
    items_shown: int,
    scanner_cursor: dict[str, Any] | None,
    total: int | None,
    next_params: dict[str, Any],
) -> Pagination | None:
    """Build the pagination block when more data is available."""
    if scanner_cursor is None:
        return None
    token = encode_cursor({'tool': tool, 'cursor': scanner_cursor})
    return Pagination(
        has_more=True,
        items_shown=items_shown,
        next_cursor=token,
        total=total,
        next_call=NextCall(tool=tool, params={**next_params, 'cursor': token}),
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def get_wallet_balance(client: ChainscanClient, address: str) -> ToolResponse:
    """Native-coin balance of an address (Wei + human-readable)."""
    wallet = str(Address(address))
    balance_wei = await client.get_balance(wallet)
    balance = format_units(balance_wei, 18)
    currency = client.currency
    zero = balance == '0'
    return build_tool_response(
        data={
            'address': _checksum(wallet),
            'balance_wei': str(balance_wei),
            'balance': balance,
            'currency': currency,
        },
        notes=None
        if not zero
        else [f'Address {wallet} holds no native {currency} on this chain.'],
        instructions=[
            'This is the native coin balance only — call get_token_portfolio or '
            'get_address_overview for ERC-20/NFT holdings.'
        ],
        content_text=(
            f'Balance of {wallet}: {balance} {currency} (raw Wei: {balance_wei}).'
            if not zero
            else f'Balance of {wallet}: 0 {currency} (address holds no native coin).'
        ),
    )


async def get_address_overview(client: ChainscanClient, address: str) -> ToolResponse:
    """Composite address snapshot: balance + first transactions + tokens + NFTs.

    Sub-queries run concurrently; partial failures land in ``notes`` instead
    of failing the whole call (gather with ``return_exceptions=True``).
    """
    wallet = str(Address(address))
    currency = client.currency

    balance_task = client.get_balance(wallet)
    txs_task = client.get_transactions(wallet, page=1, offset=_OVERVIEW_TX_LIMIT)
    tokens_task = client.get_token_portfolio(wallet)
    nfts_task = client.get_nft_portfolio(wallet)
    balance_r, txs_r, tokens_r, nfts_r = await asyncio.gather(
        balance_task, txs_task, tokens_task, nfts_task, return_exceptions=True
    )

    notes: list[str] = []
    if isinstance(balance_r, BaseException):
        raise balance_r

    balance_wei = str(balance_r)
    balance = format_units(balance_wei, 18)

    transactions: list[dict[str, Any]] = []
    if isinstance(txs_r, BaseException):
        notes.append(_notes_from_exception('recent transactions', txs_r))
    else:
        transactions = [_curate_transaction(tx, currency) for tx in txs_r[:_OVERVIEW_TX_LIMIT]]

    tokens: list[dict[str, Any]] = []
    if isinstance(tokens_r, BaseException):
        notes.append(_notes_from_exception('token portfolio', tokens_r))
    else:
        tokens = [_token_fields(item) for item in tokens_r[:_PORTFOLIO_TOKEN_LIMIT]]
        if len(tokens_r) > _PORTFOLIO_TOKEN_LIMIT:
            notes.append(f'Showing {_PORTFOLIO_TOKEN_LIMIT} of {len(tokens_r)} token holdings.')

    nft_collections: list[dict[str, Any]] = []
    if isinstance(nfts_r, BaseException):
        notes.append(_notes_from_exception('NFT portfolio', nfts_r))
    else:
        nft_collections = [_nft_collection(item) for item in nfts_r[:_NFT_COLLECTION_LIMIT]]
        if len(nfts_r) > _NFT_COLLECTION_LIMIT:
            notes.append(f'Showing {_NFT_COLLECTION_LIMIT} of {len(nfts_r)} NFT collections.')

    return build_tool_response(
        data={
            'address': _checksum(wallet),
            'currency': currency,
            'balance_wei': balance_wei,
            'balance': balance,
            'transactions': transactions,
            'tokens': tokens,
            'nft_collections': nft_collections,
        },
        notes=notes or None,
        instructions=[
            'Recent transactions show the newest page only — use get_transactions '
            'with pagination.next_call for full history.',
            'Token balances are raw-unit strings plus formatted values; verify '
            'decimals against get_token_info for high-stakes math.',
        ],
        content_text=(
            f'Overview of {wallet}: balance {balance} {currency}, '
            f'{len(transactions)} recent transactions, {len(tokens)} tokens, '
            f'{len(nft_collections)} NFT collections.'
        ),
    )


async def get_transactions(
    client: ChainscanClient,
    address: str,
    cursor: str | None = None,
    limit: int | None = None,
    *,
    chain: str = 'ethereum',
    scanner: str | None = None,
) -> ToolResponse:
    """One curated page of an address's transactions with an opaque cursor."""
    wallet = str(Address(address))
    if not client.supports_method(Method.ACCOUNT_TRANSACTIONS):
        return build_tool_response(
            data=None,
            notes=_unsupported_notes(client.scanner_name, Method.ACCOUNT_TRANSACTIONS),
            instructions=['list_chains shows which chains the default scanner serves.'],
            content_text=f'Cannot list transactions for {wallet}: scanner lacks the method.',
        )

    page_size = clamp_page_size(limit)
    params: dict[str, Any] = {'address': wallet, 'page': 1, 'offset': page_size}
    if cursor is not None:
        params.update(decode_tool_cursor(cursor, 'get_transactions', _TX_CURSOR_KEYS))

    items, scanner_cursor = await client.fetch_page(Method.ACCOUNT_TRANSACTIONS, params)
    transactions = [_curate_transaction(item, client.currency) for item in items[:page_size]]

    pagination = _pagination(
        tool='get_transactions',
        items_shown=len(transactions),
        scanner_cursor=scanner_cursor,
        total=None,
        next_params=_next_call_params(chain, scanner, address=address, limit=page_size),
    )
    notes: list[str] | None = None
    if not transactions:
        notes = [f'No transactions found for {wallet} on this scanner/page window.']
    return build_tool_response(
        data={
            'address': _checksum(wallet),
            'currency': client.currency,
            'total_shown': len(transactions),
            'transactions': transactions,
        },
        notes=notes,
        pagination=pagination,
        content_text=(
            f'{len(transactions)} transactions for {wallet}'
            + (' (more available).' if pagination else ' (end of data).')
        ),
    )


async def get_transaction_info(client: ChainscanClient, tx_hash: str) -> ToolResponse:
    """Transaction details with fastabi-decoded input when an ABI is available."""
    if not client.supports_method(Method.TX_BY_HASH):
        return build_tool_response(
            data=None,
            notes=_unsupported_notes(client.scanner_name, Method.TX_BY_HASH),
            content_text='Cannot fetch transaction: scanner lacks the method.',
        )

    tx = await client.get_transaction(tx_hash)
    if not tx:
        return build_tool_response(
            data=None,
            notes=[
                f'Transaction {tx_hash} not found. It may be pending, on another '
                'chain, or the hash is malformed.'
            ],
            content_text=f'Transaction {tx_hash} not found.',
        )

    notes: list[str] = []
    data: dict[str, Any] = {
        'hash': tx.get('hash', tx_hash),
        'from': _checksum(_flat_address(tx.get('from'))),
        'to': _checksum(_flat_address(tx.get('to'))),
        'block_number': _int_field(tx.get('blockNumber', tx.get('block_number'))),
        'value_wei': _wei_field(tx.get('value')),
        'nonce': _int_field(tx.get('nonce')),
        'gas': _int_field(tx.get('gas', tx.get('gas_limit'))),
        'gas_price_wei': _wei_field(tx.get('gasPrice', tx.get('gas_price'))),
    }
    data['value'] = f"{format_units(data['value_wei'], 18)} {client.currency}"

    status_task = asyncio.create_task(_best_effort_status(client, tx_hash))
    raw_input = _str_field(tx.get('input') or tx.get('raw_input'))
    decoded: dict[str, Any] | None = None
    if raw_input and raw_input != '0x' and len(raw_input) >= 10:
        decoded, decode_note = await _decode_input_best_effort(client, data['to'], raw_input)
        if decode_note:
            notes.append(decode_note)
    if decoded is not None:
        data['decoded_input'] = decoded
    elif raw_input and raw_input != '0x':
        sampled, was_truncated = truncate_long_strings(raw_input)
        data['raw_input'] = sampled
        if was_truncated:
            notes.append('raw_input was truncated to conserve context ("value_truncated": true).')

    status, status_note = await status_task
    if status_note:
        notes.append(status_note)
    if status:
        data['status'] = status

    return build_tool_response(
        data=data,
        notes=notes or None,
        instructions=[
            'Decoded input comes from the contract ABI fetched automatically; '
            'use read_contract to query contract state directly.'
        ]
        if data.get('decoded_input')
        else [
            'Input is undecoded (no verified ABI) — inspect raw_input or try '
            'read_contract if you know the function.'
        ],
        content_text=(
            f"Transaction {data['hash']}: {data['from']} -> {data['to']} "
            f"{data['value']}, block {data['block_number']}"
            + (f", function {decoded['function']}()" if decoded else '')
            + '.'
        ),
    )


async def _best_effort_status(
    client: ChainscanClient, tx_hash: str
) -> tuple[str | None, str | None]:
    if not client.supports_method(Method.TX_RECEIPT_STATUS):
        return None, None
    try:
        status = await client.get_transaction_status(tx_hash)
    except ChainscanClientError as exc:
        return None, _notes_from_exception('receipt status', exc)
    value = status.get('status') if isinstance(status, dict) else None
    if value is None:
        return None, 'Receipt status not available yet (transaction may be pending).'
    return str(value), None


async def _decode_input_best_effort(
    client: ChainscanClient, contract: str, raw_input: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Decode calldata via the explorer ABI; failures degrade to a note."""
    if not contract:
        return None, None
    if not client.supports_method(Method.CONTRACT_ABI):
        return None, 'Input decoding unavailable: scanner lacks the ABI endpoint.'
    try:
        abi_json = await client.get_contract_abi(contract)
    except ChainscanClientError as exc:
        return None, f'ABI not available ({exc}); raw input kept.'
    try:
        abi = orjson.loads(abi_json) if isinstance(abi_json, str) else abi_json
    except orjson.JSONDecodeError:
        return None, 'Contract ABI is not valid JSON; raw input kept.'
    if not isinstance(abi, list) or not abi:
        return None, 'Contract is not verified (no ABI); raw input kept.'
    decoded = decode_transaction_input({'input': raw_input}, abi)
    name = decoded.get('decoded_func')
    if not isinstance(name, str) or not name:
        return None, 'Function selector not found in the contract ABI; raw input kept.'
    args_data, _ = truncate_long_strings(decoded.get('decoded_data') or {})
    return {'function': name, 'args': args_data}, None


async def get_token_portfolio(
    client: ChainscanClient,
    address: str,
    cursor: str | None = None,
    limit: int | None = None,
    *,
    chain: str = 'ethereum',
    scanner: str | None = None,
) -> ToolResponse:
    """One curated page of ERC-20 holdings with an opaque cursor."""
    wallet = str(Address(address))
    if not client.supports_method(Method.ACCOUNT_TOKEN_PORTFOLIO):
        return build_tool_response(
            data=None,
            notes=_unsupported_notes(client.scanner_name, Method.ACCOUNT_TOKEN_PORTFOLIO),
            content_text=f'Cannot list tokens for {wallet}: scanner lacks the method.',
        )

    page_size = clamp_page_size(limit)
    params: dict[str, Any] = {'address': wallet, 'page': 1, 'offset': page_size}
    if cursor is not None:
        params.update(decode_tool_cursor(cursor, 'get_token_portfolio', _PORTFOLIO_CURSOR_KEYS))

    items, scanner_cursor = await client.fetch_page(Method.ACCOUNT_TOKEN_PORTFOLIO, params)
    tokens = [_token_fields(item) for item in items[:page_size]]
    pagination = _pagination(
        tool='get_token_portfolio',
        items_shown=len(tokens),
        scanner_cursor=scanner_cursor,
        total=None,
        next_params=_next_call_params(chain, scanner, address=address, limit=page_size),
    )
    return build_tool_response(
        data={
            'address': _checksum(wallet),
            'total_shown': len(tokens),
            'tokens': tokens,
        },
        notes=None if tokens else [f'No ERC-20 holdings found for {wallet}.'],
        pagination=pagination,
        content_text=(
            f'{len(tokens)} token holdings for {wallet}'
            + (' (more available).' if pagination else ' (end of data).')
        ),
    )


async def get_token_info(client: ChainscanClient, token_address: str) -> ToolResponse:
    """Token metadata: name/symbol/decimals, supply (raw + formatted), holders."""
    token = str(Address(token_address))
    if not client.supports_method(Method.TOKEN_INFO):
        return build_tool_response(
            data=None,
            notes=_unsupported_notes(client.scanner_name, Method.TOKEN_INFO),
            content_text=f'Cannot fetch token info for {token}: scanner lacks the method.',
        )

    info = await client.get_token_info(token)
    notes: list[str] = []
    data: dict[str, Any] = {
        'contract_address': _checksum(token),
        'name': info.get('name'),
        'symbol': info.get('symbol'),
        'decimals': _int_field(info.get('decimals'), default=18) or 18,
        'total_supply': str(info.get('totalSupply', info.get('total_supply')) or '0'),
    }
    decimals = data['decimals']
    data['total_supply_formatted'] = format_units(data['total_supply'], decimals)

    if client.supports_method(Method.TOKEN_HOLDER_COUNT):
        try:
            data['holder_count'] = await client.get_token_holder_count(token)
        except ChainscanClientError as exc:
            notes.append(_notes_from_exception('holder count', exc))
    else:
        notes.append(f'Holder count not available on scanner {client.scanner_name!r}.')

    return build_tool_response(
        data=data,
        notes=notes or None,
        instructions=[
            'Use get_token_holders / get_top_token_holders for distribution analysis '
            'and read_contract for on-chain token state.'
        ],
        content_text=(
            f"Token {data['symbol'] or token}: {data['name'] or 'unnamed'}, "
            f"decimals {data['decimals']}, total supply {data['total_supply_formatted']}."
        ),
    )


async def _token_decimals(client: ChainscanClient, token: str) -> tuple[int | None, str | None]:
    """Best-effort decimals for human-readable holder balances."""
    if not client.supports_method(Method.TOKEN_INFO):
        return None, None
    try:
        info = await client.get_token_info(token)
    except ChainscanClientError:
        return None, None
    decimals = info.get('decimals')
    try:
        return int(decimals) if decimals is not None else None, None
    except (TypeError, ValueError):
        return None, None


async def get_token_holders(
    client: ChainscanClient,
    token_address: str,
    cursor: str | None = None,
    limit: int | None = None,
    *,
    chain: str = 'ethereum',
    scanner: str | None = None,
) -> ToolResponse:
    """One curated page of token holders with balance formatting and totals."""
    token = str(Address(token_address))
    if not client.supports_method(Method.TOKEN_HOLDERS):
        return build_tool_response(
            data=None,
            notes=_unsupported_notes(client.scanner_name, Method.TOKEN_HOLDERS),
            content_text=f'Cannot list holders of {token}: scanner lacks the method.',
        )

    decimals, _ = await _token_decimals(client, token)
    total: int | None = None
    if client.supports_method(Method.TOKEN_HOLDER_COUNT):
        try:
            total = await client.get_token_holder_count(token)
        except ChainscanClientError:
            total = None

    page_size = clamp_page_size(limit)
    params: dict[str, Any] = {'contract_address': token, 'page': 1, 'offset': page_size}
    if cursor is not None:
        params.update(decode_tool_cursor(cursor, 'get_token_holders', _HOLDERS_CURSOR_KEYS))
    items, scanner_cursor = await client.fetch_page(Method.TOKEN_HOLDERS, params)

    holders = []
    for item in items[:page_size]:
        raw = str(item.get('value') or '0')
        entry: dict[str, Any] = {
            'address': _checksum(_str_field(item.get('address'))),
            'balance_raw': raw,
        }
        if decimals is not None:
            entry['balance'] = format_units(raw, decimals)
        holders.append(entry)

    symbol: str | None = None
    if client.supports_method(Method.TOKEN_INFO):
        try:
            symbol = str((await client.get_token_info(token)).get('symbol') or '') or None
        except ChainscanClientError:
            symbol = None

    data: dict[str, Any] = {
        'contract_address': _checksum(token),
        'total_shown': len(holders),
        'holders': holders,
    }
    if symbol:
        data['token_symbol'] = symbol
        for entry in holders:
            entry['token_symbol'] = symbol

    notes: list[str] = []
    if total is not None and holders:
        notes.append(f'Showing {len(holders)} of {total} holders.')
    if not holders:
        notes.append(f'No holders returned for {token} on this page.')

    pagination = _pagination(
        tool='get_token_holders',
        items_shown=len(holders),
        scanner_cursor=scanner_cursor,
        total=total,
        next_params=_next_call_params(
            chain, scanner, token_address=token_address, limit=page_size
        ),
    )
    return build_tool_response(
        data=data,
        notes=notes or None,
        pagination=pagination,
        content_text=(
            f'{len(holders)} holders of {symbol or token}'
            + (f' (of {total} total)' if total is not None else '')
            + (' (more available).' if pagination else ' (end of data).')
        ),
    )


async def get_top_token_holders(
    client: ChainscanClient,
    token_address: str,
    limit: int = 100,
) -> ToolResponse:
    """Top-N holders by balance (Etherscan PRO endpoint)."""
    token = str(Address(token_address))
    if not client.supports_method(Method.TOKEN_TOP_HOLDERS):
        return build_tool_response(
            data=None,
            notes=_unsupported_notes(client.scanner_name, Method.TOKEN_TOP_HOLDERS),
            content_text=f'Cannot list top holders of {token}: scanner lacks the method.',
        )
    if limit < 1:
        raise ValueError(f'limit must be at least 1, got {limit}')

    items = await client.get_top_token_holders(token, limit=limit)
    decimals, _ = await _token_decimals(client, token)
    holders = []
    for item in items[:limit]:
        raw = str(item.get('value') or '0')
        entry: dict[str, Any] = {
            'address': _checksum(_str_field(item.get('address'))),
            'balance_raw': raw,
        }
        if decimals is not None:
            entry['balance'] = format_units(raw, decimals)
        holders.append(entry)

    return build_tool_response(
        data={
            'contract_address': _checksum(token),
            'total_shown': len(holders),
            'holders': holders,
        },
        notes=None if holders else [f'No top holders returned for {token}.'],
        instructions=[
            'Top-holder ordering is guaranteed by the scanner endpoint; use '
            'get_token_holders for full pagination through every holder.'
        ],
        content_text=f'Top {len(holders)} holders of {token}.',
    )


async def get_contract_abi(client: ChainscanClient, address: str) -> ToolResponse:
    """Verified ABI summary: function/event signatures, not the raw ABI dump.

    The full ABI can be huge; agents get the curated signature list and use
    ``read_contract``, which auto-fetches the ABI, for actual calls.
    """
    contract = str(Address(address))
    if not client.supports_method(Method.CONTRACT_ABI):
        return build_tool_response(
            data=None,
            notes=_unsupported_notes(client.scanner_name, Method.CONTRACT_ABI),
            content_text=f'Cannot fetch ABI of {contract}: scanner lacks the method.',
        )

    try:
        abi_json = await client.get_contract_abi(contract)
    except ChainscanClientError as exc:
        return build_tool_response(
            data=None,
            notes=[
                f'No ABI for {contract}: {exc}. The contract is likely not '
                'verified on this explorer.'
            ],
            content_text=f'No verified ABI for {contract}.',
        )
    try:
        abi = orjson.loads(abi_json) if isinstance(abi_json, str) else abi_json
    except orjson.JSONDecodeError:
        abi = None
    if not isinstance(abi, list) or not abi:
        return build_tool_response(
            data=None,
            notes=[f'Contract {contract} has no verified ABI on this scanner.'],
            content_text=f'No verified ABI for {contract}.',
        )

    functions = [
        item
        for item in abi
        if isinstance(item, dict) and item.get('type') == 'function' and item.get('name')
    ]
    events = [
        item
        for item in abi
        if isinstance(item, dict) and item.get('type') == 'event' and item.get('name')
    ]
    signatures = [canonical_signature(str(fn['name']), fn.get('inputs') or []) for fn in functions]
    notes: list[str] = []
    if len(signatures) > _ABI_SIGNATURE_LIMIT:
        notes.append(f'Showing {_ABI_SIGNATURE_LIMIT} of {len(signatures)} function signatures.')
    return build_tool_response(
        data={
            'contract_address': _checksum(contract),
            'function_count': len(functions),
            'event_count': len(events),
            'functions': signatures[:_ABI_SIGNATURE_LIMIT],
        },
        notes=notes or None,
        instructions=[
            'Call read_contract with any of these function names — the ABI is '
            'fetched and applied automatically, no manual ABI input needed.'
        ],
        content_text=(
            f'{contract}: {len(functions)} functions, {len(events)} events in verified ABI.'
        ),
    )


async def read_contract(
    client: ChainscanClient,
    address: str,
    function_name: str,
    args: str = '[]',
    block: str = 'latest',
) -> ToolResponse:
    """Read contract state via auto-fetched ABI + eth_call, outputs decoded.

    ``args`` is a JSON array string; numeric strings coerce to ints, ``0x``
    hex strings pass through for bytes arguments, addresses as ``0x`` strings.
    """
    contract = str(Address(address))
    parsed_args, args_note = _parse_json_args(args)

    if not client.supports_method(Method.CONTRACT_ABI):
        return build_tool_response(
            data=None,
            notes=_unsupported_notes(client.scanner_name, Method.CONTRACT_ABI),
            content_text=f'Cannot read {contract}: scanner lacks the ABI endpoint.',
        )
    abi_note: str | None = args_note
    try:
        abi_json = await client.get_contract_abi(contract)
        abi = orjson.loads(abi_json) if isinstance(abi_json, str) else abi_json
    except (ChainscanClientError, orjson.JSONDecodeError) as exc:
        return build_tool_response(
            data=None,
            notes=[
                f'No verified ABI for {contract} ({exc}); cannot auto-encode the call.',
            ],
            content_text=f'Cannot read {function_name} on {contract}: no verified ABI.',
        )
    if not isinstance(abi, list) or not abi:
        return build_tool_response(
            data=None,
            notes=[f'Contract {contract} has no verified ABI; cannot encode the call.'],
            content_text=f'Cannot read {function_name} on {contract}: no verified ABI.',
        )

    overloads = [
        item
        for item in abi
        if isinstance(item, dict)
        and item.get('type') == 'function'
        and item.get('name') == function_name
    ]
    if not overloads:
        available = sorted(
            {
                str(item.get('name'))
                for item in abi
                if isinstance(item, dict) and item.get('type') == 'function' and item.get('name')
            }
        )
        suggestion = difflib.get_close_matches(function_name, available, n=3)
        close = f' Did you mean: {", ".join(suggestion)}?' if suggestion else ''
        return build_tool_response(
            data=None,
            notes=[
                f'Function {function_name!r} not found in the verified ABI of {contract}.'
                f'{close} Available functions: {", ".join(available[:_FUNCTION_NAME_LIMIT])}'
            ],
            content_text=f'Function {function_name} not found on {contract}.',
        )

    matches = [fn for fn in overloads if len(fn.get('inputs') or []) == len(parsed_args)]
    if not matches:
        signatures = ', '.join(
            f'{canonical_signature(function_name, fn.get("inputs") or [])} '
            f'(expects {len(fn.get("inputs") or [])} argument(s))'
            for fn in overloads
        )
        raise ValueError(
            f'{function_name}: no overload takes {len(parsed_args)} argument(s); '
            f'overloads: {signatures}'
        )
    function = matches[0]
    inputs = function.get('inputs') or []

    try:
        call_data = '0x' + (
            selector(function_name, inputs)[2:] + encode_arguments(inputs, parsed_args).hex()
        )
    except ValueError as exc:
        raise ValueError(f'cannot encode arguments for {function_name}: {exc}') from exc

    if not client.supports_method(Method.PROXY_ETH_CALL):
        return build_tool_response(
            data=None,
            notes=_unsupported_notes(client.scanner_name, Method.PROXY_ETH_CALL),
            content_text=f'Cannot read {contract}: scanner lacks the eth_call endpoint.',
        )

    notes: list[str] = []
    if abi_note:
        notes.append(abi_note)
    if len(overloads) > 1:
        notes.append(
            'Multiple overloads share this name; chosen '
            f'{canonical_signature(function_name, inputs)} by argument count.'
        )

    try:
        result_hex = await client.eth_call(to=contract, data=call_data, tag=block)
    except ChainscanClientError as exc:
        return build_tool_response(
            data=None,
            notes=[f'eth_call failed: {exc}'],
            content_text=f'Call to {function_name} on {contract} failed.',
        )

    outputs = function.get('outputs') or []
    result: dict[str, Any] | None
    if not isinstance(result_hex, str) or result_hex in ('', '0x'):
        result = None
        notes.append(
            'eth_call returned empty data — the call most likely reverted. '
            'Check arguments and the block tag.'
        )
    elif not outputs:
        result = {}
        notes.append('Function declares no outputs; raw result discarded.')
    else:
        try:
            result = decode_arguments(outputs, result_hex)
        except ValueError as exc:
            result = None
            notes.append(f'Could not decode outputs ({exc}); raw result kept.')
            notes.append(f'raw result: {result_hex}')

    return build_tool_response(
        data={
            'contract_address': _checksum(contract),
            'function': function_name,
            'signature': canonical_signature(function_name, inputs),
            'block': block,
            'args': parsed_args,
            'result': result,
        },
        notes=notes or None,
        instructions=[
            'Arguments were auto-encoded from the verified ABI — call '
            'get_contract_abi to discover other callable functions.'
        ],
        content_text=(
            f'{function_name}({", ".join(str(a) for a in parsed_args)}) on '
            f'{contract} at block {block} -> '
            + ('empty/reverted' if result is None else orjson.dumps(result).decode())
            + '.'
        ),
    )


def _parse_json_args(args: str) -> tuple[list[Any], str | None]:
    """Parse the ``args`` JSON array string with an agent-friendly error."""
    text = args.strip() or '[]'
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f'args must be a JSON array string (e.g. \'["0xabc...", 5]\'): {exc}'
        ) from exc
    if not isinstance(parsed, list):
        raise ValueError(f'args must be a JSON array, got {type(parsed).__name__}')
    note = None
    if any(isinstance(item, dict) for item in parsed):
        note = 'Object arguments are interpreted as named tuple components.'
    return parsed, note


async def resolve_ens(client: ChainscanClient, name_or_address: str) -> ToolResponse:
    """Resolve ENS in both directions: name → address, address → name."""
    value = name_or_address.strip()
    if value.startswith('0x') or '.' not in value:
        wallet = str(Address(value))  # ValueError for malformed addresses
        name = await client.lookup_address(wallet)
        data = {'address': _checksum(wallet), 'ens_name': name}
        return build_tool_response(
            data=data,
            notes=None if name else [f'No ENS name is set for {wallet}.'],
            content_text=f'{wallet} -> {name or "no ENS name"}.',
        )

    address = await client.resolve_name(value)
    data = {'name': value, 'address': _checksum(address) if address else None}
    return build_tool_response(
        data=data,
        notes=None
        if address
        else [f'{value} does not resolve. ENS resolution works for names on Ethereum mainnet.'],
        instructions=['Validate the resolved address with read_contract or get_address_overview.']
        if address
        else None,
        content_text=f'{value} -> {address or "unresolved"}.',
    )


def list_chains(query: str | None = None) -> ToolResponse:
    """Chains served by the MCP tools, filterable by name/alias/ID substring."""
    matches = []
    needle = (query or '').strip().lower()
    for chain_id, info in sorted(list_supported_chains().items()):
        name = str(info.get('name'))
        aliases = [str(alias) for alias in info.get('aliases', [])]
        if needle and needle not in (name, *aliases, str(chain_id)):
            continue
        matches.append(
            {
                'chain_id': chain_id,
                'name': name,
                'aliases': aliases,
                'blockscout': info.get('blockscout_instance'),
            }
        )
    notes = None
    if not matches:
        notes = [f'No chain matches {query!r}. Try a name, alias or numeric chain ID.']
    return build_tool_response(
        data={'chains': matches, 'count': len(matches)},
        notes=notes,
        instructions=[
            'Pass the chain name or ID to the chain parameter of any other tool. '
            'The default scanner (blockscout) needs no API key; scanner "etherscan" '
            'covers every listed chain but needs ETHERSCAN_KEY.',
        ],
        content_text=(
            f'{len(matches)} chains available' + (f' matching {query!r}' if query else '') + '.'
        ),
    )
