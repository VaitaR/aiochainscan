"""Tests for the value conversion helpers (``aiochainscan.convert``).

The contract under test mirrors the project's data-integrity rules:

- Wei/token math is ``Decimal``-exact — no ``float`` step, so 0.1 + 02-style
  artifacts are impossible, magnitudes beyond 10**30 wei stay exact and
  negative (allowance-style) amounts are valid.
- Hex-aware parsers accept the three shapes one field can take across
  Etherscan-style and JSON-RPC proxy endpoints: hex string, decimal string,
  already-converted int.
- Timestamps become timezone-aware (UTC) datetimes / ISO-8601 strings.

Invalid input (empty/None-like, fractional wei, NaN/Infinity, bare hex)
fails loudly with ``ValueError``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from aiochainscan import (
    format_ether,
    hex_to_int,
    hex_to_str,
    to_datetime,
    to_decimal_amount,
    to_iso,
    wei_to_ether,
)

# ─────────────────────────── wei / token amounts ───────────────────────────


class TestWeiToEther:
    def test_basic_conversion(self) -> None:
        assert wei_to_ether('1500000000000000000') == Decimal('1.5')

    def test_int_input(self) -> None:
        assert wei_to_ether(10**18) == Decimal('1')

    def test_zero(self) -> None:
        assert wei_to_ether('0') == Decimal('0')

    def test_exact_decimal_not_float(self) -> None:
        # The canonical float failure: 0.1 + 0.2 != 0.3 in binary floating point.
        assert wei_to_ether('100000000000000000') + wei_to_ether('200000000000000000') == Decimal(
            '0.3'
        )

    def test_sub_ether_precision_exact(self) -> None:
        assert wei_to_ether('123456789012345678') == Decimal('0.123456789012345678')

    def test_negative_allowance_style(self) -> None:
        assert wei_to_ether('-21000000000000000000') == Decimal('-21')
        assert wei_to_ether(-1500000000000000000) == Decimal('-1.5')

    def test_huge_value_exact(self) -> None:
        # 37-digit wei amount: far beyond float's exact-integer range (2**53).
        raw = '12345678901234567890123456789012345'
        assert str(wei_to_ether(raw)) == '12345678901234567.890123456789012345'

    def test_huge_power_of_ten(self) -> None:
        assert wei_to_ether('1' + '0' * 36) == Decimal(10) ** 18

    def test_non_18_decimals(self) -> None:
        # wei_to_ether delegates to to_decimal_amount with a decimals default.
        assert wei_to_ether('1500000', decimals=6) == Decimal('1.5')

    def test_error_empty_string(self) -> None:
        with pytest.raises(ValueError, match='empty'):
            wei_to_ether('')

    def test_error_whitespace_string(self) -> None:
        with pytest.raises(ValueError, match='empty'):
            wei_to_ether('   ')

    def test_error_none_like(self) -> None:
        with pytest.raises(ValueError, match='Amount must be str or int'):
            wei_to_ether(None)  # type: ignore[arg-type]

    def test_error_non_numeric(self) -> None:
        with pytest.raises(ValueError, match='Invalid amount value'):
            wei_to_ether('abc')

    def test_error_nan_and_infinity(self) -> None:
        with pytest.raises(ValueError, match='Non-finite'):
            wei_to_ether('NaN')
        with pytest.raises(ValueError, match='Non-finite'):
            wei_to_ether('Infinity')

    def test_error_fractional_wei_is_corrupted_data(self) -> None:
        with pytest.raises(ValueError, match='Fractional base-unit'):
            wei_to_ether('1.5')

    def test_error_float_input_rejected(self) -> None:
        with pytest.raises(ValueError, match='Amount must be str or int'):
            wei_to_ether(1.5)  # type: ignore[arg-type]

    def test_surrounding_whitespace_tolerated(self) -> None:
        assert wei_to_ether(' 1500000000000000000\n') == Decimal('1.5')


class TestToDecimalAmount:
    def test_usdc_6_decimals(self) -> None:
        assert to_decimal_amount('1500000', 6) == Decimal('1.5')

    def test_wbtc_8_decimals(self) -> None:
        assert to_decimal_amount('100000000', 8) == Decimal('1')

    def test_api_token_decimal_string_roundtrip(self) -> None:
        # Erc20Transfer rows carry value + tokenDecimal as sibling strings.
        value, token_decimal = '123456789', '6'
        assert to_decimal_amount(value, int(token_decimal)) == Decimal('123.456789')

    def test_huge_token_amount_exact(self) -> None:
        raw = '98765432109876543210987654321098765432'
        assert str(to_decimal_amount(raw, 18)) == '98765432109876543210.987654321098765432'

    def test_negative_token_amount(self) -> None:
        assert to_decimal_amount('-2500000', 6) == Decimal('-2.5')

    def test_error_negative_decimals(self) -> None:
        with pytest.raises(ValueError, match='decimals must be >= 0'):
            to_decimal_amount('1', -1)

    def test_zero_decimals(self) -> None:
        assert to_decimal_amount('42', 0) == Decimal('42')


class TestFormatEther:
    def test_default_precision(self) -> None:
        assert format_ether('1500000000000000000') == '1.500000'

    def test_trailing_zeros_kept(self) -> None:
        assert format_ether(10**18) == '1.000000'

    def test_custom_precision(self) -> None:
        assert format_ether('1500000000000000000', precision=2) == '1.50'

    def test_precision_zero_rounds_half_up(self) -> None:
        assert format_ether('1500000000000000000', precision=0) == '2'

    def test_half_up_rounding_boundary(self) -> None:
        # 5e11 wei == 0.0000005 ether: half-up rounds to 0.000001
        # (banker's rounding would give 0.000000).
        assert format_ether('500000000000') == '0.000001'

    def test_dust_rounds_to_zero(self) -> None:
        assert format_ether('1') == '0.000000'

    def test_negative_dust_has_no_negative_zero(self) -> None:
        assert format_ether('-1') == '0.000000'

    def test_negative_amount(self) -> None:
        assert format_ether('-1500000000000000000') == '-1.500000'

    def test_token_decimals(self) -> None:
        assert format_ether('1500000', decimals=6, precision=2) == '1.50'

    def test_huge_value_no_context_overflow(self) -> None:
        # 10**40 wei == 10**22 ether — 29 output digits, beyond the default
        # 28-digit Decimal context; must format exactly, not raise.
        assert format_ether(10**40) == '10000000000000000000000.000000'

    def test_rounding_carry_grows_integer_part(self) -> None:
        # 9999999500000000000 wei == 9.9999995 ether: half-up produces a
        # carry into a new integer digit (10.000000). The context precision
        # must reserve a digit for it — this used to raise InvalidOperation.
        assert format_ether('9999999500000000000', 18, 6) == '10.000000'
        assert format_ether('-9999999500000000000', 18, 6) == '-10.000000'
        # All-nines boundary: 9.9999994 ether rounds down, no carry.
        assert format_ether('9999999400000000000', 18, 6) == '9.999999'
        # Carry with fewer decimals (9.95 -> 10.0 at precision 1).
        assert format_ether('9950000000000000000', 18, 1) == '10.0'

    def test_error_negative_precision(self) -> None:
        with pytest.raises(ValueError, match='precision must be >= 0'):
            format_ether('1', precision=-1)

    def test_error_invalid_amount_propagates(self) -> None:
        with pytest.raises(ValueError, match='Invalid amount value'):
            format_ether('ouch')


# ───────────────────────────── hex-aware parsing ────────────────────────────


class TestHexToInt:
    def test_hex_string(self) -> None:
        assert hex_to_int('0x1a') == 26

    def test_uppercase_prefix_and_digits(self) -> None:
        assert hex_to_int('0X1A') == 26

    def test_decimal_string(self) -> None:
        assert hex_to_int('26') == 26

    def test_int_passthrough(self) -> None:
        assert hex_to_int(26) == 26
        assert hex_to_int(-7) == -7

    def test_zero(self) -> None:
        assert hex_to_int('0x0') == 0
        assert hex_to_int('0') == 0

    def test_negative_hex(self) -> None:
        assert hex_to_int('-0x10') == -16

    def test_whitespace_tolerated(self) -> None:
        assert hex_to_int(' 0x1a ') == 26

    def test_roundtrip_hex_of_int(self) -> None:
        for value in (0, 1, 42, 26, 21000, 2**64):
            assert hex_to_int(hex(value)) == value

    def test_error_bare_hex_without_prefix(self) -> None:
        # '1a' is ambiguous — treated as decimal and rejected, not guessed.
        with pytest.raises(ValueError, match='Invalid integer value'):
            hex_to_int('1a')

    def test_error_garbage(self) -> None:
        with pytest.raises(ValueError, match='Invalid integer value'):
            hex_to_int('0xzz')

    def test_error_empty_and_prefix_only(self) -> None:
        with pytest.raises(ValueError, match='Invalid integer value'):
            hex_to_int('')
        with pytest.raises(ValueError, match='Invalid integer value'):
            hex_to_int('0x')

    def test_error_non_str_int(self) -> None:
        with pytest.raises(ValueError, match='Integer must be str or int'):
            hex_to_int(None)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match='Integer must be str or int'):
            hex_to_int(1.5)  # type: ignore[arg-type]


class TestHexToStr:
    def test_prefixed(self) -> None:
        assert hex_to_str('0x48656c6c6f') == 'Hello'

    def test_unprefixed(self) -> None:
        assert hex_to_str('48656c6c6f') == 'Hello'

    def test_empty_input_field(self) -> None:
        # Empty transaction input arrives as '0x'.
        assert hex_to_str('0x') == ''
        assert hex_to_str('') == ''

    def test_multibyte_utf8(self) -> None:
        assert hex_to_str('0xd09ed0b9') == 'Ой'

    def test_error_odd_length(self) -> None:
        with pytest.raises(ValueError, match='Invalid hex-encoded UTF-8 data'):
            hex_to_str('0x123')

    def test_error_not_hex(self) -> None:
        with pytest.raises(ValueError, match='Invalid hex-encoded UTF-8 data'):
            hex_to_str('0xzz')

    def test_error_invalid_utf8(self) -> None:
        # 0xff is not a valid UTF-8 byte — surfaced as ValueError, not UnicodeDecodeError.
        with pytest.raises(ValueError, match='Invalid hex-encoded UTF-8 data'):
            hex_to_str('0xff')

    def test_error_non_str(self) -> None:
        with pytest.raises(ValueError, match='Hex data must be str'):
            hex_to_str(123)  # type: ignore[arg-type]


# ─────────────────────────────── timestamps ─────────────────────────────────


class TestToDatetime:
    def test_decimal_string(self) -> None:
        assert to_datetime('1609459200') == datetime(2021, 1, 1, 0, 0, tzinfo=UTC)

    def test_int_input(self) -> None:
        assert to_datetime(1609459200) == datetime(2021, 1, 1, 0, 0, tzinfo=UTC)

    def test_hex_timestamp(self) -> None:
        # JSON-RPC proxy blocks carry hex block.timestamp fields.
        assert to_datetime(hex(1609459200)) == datetime(2021, 1, 1, 0, 0, tzinfo=UTC)

    def test_epoch(self) -> None:
        assert to_datetime('0') == datetime(1970, 1, 1, 0, 0, tzinfo=UTC)

    def test_timezone_aware_utc(self) -> None:
        dt = to_datetime('1609459200')
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timedelta(0)
        assert dt.tzinfo is UTC

    def test_error_unparsable(self) -> None:
        with pytest.raises(ValueError, match='Invalid unix timestamp value'):
            to_datetime('abc')
        with pytest.raises(ValueError, match='Invalid unix timestamp value'):
            to_datetime('2021-01-01')

    def test_error_empty_and_none(self) -> None:
        with pytest.raises(ValueError, match='Invalid unix timestamp value'):
            to_datetime('')
        with pytest.raises(ValueError, match='Unix timestamp must be str or int'):
            to_datetime(None)  # type: ignore[arg-type]

    def test_error_out_of_range_is_value_error(self) -> None:
        # 2**64-1 seconds is far beyond year 9999: datetime raises
        # OverflowError internally, but this module's contract is
        # ValueError-only.
        with pytest.raises(ValueError, match='out of range'):
            to_datetime('0x' + 'f' * 16)
        with pytest.raises(ValueError, match='out of range'):
            to_datetime(-(2**64))


class TestToIso:
    def test_iso_format(self) -> None:
        assert to_iso('1609459200') == '2021-01-01T00:00:00+00:00'

    def test_epoch(self) -> None:
        assert to_iso(0) == '1970-01-01T00:00:00+00:00'

    def test_hex_parity(self) -> None:
        assert to_iso(hex(1609459200)) == to_iso(1609459200)

    def test_error_propagates(self) -> None:
        with pytest.raises(ValueError, match='Invalid unix timestamp value'):
            to_iso('not-a-timestamp')


# ───────────────────────────── integration / exports ────────────────────────


class TestPublicExports:
    def test_all_helpers_exported_from_package(self) -> None:
        import aiochainscan

        for name in (
            'wei_to_ether',
            'format_ether',
            'to_decimal_amount',
            'hex_to_int',
            'hex_to_str',
            'to_datetime',
            'to_iso',
        ):
            assert name in aiochainscan.__all__
            assert callable(getattr(aiochainscan, name))

    def test_raw_api_row_conversion(self) -> None:
        # A competitor-style raw row (results.ts NormalTransaction shape):
        # every scalar is a string; convert the fields you actually need.
        row = {
            'value': '1000000000000000000',
            'timeStamp': '1609459200',
            'gasUsed': '21000',
            'nonce': '0x1a',  # proxy-flavored variant of the same field
        }
        assert wei_to_ether(row['value']) == Decimal('1')
        assert to_iso(row['timeStamp']) == '2021-01-01T00:00:00+00:00'
        assert hex_to_int(row['gasUsed']) == 21000
        assert hex_to_int(row['nonce']) == 26

    def test_erc20_transfer_row_with_token_decimals(self) -> None:
        row = {'value': '123456789', 'tokenDecimal': '6', 'tokenSymbol': 'USDC'}
        amount = to_decimal_amount(row['value'], int(row['tokenDecimal']))
        assert amount == Decimal('123.456789')
        assert (
            format_ether(row['value'], decimals=int(row['tokenDecimal']), precision=2) == '123.46'
        )
