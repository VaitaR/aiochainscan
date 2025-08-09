"""Domain models and value objects.

Only pure, dependency-free data types live here. No I/O, no logging, no env access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


@dataclass(slots=True, frozen=True)
class Address:
    """EVM address value object.

    Stores a normalized, lowercase hex string with 0x prefix.
    """

    value: str

    def __post_init__(self) -> None:
        normalized: str = self.value.lower().strip()
        if not (normalized.startswith('0x') and len(normalized) == 42):
            raise ValueError('Address must be 0x-prefixed 40-hex string')
        object.__setattr__(self, 'value', normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(slots=True, frozen=True)
class TxHash:
    """Transaction hash value object."""

    value: str

    def __post_init__(self) -> None:
        normalized: str = self.value.lower().strip()
        if not (normalized.startswith('0x') and len(normalized) == 66):
            raise ValueError('TxHash must be 0x-prefixed 64-hex string')
        object.__setattr__(self, 'value', normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(slots=True, frozen=True)
class BlockNumber:
    """Block number value object (non-negative integer)."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError('BlockNumber must be non-negative')

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)


T = TypeVar('T')


@dataclass(slots=True, frozen=True)
class Page(Generic[T]):
    """Typed page container for cursor-based pagination.

    Items are strongly typed via the generic parameter. The `next_cursor`
    is an opaque string that callers should treat as a black box. Its
    contents may encode REST page/offset parameters or a GraphQL endCursor.
    """

    items: list[T]
    next_cursor: str | None
