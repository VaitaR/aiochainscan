"""
Date utilities for aiochainscan.

This module provides helper functions for working with dates in API requests.
"""

from datetime import date, datetime, timedelta, timezone


def default_range(days: int = 30) -> tuple[date, date]:
    """Generate a default date range for API requests.

    Uses yesterday's date (UTC) as the end date to ensure the date is fully
    closed and calculated by all blockchain explorers, while avoiding
    "End date cannot be greater than today" errors from timezone differences.

    Args:
        days: Number of days in the range (default: 30)

    Returns:
        Tuple of (start_date, end_date) where end_date is yesterday UTC

    Examples:
        >>> start, end = default_range()
        >>> print(f"From {start} to {end}")  # Last 30 days ending yesterday

        >>> start, end = default_range(7)
        >>> print(f"From {start} to {end}")  # Last 7 days ending yesterday
    """
    # Use yesterday UTC as safe closed day (already finalized by all explorers)
    end_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    start_date = end_date - timedelta(days=days)
    return start_date, end_date
