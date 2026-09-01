"""Domain models and value objects.

Only pure, dependency-free data types live here. No I/O, no logging, no env access.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiochainscan.crypto import is_address, to_checksum_address


@dataclass(slots=True, frozen=True)
class Address:
    """EVM address value object with EIP-55 checksum normalization.

    Stores addresses in EIP-55 checksum format for consistency and interoperability.
    Comparison is case-insensitive to handle addresses from different sources.

    Example:
        >>> addr = Address('0xd8da6bf26964af9d7eed9e03e53415d37aa96045')
        >>> str(addr)
        '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'  # EIP-55 checksum
        >>> addr == '0xD8DA6BF26964AF9D7EED9E03E53415D37AA96045'  # Case-insensitive
        True
    """

    value: str

    def __post_init__(self) -> None:
        stripped = self.value.strip()
        if not is_address(stripped):
            raise ValueError(f'Invalid EVM address: {stripped!r}')
        # Normalize to EIP-55 checksum format
        object.__setattr__(self, 'value', to_checksum_address(stripped))

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        """Case-insensitive equality for cross-source compatibility."""
        if isinstance(other, Address):
            return self.value.lower() == other.value.lower()
        if isinstance(other, str):
            return self.value.lower() == other.lower()
        return False

    def __hash__(self) -> int:
        """Hash based on lowercase for consistent hashing with __eq__."""
        return hash(self.value.lower())


@dataclass(slots=True, frozen=True)
class TxHash:
    """Transaction hash value object.

    Stores normalized lowercase hex string with 0x prefix.
    Transaction hashes don't use EIP-55 checksums (unlike addresses).
    Comparison is case-insensitive for cross-source compatibility.
    """

    value: str

    def __post_init__(self) -> None:
        normalized: str = self.value.lower().strip()
        if not (normalized.startswith('0x') and len(normalized) == 66):
            raise ValueError('TxHash must be 0x-prefixed 64-hex string')
        object.__setattr__(self, 'value', normalized)

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        """Case-insensitive equality for cross-source compatibility."""
        if isinstance(other, TxHash):
            return self.value.lower() == other.value.lower()
        if isinstance(other, str):
            return self.value.lower() == other.lower()
        return False

    def __hash__(self) -> int:
        """Hash based on lowercase for consistent hashing with __eq__."""
        return hash(self.value.lower())


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


@dataclass(slots=True, frozen=True)
class Page[T]:
    """Typed page container for cursor-based pagination.

    Items are strongly typed via the generic parameter. The `next_cursor`
    is an opaque string that callers should treat as a black box. Its
    contents may encode REST page/offset parameters or a GraphQL endCursor.
    """

    items: list[T]
    next_cursor: str | None
