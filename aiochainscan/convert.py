"""Value conversion helpers for explorer-API scalars.

Explorer APIs return every scalar as a JSON string: wei amounts, hex numbers
from the JSON-RPC proxy, unix timestamps. Competitor SDKs pass those strings
through untouched — these module-level helpers close that gap with exact,
float-free conversions:

- Wei/token math is ``Decimal``-exact (never ``float``), survives values
  beyond 10**30 wei and keeps negative (allowance-style) amounts valid.
- Hex-aware parsing accepts ``'0x...'`` hex strings, decimal strings and
  already-converted ``int`` values — the three shapes one field can take
  across Etherscan-style and proxy endpoints.
- Timestamps convert to timezone-aware (UTC) ``datetime`` objects.

All functions are pure, stateless and dependency-free (stdlib only).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

__all__ = [
    'format_ether',
    'hex_to_int',
    'hex_to_str',
    'to_datetime',
    'to_decimal_amount',
    'to_iso',
    'wei_to_ether',
]


def _coerce_decimal(raw: str | int) -> Decimal:
    """Parse a base-unit amount exactly (integer str/int only, no float step).

    Wei semantics are integer math: fractional base-unit strings are rejected
    as corrupted data rather than silently accepted.
    """
    if isinstance(raw, int):
        return Decimal(raw)
    if not isinstance(raw, str):
        raise ValueError(f'Amount must be str or int, got {type(raw).__name__}: {raw!r}')
    text = raw.strip()
    if not text:
        raise ValueError('Amount string is empty — expected a base-unit integer string')
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f'Invalid amount value: {raw!r}') from exc
    if not value.is_finite():
        raise ValueError(f'Non-finite amount value: {raw!r}')
    if value != value.to_integral_value():
        raise ValueError(f'Fractional base-unit amount: {raw!r} (wei is integer math)')
    return value


def _parse_flexible_int(value: str | int, kind: str) -> int:
    """Parse an API scalar that arrives as int, decimal string or ``0x`` hex string."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        body = text[1:] if text[:1] in ('+', '-') else text
        try:
            if body[:2].lower() == '0x':
                return int(text, 16)
            return int(text, 10)
        except ValueError as exc:
            raise ValueError(f'Invalid {kind} value: {value!r}') from exc
    raise ValueError(
        f'{kind.capitalize()} must be str or int, got {type(value).__name__}: {value!r}'
    )


def to_decimal_amount(raw: str | int, decimals: int) -> Decimal:
    """Convert a raw base-unit amount to a human-scale ``Decimal``.

    Exact integer→decimal scaling (``10**-decimals`` exponent shift, no float
    step, no division rounding), correct for any magnitude — including values
    beyond 10**30 wei — and for negative amounts.

    Args:
        raw: Base-unit integer as ``str`` or ``int`` (explorers return strings).
        decimals: Token precision — 18 for ETH, 6 for USDC, 8 for WBTC, ...

    Returns:
        Exact amount as ``Decimal`` (e.g. ``Decimal('1.5')``).

    Raises:
        ValueError: On empty/None-like input, non-numeric, fractional or
            non-finite values, or negative ``decimals``.

    Examples:
        >>> to_decimal_amount('1500000000000000000', 18)
        Decimal('1.5')
        >>> to_decimal_amount('1500000', 6)      # USDC
        Decimal('1.5')
        >>> to_decimal_amount('100000000', 8)    # WBTC
        Decimal('1')
    """
    if decimals < 0:
        raise ValueError(f'decimals must be >= 0, got {decimals}')
    value = _coerce_decimal(raw)
    # scaleb is exact only while the coefficient fits the context precision —
    # widen it to the actual digit count so 30+ digit wei values survive.
    with localcontext() as ctx:
        ctx.prec = max(len(value.as_tuple().digits), 28) + 1
        return value.scaleb(-decimals)


def wei_to_ether(wei: str | int, decimals: int = 18) -> Decimal:
    """Convert wei to ether — ``to_decimal_amount`` with the 18-decimals default.

    The wei argument stays string/int math end to end: the result is an exact
    ``Decimal`` (never ``float``), so ``wei_to_ether('100000000000000000') +
    wei_to_ether('200000000000000000')`` is exactly ``Decimal('0.3')``.

    Args:
        wei: Base-unit amount as ``str`` or ``int``; negatives are valid.
        decimals: Native-asset precision (18 for ETH and most chains).

    Raises:
        ValueError: On invalid input (see :func:`to_decimal_amount`).

    Examples:
        >>> wei_to_ether('1500000000000000000')
        Decimal('1.5')
        >>> wei_to_ether(-21000000000000000000)
        Decimal('-21')
    """
    return to_decimal_amount(wei, decimals)


def format_ether(wei: str | int, decimals: int = 18, precision: int = 6) -> str:
    """Format a base-unit amount as a fixed-precision human-readable string.

    Rounds half-up to ``precision`` decimal places (the trailing zeros are
    kept: ``'1.500000'``). Works for any magnitude — the context precision is
    sized to the value, so formatting 10**40 wei does not overflow.

    Args:
        wei: Base-unit amount as ``str`` or ``int``.
        decimals: Token precision (18 for ETH, 6 for USDC, ...).
        precision: Decimal places in the output string.

    Raises:
        ValueError: On invalid input or negative ``precision``.

    Examples:
        >>> format_ether('1500000000000000000')
        '1.500000'
        >>> format_ether('1500000', decimals=6, precision=2)
        '1.50'
    """
    if precision < 0:
        raise ValueError(f'precision must be >= 0, got {precision}')
    value = to_decimal_amount(wei, decimals)
    with localcontext() as ctx:
        # Integer digits + requested places + one carry digit: ROUND_HALF_UP
        # can grow the integer part by one place (9.9999995 -> 10.000000),
        # and quantize raises InvalidOperation when the result would not fit
        # the context precision.
        ctx.prec = max(value.adjusted() + 1, 1) + precision + 1
        quantized = value.quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)
    if quantized.is_zero():
        quantized = abs(quantized)  # avoid '-0.000000' for tiny negative dust
    return format(quantized, 'f')


def hex_to_int(value: str | int) -> int:
    """Parse an API integer that may arrive as hex, decimal string or int.

    The main dual-mode helper: JSON-RPC proxy fields come as ``'0x1a'`` while
    Etherscan-style endpoints return the same value as ``'26'``. Already
    converted ``int`` values pass through unchanged.

    Raises:
        ValueError: On non-hex/non-decimal strings (including bare hex like
            ``'1a'`` without the ``0x`` prefix — that is ambiguous) or
            non-str/int input.

    Examples:
        >>> hex_to_int('0x1a')
        26
        >>> hex_to_int('26')
        26
        >>> hex_to_int(26)
        26
    """
    return _parse_flexible_int(value, 'integer')


def hex_to_str(value: str) -> str:
    """Decode a hex string (``0x`` prefix optional) to UTF-8 text.

    For `data`/`input` fields; an empty value (``'0x'`` or ``''``) decodes to
    an empty string, as empty transaction input does.

    Raises:
        ValueError: On odd-length or non-hex input, invalid UTF-8 bytes, or
            non-str input.

    Examples:
        >>> hex_to_str('0x48656c6c6f')
        'Hello'
        >>> hex_to_str('0x')
        ''
    """
    if not isinstance(value, str):
        raise ValueError(f'Hex data must be str, got {type(value).__name__}: {value!r}')
    text = value.strip()
    if text[:2].lower() == '0x':
        text = text[2:]
    try:
        return bytes.fromhex(text).decode('utf-8')
    except ValueError as exc:  # covers fromhex and UnicodeDecodeError
        raise ValueError(f'Invalid hex-encoded UTF-8 data: {value!r}') from exc


def to_datetime(ts: str | int) -> datetime:
    """Convert a unix timestamp (seconds) to a timezone-aware UTC ``datetime``.

    Accepts the same dual-mode input as :func:`hex_to_int`: ``int``, decimal
    string or ``'0x...'`` hex string (proxy `block.timestamp` fields are hex).

    Raises:
        ValueError: On unparsable input or timestamps outside the datetime
            range (the contract is ValueError-only, so ``OverflowError`` from
            the datetime constructor is re-raised as ``ValueError``).

    Examples:
        >>> to_datetime('1609459200')
        datetime.datetime(2021, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    """
    seconds = _parse_flexible_int(ts, 'unix timestamp')
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError) as exc:
        raise ValueError(f'Unix timestamp out of range: {ts!r}') from exc


def to_iso(ts: str | int) -> str:
    """Convert a unix timestamp to an ISO-8601 string (UTC).

    Raises:
        ValueError: On unparsable input.

    Examples:
        >>> to_iso('1609459200')
        '2021-01-01T00:00:00+00:00'
    """
    return to_datetime(ts).isoformat()
