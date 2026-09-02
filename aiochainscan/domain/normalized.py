"""Normalized, provider-agnostic domain models.

Frozen slotted dataclasses over the raw provider dicts returned by
``ChainscanClient``. Additive only: nothing here changes what any existing
method returns — these are new accessors, see ``domain/normalize.py``.

Every model carries ``provider_data`` with the untouched provider response,
so a field this layer does not know about is never lost. A field mapped from
only one provider is ``None`` on the other — never invented, never defaulted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any


@dataclass(slots=True, frozen=True)
class Transaction:
    hash: str | None
    block_number: int | None
    from_address: str | None
    to_address: str | None
    value_wei: int
    gas: int | None
    gas_price_wei: int | None
    gas_used: int | None
    nonce: int | None
    timestamp: datetime | None
    is_error: bool | None
    input_data: str | None
    provider_data: Mapping[str, Any]


@dataclass(slots=True, frozen=True)
class TokenTransfer:
    transaction_hash: str | None
    block_number: int | None
    from_address: str | None
    to_address: str | None
    contract_address: str | None
    token_symbol: str | None
    token_name: str | None
    token_decimals: int | None
    value_raw: int
    timestamp: datetime | None
    provider_data: Mapping[str, Any]


@dataclass(slots=True, frozen=True)
class InternalTransaction:
    hash: str | None
    block_number: int | None
    from_address: str | None
    to_address: str | None
    contract_address: str | None
    value_wei: int
    gas: int | None
    gas_used: int | None
    is_error: bool | None
    timestamp: datetime | None
    provider_data: Mapping[str, Any]


@dataclass(slots=True, frozen=True)
class Log:
    address: str | None
    block_number: int | None
    transaction_hash: str | None
    log_index: int | None
    topics: tuple[str, ...]
    data: str | None
    provider_data: Mapping[str, Any]


@dataclass(slots=True, frozen=True)
class Block:
    number: int | None
    hash: str | None
    timestamp: datetime | None
    gas_used: int | None
    gas_limit: int | None
    miner: str | None
    provider_data: Mapping[str, Any]


def freeze_provider_data(item: Mapping[str, Any]) -> Mapping[str, Any]:
    """Wrap a raw provider item as a read-only ``provider_data`` payload."""
    return MappingProxyType(dict(item))
