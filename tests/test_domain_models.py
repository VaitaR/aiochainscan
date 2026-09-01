"""Tests for domain models with EIP-55 checksum and case-insensitive equality.

These tests verify:
1. Address uses EIP-55 checksum normalization
2. Address/TxHash have case-insensitive equality
3. Invalid addresses are rejected with proper validation
"""

import pytest

from aiochainscan.domain.models import Address, BlockNumber, Page, TxHash


class TestAddress:
    """Test Address value object with EIP-55 checksum."""

    # Known addresses with their EIP-55 checksums
    VITALIK_LOWER = '0xd8da6bf26964af9d7eed9e03e53415d37aa96045'
    VITALIK_UPPER = '0xD8DA6BF26964AF9D7EED9E03E53415D37AA96045'
    VITALIK_CHECKSUM = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    USDT_LOWER = '0xdac17f958d2ee523a2206206994597c13d831ec7'
    USDT_CHECKSUM = '0xdAC17F958D2ee523a2206206994597C13D831ec7'

    def test_normalizes_to_eip55_checksum(self):
        """Address should normalize to EIP-55 checksum format."""
        addr = Address(self.VITALIK_LOWER)
        assert addr.value == self.VITALIK_CHECKSUM

    def test_accepts_uppercase_input(self):
        """Address should accept uppercase and normalize to checksum."""
        addr = Address(self.VITALIK_UPPER)
        assert addr.value == self.VITALIK_CHECKSUM

    def test_accepts_checksum_input(self):
        """Address should accept valid checksum addresses."""
        addr = Address(self.VITALIK_CHECKSUM)
        assert addr.value == self.VITALIK_CHECKSUM

    def test_strips_whitespace(self):
        """Address should strip leading/trailing whitespace."""
        addr = Address(f'  {self.VITALIK_LOWER}  ')
        assert addr.value == self.VITALIK_CHECKSUM

    def test_case_insensitive_equality_with_address(self):
        """Two Address objects should be equal regardless of original case."""
        addr1 = Address(self.VITALIK_LOWER)
        addr2 = Address(self.VITALIK_UPPER)
        assert addr1 == addr2

    def test_case_insensitive_equality_with_string(self):
        """Address should be equal to string regardless of case."""
        addr = Address(self.VITALIK_CHECKSUM)
        assert addr == self.VITALIK_LOWER
        assert addr == self.VITALIK_UPPER
        assert addr == self.VITALIK_CHECKSUM

    def test_hash_consistent_with_equality(self):
        """Equal addresses should have equal hashes (required for dict/set)."""
        addr1 = Address(self.VITALIK_LOWER)
        addr2 = Address(self.VITALIK_UPPER)
        assert hash(addr1) == hash(addr2)

        # Should work in sets
        addr_set = {addr1, addr2}
        assert len(addr_set) == 1

    def test_usable_as_dict_key(self):
        """Address should be usable as dictionary key."""
        addr1 = Address(self.VITALIK_LOWER)
        addr2 = Address(self.VITALIK_UPPER)

        d = {addr1: 'vitalik'}
        assert d[addr2] == 'vitalik'

    def test_str_returns_checksum(self):
        """str(Address) should return EIP-55 checksum."""
        addr = Address(self.VITALIK_LOWER)
        assert str(addr) == self.VITALIK_CHECKSUM

    def test_rejects_invalid_address_short(self):
        """Should reject addresses that are too short."""
        with pytest.raises(ValueError, match='Invalid EVM address'):
            Address('0x1234')

    def test_rejects_invalid_address_long(self):
        """Should reject addresses that are too long."""
        with pytest.raises(ValueError, match='Invalid EVM address'):
            Address('0x' + 'a' * 50)

    def test_accepts_address_without_prefix(self):
        """eth_utils is lenient and auto-adds 0x prefix."""
        addr = Address('d8da6bf26964af9d7eed9e03e53415d37aa96045')
        assert addr.value == self.VITALIK_CHECKSUM

    def test_rejects_invalid_hex_characters(self):
        """Should reject addresses with invalid hex characters."""
        with pytest.raises(ValueError, match='Invalid EVM address'):
            Address('0xg8da6bf26964af9d7eed9e03e53415d37aa96045')

    def test_rejects_empty_string(self):
        """Should reject empty string."""
        with pytest.raises(ValueError, match='Invalid EVM address'):
            Address('')

    def test_rejects_only_whitespace(self):
        """Should reject string with only whitespace."""
        with pytest.raises(ValueError, match='Invalid EVM address'):
            Address('   ')

    def test_multiple_known_checksums(self):
        """Verify EIP-55 checksum for multiple known addresses."""
        usdt = Address(self.USDT_LOWER)
        assert usdt.value == self.USDT_CHECKSUM

    def test_inequality_with_different_address(self):
        """Different addresses should not be equal."""
        addr1 = Address(self.VITALIK_LOWER)
        addr2 = Address(self.USDT_LOWER)
        assert addr1 != addr2

    def test_inequality_with_non_address_types(self):
        """Address should not equal non-address types."""
        addr = Address(self.VITALIK_CHECKSUM)
        assert addr != 42
        assert addr is not None
        assert addr != []


class TestTxHash:
    """Test TxHash value object with case-insensitive equality."""

    SAMPLE_HASH_LOWER = '0x' + 'a' * 64
    SAMPLE_HASH_UPPER = '0x' + 'A' * 64
    SAMPLE_HASH_MIXED = '0x' + 'aA' * 32

    def test_normalizes_to_lowercase(self):
        """TxHash should normalize to lowercase."""
        h = TxHash(self.SAMPLE_HASH_UPPER)
        assert h.value == self.SAMPLE_HASH_LOWER

    def test_case_insensitive_equality_with_txhash(self):
        """Two TxHash objects should be equal regardless of original case."""
        h1 = TxHash(self.SAMPLE_HASH_LOWER)
        h2 = TxHash(self.SAMPLE_HASH_UPPER)
        assert h1 == h2

    def test_case_insensitive_equality_with_string(self):
        """TxHash should be equal to string regardless of case."""
        h = TxHash(self.SAMPLE_HASH_LOWER)
        assert h == self.SAMPLE_HASH_UPPER
        assert h == self.SAMPLE_HASH_MIXED

    def test_hash_consistent_with_equality(self):
        """Equal TxHashes should have equal hashes."""
        h1 = TxHash(self.SAMPLE_HASH_LOWER)
        h2 = TxHash(self.SAMPLE_HASH_UPPER)
        assert hash(h1) == hash(h2)

    def test_usable_as_dict_key(self):
        """TxHash should be usable as dictionary key."""
        h1 = TxHash(self.SAMPLE_HASH_LOWER)
        h2 = TxHash(self.SAMPLE_HASH_UPPER)

        d = {h1: 'tx1'}
        assert d[h2] == 'tx1'

    def test_str_returns_lowercase(self):
        """str(TxHash) should return lowercase."""
        h = TxHash(self.SAMPLE_HASH_UPPER)
        assert str(h) == self.SAMPLE_HASH_LOWER

    def test_rejects_invalid_hash_short(self):
        """Should reject hashes that are too short."""
        with pytest.raises(ValueError, match='TxHash must be 0x-prefixed 64-hex string'):
            TxHash('0x' + 'a' * 32)

    def test_rejects_invalid_hash_long(self):
        """Should reject hashes that are too long."""
        with pytest.raises(ValueError, match='TxHash must be 0x-prefixed 64-hex string'):
            TxHash('0x' + 'a' * 70)

    def test_rejects_invalid_hash_no_prefix(self):
        """Should reject hashes without 0x prefix."""
        with pytest.raises(ValueError, match='TxHash must be 0x-prefixed 64-hex string'):
            TxHash('a' * 64)

    def test_rejects_non_hex_characters(self):
        """Should reject correctly sized hashes containing non-hex characters."""
        with pytest.raises(ValueError, match='TxHash must be 0x-prefixed 64-hex string'):
            TxHash('0x' + 'g' + 'a' * 63)


class TestBlockNumber:
    """Test BlockNumber value object."""

    def test_accepts_zero(self):
        """BlockNumber should accept zero."""
        bn = BlockNumber(0)
        assert bn.value == 0
        assert int(bn) == 0

    def test_accepts_positive(self):
        """BlockNumber should accept positive integers."""
        bn = BlockNumber(12345678)
        assert bn.value == 12345678
        assert str(bn) == '12345678'

    def test_rejects_negative(self):
        """BlockNumber should reject negative integers."""
        with pytest.raises(ValueError, match='BlockNumber must be non-negative'):
            BlockNumber(-1)


class TestPage:
    """Test generic Page container."""

    def test_page_with_items_and_cursor(self):
        """Page should store items and next_cursor."""
        items = [{'id': 1}, {'id': 2}]
        page = Page(items=items, next_cursor='cursor123')

        assert page.items == items
        assert page.next_cursor == 'cursor123'

    def test_page_with_none_cursor(self):
        """Page should accept None cursor for last page."""
        items = [{'id': 1}]
        page = Page(items=items, next_cursor=None)

        assert page.items == items
        assert page.next_cursor is None

    def test_page_is_frozen(self):
        """Page should be immutable (frozen dataclass)."""
        page = Page(items=[1, 2, 3], next_cursor='next')

        with pytest.raises(AttributeError):
            page.items = []
