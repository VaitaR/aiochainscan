from datetime import date, timedelta

from aiochainscan.utils.date import default_range


def test_default_range():
    """Test default_range function with various parameters."""
    # Fixed historical end date: January 31, 2024
    fixed_end = date(2024, 1, 31)

    # Test default 30 days
    start, end = default_range()
    expected_start = fixed_end - timedelta(days=30)

    assert end == fixed_end
    assert start == expected_start
    assert start == date(2024, 1, 1)  # Jan 1, 2024

    # Test custom days
    start, end = default_range(days=7)
    expected_start = fixed_end - timedelta(days=7)

    assert end == fixed_end
    assert start == expected_start
    assert start == date(2024, 1, 24)  # Jan 24, 2024

    # Test with 0 days (should give same date)
    start, end = default_range(days=0)
    assert start == fixed_end
    assert end == fixed_end

    # Test with 1 day
    start, end = default_range(days=1)
    expected_start = fixed_end - timedelta(days=1)
    assert start == expected_start
    assert end == fixed_end
    assert start == date(2024, 1, 30)  # Jan 30, 2024

    # Test with large number of days
    start, end = default_range(days=365)
    expected_start = fixed_end - timedelta(days=365)
    assert start == expected_start
    assert end == fixed_end


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
