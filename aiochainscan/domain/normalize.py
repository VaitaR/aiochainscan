"""Per-provider field normalization into the ``domain.normalized`` models.

Etherscan-style aliases (``blockNumber``, ``timeStamp``, ``gasUsed``,
``gasPrice``, ``isError``, ``tokenSymbol``/``tokenName``/``tokenDecimal``,
``contractAddress``) were first recorded in the dual-provider handling of
``aiochainscan/mcp/tools.py`` and ``aiochainscan/domain/contract.py``; this
module is now the ONE owner of that accessor vocabulary (see the provider
field dialect below), and those consumers import it from here. The aliases
are unchanged from the first Track D pass and are not re-verified here (no
Etherscan API key was used — see ``docs/V1_PLAN.md`` Track D follow-up).

BlockScout-V2-native aliases were recorded live from the keyless public
instance (``https://eth.blockscout.com`` — the same instance
``tests/test_blockscout_ethereum_flow.py`` already calls) and saved as
fixtures under ``tests/fixtures/blockscout_v2/``:

- ``block.json`` — ``GET /api/v2/blocks/{number}`` (native V2 block header).
- ``block_jsonrpc.json`` — ``eth_getBlockByNumber`` result via
  ``POST /api/eth-rpc``, the shape shared by the Etherscan-like
  ``BLOCK_BY_NUMBER`` spec (``module=proxy&action=eth_getBlockByNumber``,
  ``aiochainscan/scanners/_etherscan_like.py``) and BlockScout V1's proxy
  fallback (``aiochainscan/scanners/blockscout_v1.py``). Recorded from the
  keyless BlockScout instance, not from an Etherscan-keyed call.
- ``transaction.json`` — one confirmed (``status: "ok"``) item from
  ``GET /api/v2/blocks/{n}/transactions``.
- ``token_transfer.json`` — one item from
  ``GET /api/v2/addresses/{addr}/token-transfers``.
- ``internal_transaction.json`` — one item from
  ``GET /api/v2/addresses/{addr}/internal-transactions``.

Findings from those fixtures that overturned the first-pass extrapolation:

- ``TokenTransfer.transaction_hash``: BlockScout V2 native key is
  ``transaction_hash``, not ``hash`` (the first pass guessed ``hash`` by
  analogy with ``Transaction.hash`` — wrong; see ``token_transfer.json``).
- ``TokenTransfer`` amount is nested: ``{"total": {"value": ..., "decimals":
  ...}}``, not a top-level ``value``/``tokenDecimal`` pair (see
  ``token_transfer.json``).
- ``Transaction.nonce`` IS present on BlockScout V2 native items under the
  same key ``nonce`` (see ``transaction.json``) — the first pass wrongly
  flagged it as Etherscan-only for lack of a fixture.
- ``Transaction.is_error`` has no BlockScout V2 equivalent key: it exposes
  ``status`` (``"ok"``/other) instead of an Etherscan-style ``isError`` flag
  (see ``transaction.json``, ``status: "ok"``) — confirmed provider-absent,
  handled by falling back to ``status``/``success`` rather than staying
  hollow.
- ``InternalTransaction`` items on BlockScout V2 native have **no**
  ``hash`` key at all (only ``transaction_hash`` + ``index`` identify one
  call) and **no** ``gas_used`` key (only ``gas_limit``) — both confirmed
  provider-absent from ``internal_transaction.json``'s full key set, not
  merely unmapped.
- ``Block``: BlockScout V2 native uses ``height`` (not ``number``),
  ``gas_used``/``gas_limit`` as decimal strings, a nested
  ``miner: {"hash": ...}``, and an ISO-8601 ``timestamp``
  (``"2024-03-23T21:34:59.000000Z"``) — all confirmed present and now
  mapped (``block.json``). The JSON-RPC shape (``block_jsonrpc.json``) uses
  hex ``number``/``gasUsed``/``gasLimit``/``timestamp`` and a flat ``miner``
  string, matching standard ``eth_getBlockByNumber``.

Timestamps on BlockScout V2 native items (blocks, transactions, transfers,
internal transactions) are ISO-8601 strings, not unix seconds — handled by
``_timestamp_or_none`` before falling back to ``convert.to_datetime`` for the
Etherscan/JSON-RPC unix-or-hex shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, overload

from ..convert import _parse_flexible_int, to_datetime
from ..crypto import to_checksum_address
from .normalized import (
    Block,
    InternalTransaction,
    Log,
    TokenTransfer,
    Transaction,
    freeze_provider_data,
)

__all__ = [
    'BLOCK_NUMBER_KEYS',
    'GAS_KEYS',
    'GAS_PRICE_KEYS',
    'GAS_USED_KEYS',
    'LOG_INDEX_KEYS',
    'LOG_TRANSACTION_HASH_KEYS',
    'TIMESTAMP_KEYS',
    'TRANSACTION_HASH_KEYS',
    'first_field',
    'flat_address',
    'int_or_default',
    'normalize_block',
    'normalize_internal_transaction',
    'normalize_log',
    'normalize_token_transfer',
    'normalize_transaction',
]

# ---------------------------------------------------------------------------
# The provider field dialect — CONTEXT.md's name for the accessor vocabulary
# that reads provider-native item dicts. This module is its ONE owner: every
# provider-dict reader (the mappers below, analytics DataFrame rows,
# ``SmartContract`` field reads, MCP curation) imports these primitives and
# alias key orders instead of re-deriving emptiness rules per call site.
# ---------------------------------------------------------------------------

BLOCK_NUMBER_KEYS: tuple[str, ...] = ('blockNumber', 'block_number')
GAS_KEYS: tuple[str, ...] = ('gas', 'gas_limit')
GAS_PRICE_KEYS: tuple[str, ...] = ('gasPrice', 'gas_price')
GAS_USED_KEYS: tuple[str, ...] = ('gasUsed', 'gas_used')
TIMESTAMP_KEYS: tuple[str, ...] = ('timeStamp', 'timestamp')
#: How a log references its transaction (Etherscan ``transactionHash`` /
#: BlockScout V2 ``transaction_hash``).
LOG_TRANSACTION_HASH_KEYS: tuple[str, ...] = ('transactionHash', 'transaction_hash')
#: The item's own transaction hash (generic ``hash`` / V2 ``transaction_hash``).
TRANSACTION_HASH_KEYS: tuple[str, ...] = ('hash', 'transaction_hash')
LOG_INDEX_KEYS: tuple[str, ...] = ('logIndex', 'log_index', 'index')


def first_field(item: Mapping[str, Any], *keys: str) -> Any:
    """Alias-first lookup: the first key whose value is not ``None``/``''``.

    A falsy ``0`` is data and survives — a genesis row keeps its block number.
    """
    for key in keys:
        value = item.get(key)
        if value is not None and value != '':
            return value
    return None


def flat_address(value: Any) -> str | None:
    """Flatten a BlockScout-V2 nested address object or an Etherscan flat string."""
    if isinstance(value, dict):
        for key in ('hash', 'address_hash', 'address'):
            nested = value.get(key)
            if isinstance(nested, str):
                return nested
        return None
    return value if isinstance(value, str) and value else None


def _checksum_or_none(value: Any) -> str | None:
    flat = flat_address(value)
    if flat is None:
        return None
    try:
        return to_checksum_address(flat)
    except ValueError:
        return flat


@overload
def int_or_default(value: Any, default: int) -> int: ...


@overload
def int_or_default(value: Any, default: None = None) -> int | None: ...


def int_or_default(value: Any, default: int | None = None) -> int | None:
    """Hex-or-decimal int coercion with a caller-supplied default.

    ``int`` passes, decimal strings and ``0x``-hex strings parse; ``bool``
    (never ``True`` -> ``1``) and unparseable values yield ``default``. The
    hex-or-decimal parse itself is ``convert._parse_flexible_int`` (the one
    owner of that rule) — this wrapper only adds the ``bool`` guard and
    turns its ``ValueError`` into ``default`` instead of raising. Signed hex
    (``'-0x10'``) therefore parses here too, unlike the pre-fold version.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int | str):
        try:
            return _parse_flexible_int(value, 'integer')
        except ValueError:
            return default
    return default


def _wei_int(value: Any) -> int:
    return int_or_default(value, default=0)


def _bool_or_none(value: Any) -> bool | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return value
    return str(value) == '1'


def _timestamp_or_none(value: Any) -> datetime | None:
    """Parse either an Etherscan/JSON-RPC unix-seconds scalar or a
    BlockScout-V2-native ISO-8601 string (``tests/fixtures/blockscout_v2/*.json``)."""
    if value is None or value == '':
        return None
    if isinstance(value, str) and 'T' in value:
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    try:
        return to_datetime(value)
    except (ValueError, TypeError):
        return None


def _is_error(item: Mapping[str, Any]) -> bool | None:
    """Etherscan's ``isError`` flag; BlockScout V2 native has no such key and
    exposes ``status``/``success`` instead (confirmed via
    ``tests/fixtures/blockscout_v2/transaction.json``,
    ``internal_transaction.json`` — never both present)."""
    if 'isError' in item:
        return _bool_or_none(item.get('isError'))
    if 'success' in item and item.get('success') is not None:
        return not bool(item['success'])
    status = item.get('status')
    if isinstance(status, str) and status:
        return status.lower() != 'ok'
    return None


def _contract_address(item: Mapping[str, Any]) -> str | None:
    """Etherscan's flat ``contractAddress``; BlockScout V2 native nests the
    created contract under ``created_contract`` (confirmed via
    ``tests/fixtures/blockscout_v2/internal_transaction.json``, ``null`` for
    a non-creation call)."""
    value = item.get('contractAddress')
    if value is None:
        value = item.get('created_contract')
    return _checksum_or_none(value)


def normalize_transaction(item: Mapping[str, Any]) -> Transaction:
    return Transaction(
        hash=item.get('hash'),
        block_number=int_or_default(first_field(item, *BLOCK_NUMBER_KEYS)),
        from_address=_checksum_or_none(item.get('from')),
        to_address=_checksum_or_none(item.get('to')),
        value_wei=_wei_int(item.get('value')),
        gas=int_or_default(first_field(item, *GAS_KEYS)),
        gas_price_wei=int_or_default(first_field(item, *GAS_PRICE_KEYS)),
        gas_used=int_or_default(first_field(item, *GAS_USED_KEYS)),
        nonce=int_or_default(item.get('nonce')),
        timestamp=_timestamp_or_none(first_field(item, *TIMESTAMP_KEYS)),
        is_error=_is_error(item),
        input_data=first_field(item, 'input', 'raw_input'),
        provider_data=freeze_provider_data(item),
    )


def normalize_internal_transaction(item: Mapping[str, Any]) -> InternalTransaction:
    return InternalTransaction(
        hash=item.get('hash'),
        transaction_hash=item.get('transaction_hash'),
        call_index=int_or_default(item.get('index')),
        block_number=int_or_default(first_field(item, *BLOCK_NUMBER_KEYS)),
        from_address=_checksum_or_none(item.get('from')),
        to_address=_checksum_or_none(item.get('to')),
        contract_address=_contract_address(item),
        value_wei=_wei_int(item.get('value')),
        gas=int_or_default(first_field(item, *GAS_KEYS)),
        gas_used=int_or_default(first_field(item, *GAS_USED_KEYS)),
        is_error=_is_error(item),
        timestamp=_timestamp_or_none(first_field(item, *TIMESTAMP_KEYS)),
        provider_data=freeze_provider_data(item),
    )


def normalize_token_transfer(item: Mapping[str, Any]) -> TokenTransfer:
    token = item.get('token')
    nested_token = token if isinstance(token, dict) else {}
    total = item.get('total')
    nested_total = total if isinstance(total, dict) else {}

    contract = (
        first_field(item, 'contractAddress')
        or nested_token.get('address_hash')
        or nested_token.get('address')
    )
    decimals_raw = first_field(item, 'tokenDecimal', 'tokenDecimals') or nested_token.get(
        'decimals'
    )
    value_raw = first_field(item, 'value') or nested_total.get('value')

    return TokenTransfer(
        transaction_hash=first_field(item, *TRANSACTION_HASH_KEYS),
        block_number=int_or_default(first_field(item, *BLOCK_NUMBER_KEYS)),
        from_address=_checksum_or_none(item.get('from')),
        to_address=_checksum_or_none(item.get('to')),
        contract_address=_checksum_or_none(contract),
        token_symbol=first_field(item, 'tokenSymbol') or nested_token.get('symbol'),
        token_name=first_field(item, 'tokenName') or nested_token.get('name'),
        token_decimals=int_or_default(decimals_raw),
        value_raw=_wei_int(value_raw),
        timestamp=_timestamp_or_none(first_field(item, *TIMESTAMP_KEYS)),
        provider_data=freeze_provider_data(item),
    )


def normalize_log(item: Mapping[str, Any]) -> Log:
    topics_raw = item.get('topics')
    topics = tuple(topics_raw) if isinstance(topics_raw, list | tuple) else ()
    return Log(
        address=_checksum_or_none(item.get('address')),
        block_number=int_or_default(first_field(item, *BLOCK_NUMBER_KEYS)),
        transaction_hash=first_field(item, *LOG_TRANSACTION_HASH_KEYS),
        log_index=int_or_default(first_field(item, *LOG_INDEX_KEYS)),
        topics=topics,
        data=item.get('data'),
        provider_data=freeze_provider_data(item),
    )


def normalize_block(item: Mapping[str, Any]) -> Block:
    """Normalize a block header.

    Handles both recorded shapes (see module docstring): BlockScout-V2-native
    (``height``, decimal-string ``gas_used``/``gas_limit``, nested ``miner``,
    ISO-8601 ``timestamp``) and the JSON-RPC ``eth_getBlockByNumber`` result
    used by the Etherscan-like ``BLOCK_BY_NUMBER`` spec and BlockScout V1's
    proxy fallback (hex ``number``/``gasUsed``/``gasLimit``/``timestamp``,
    flat ``miner`` string). Both are fixture-confirmed; no field here is a
    guess from provider documentation.
    """
    return Block(
        number=int_or_default(first_field(item, 'number', 'height')),
        hash=item.get('hash'),
        timestamp=_timestamp_or_none(item.get('timestamp')),
        gas_used=int_or_default(first_field(item, *GAS_USED_KEYS)),
        gas_limit=int_or_default(first_field(item, 'gasLimit', 'gas_limit')),
        miner=_checksum_or_none(item.get('miner')),
        difficulty=int_or_default(item.get('difficulty')),
        provider_data=freeze_provider_data(item),
    )
