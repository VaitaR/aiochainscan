from datetime import date, datetime, timedelta, timezone

from aiochainscan.utils.date import default_range


def test_default_range():
    """Test default_range function with various parameters."""
    # Expected end date: yesterday UTC
    yesterday_utc = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    # Test default 30 days
    start, end = default_range()
    expected_start = yesterday_utc - timedelta(days=30)

    assert end == yesterday_utc
    assert start == expected_start

    # Test custom days
    start, end = default_range(days=7)
    expected_start = yesterday_utc - timedelta(days=7)

    assert end == yesterday_utc
    assert start == expected_start

    # Test with 0 days (should give same date)
    start, end = default_range(days=0)
    assert start == yesterday_utc
    assert end == yesterday_utc

    # Test with 1 day
    start, end = default_range(days=1)
    expected_start = yesterday_utc - timedelta(days=1)
    assert start == expected_start
    assert end == yesterday_utc

    # Test with large number of days
    start, end = default_range(days=365)
    expected_start = yesterday_utc - timedelta(days=365)
    assert start == expected_start
    assert end == yesterday_utc


def test_default_range_return_type():
    """Test that default_range returns a tuple of date objects."""
    start, end = default_range()

    assert isinstance(start, date)
    assert isinstance(end, date)
    assert isinstance((start, end), tuple)
    assert len((start, end)) == 2


def test_default_range_order():
    """Test that start date is always before or equal to end date."""
    start, end = default_range(days=30)
    assert start <= end

    start, end = default_range(days=0)
    assert start == end

    start, end = default_range(days=1)
    assert start < end
