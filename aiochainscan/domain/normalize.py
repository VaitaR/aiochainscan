"""Per-provider field normalization into the ``domain.normalized`` models.

Field aliases are taken from real dual-provider handling already in this
repo, not from provider documentation:

- Etherscan-style keys (``blockNumber``, ``timeStamp``, ``gasUsed``,
  ``gasPrice``, ``isError``) and their BlockScout-V2-native snake_case
  counterparts (``block_number``, ``timestamp``, ``gas_used``, ``gas_price``)
  come from ``aiochainscan/mcp/tools.py::_curate_transaction`` and
  ``aiochainscan/services/analytics.py::transactions_to_dataframe``.
- The ``from``/``to`` dict-or-string address shape (BlockScout V2 nests
  ``{'hash': ...}``, Etherscan is a flat string) comes from
  ``aiochainscan/mcp/tools.py::_flat_address`` and
  ``aiochainscan/domain/contract.py`` (``_address_field`` usage in
  ``iter_transactions``/``iter_events``).
- ``logIndex``/``log_index``/``index`` and ``transactionHash``/
  ``transaction_hash`` for logs come from
  ``aiochainscan/domain/contract.py::iter_events``.
- ``topics``/``data`` on logs are read under the same key for every provider
  (``aiochainscan/decode.py::decode_log_data``, exercised by both scanners in
  ``tests/test_contract_api.py`` and ``tests/test_decode.py``).
- Token fields (``tokenSymbol``/``tokenName``/``tokenDecimals``/
  ``contractAddress`` vs. the nested ``token`` object) come from
  ``aiochainscan/mcp/tools.py::_token_fields``.

Where no such precedent exists in the repo (block header fields beyond
``number``, internal-transaction trace metadata), the field is left
unmapped: the accessor is declared but stays ``None`` for every provider.
That gap is deliberate, not an oversight, and it is called out in
``docs/V1_PLAN.md`` Track D reporting rather than papered over with a guess.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ..convert import to_datetime
from ..crypto import to_checksum_address
from .normalized import (
    Block,
    InternalTransaction,
    Log,
    TokenTransfer,
    Transaction,
    freeze_provider_data,
)


def _first(item: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None and value != '':
            return value
    return None


def _flat_address(value: Any) -> str | None:
    """Flatten a BlockScout-V2 nested address object or an Etherscan flat string."""
    if isinstance(value, dict):
        for key in ('hash', 'address_hash', 'address'):
            nested = value.get(key)
            if isinstance(nested, str):
                return nested
        return None
    return value if isinstance(value, str) and value else None


def _checksum_or_none(value: Any) -> str | None:
    flat = _flat_address(value)
    if flat is None:
        return None
    try:
        return to_checksum_address(flat)
    except ValueError:
        return flat


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value)
    try:
        return int(text, 16) if text.startswith(('0x', '0X')) else int(text)
    except ValueError:
        return None


def _wei_int(value: Any) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else 0


def _bool_or_none(value: Any) -> bool | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return value
    return str(value) == '1'


def _timestamp_or_none(value: Any) -> datetime | None:
    if value is None or value == '':
        return None
    try:
        return to_datetime(value)
    except (ValueError, TypeError):
        return None


def normalize_transaction(item: Mapping[str, Any]) -> Transaction:
    return Transaction(
        hash=item.get('hash'),
        block_number=_int_or_none(_first(item, 'blockNumber', 'block_number')),
        from_address=_checksum_or_none(item.get('from')),
        to_address=_checksum_or_none(item.get('to')),
        value_wei=_wei_int(item.get('value')),
        gas=_int_or_none(_first(item, 'gas', 'gas_limit')),
        gas_price_wei=_int_or_none(_first(item, 'gasPrice', 'gas_price')),
        gas_used=_int_or_none(_first(item, 'gasUsed', 'gas_used')),
        nonce=_int_or_none(item.get('nonce')),
        timestamp=_timestamp_or_none(_first(item, 'timeStamp', 'timestamp')),
        is_error=_bool_or_none(item.get('isError')),
        input_data=item.get('input'),
        provider_data=freeze_provider_data(item),
    )


def normalize_internal_transaction(item: Mapping[str, Any]) -> InternalTransaction:
    return InternalTransaction(
        hash=item.get('hash'),
        block_number=_int_or_none(_first(item, 'blockNumber', 'block_number')),
        from_address=_checksum_or_none(item.get('from')),
        to_address=_checksum_or_none(item.get('to')),
        contract_address=_checksum_or_none(item.get('contractAddress')),
        value_wei=_wei_int(item.get('value')),
        gas=_int_or_none(_first(item, 'gas', 'gas_limit')),
        gas_used=_int_or_none(_first(item, 'gasUsed', 'gas_used')),
        is_error=_bool_or_none(item.get('isError')),
        timestamp=_timestamp_or_none(_first(item, 'timeStamp', 'timestamp')),
        provider_data=freeze_provider_data(item),
    )


def normalize_token_transfer(item: Mapping[str, Any]) -> TokenTransfer:
    token = item.get('token')
    nested = token if isinstance(token, dict) else {}
    contract = (
        _first(item, 'contractAddress') or nested.get('address_hash') or nested.get('address')
    )
    decimals_raw = _first(item, 'tokenDecimal', 'tokenDecimals') or nested.get('decimals')
    return TokenTransfer(
        transaction_hash=item.get('hash'),
        block_number=_int_or_none(_first(item, 'blockNumber', 'block_number')),
        from_address=_checksum_or_none(item.get('from')),
        to_address=_checksum_or_none(item.get('to')),
        contract_address=_checksum_or_none(contract),
        token_symbol=_first(item, 'tokenSymbol') or nested.get('symbol'),
        token_name=_first(item, 'tokenName') or nested.get('name'),
        token_decimals=_int_or_none(decimals_raw),
        value_raw=_wei_int(item.get('value')),
        timestamp=_timestamp_or_none(_first(item, 'timeStamp', 'timestamp')),
        provider_data=freeze_provider_data(item),
    )


def normalize_log(item: Mapping[str, Any]) -> Log:
    topics_raw = item.get('topics')
    topics = tuple(topics_raw) if isinstance(topics_raw, list | tuple) else ()
    return Log(
        address=_checksum_or_none(item.get('address')),
        block_number=_int_or_none(_first(item, 'blockNumber', 'block_number')),
        transaction_hash=_first(item, 'transactionHash', 'transaction_hash'),
        log_index=_int_or_none(_first(item, 'logIndex', 'log_index', 'index')),
        topics=topics,
        data=item.get('data'),
        provider_data=freeze_provider_data(item),
    )


def normalize_block(item: Mapping[str, Any]) -> Block:
    """Normalize a block header.

    Only ``number`` has repo precedent (``tests/test_blockscout_ethereum_flow.py``
    reads ``latest_block_info['number']`` from a live BlockScout response).
    ``hash``/``timestamp``/``gas_used``/``gas_limit``/``miner`` have no
    matching fixture or dual-provider handling anywhere in this repo, so they
    stay unmapped (always ``None``) rather than guessed from API docs.
    """
    return Block(
        number=_int_or_none(item.get('number')),
        hash=None,
        timestamp=None,
        gas_used=None,
        gas_limit=None,
        miner=None,
        provider_data=freeze_provider_data(item),
    )
