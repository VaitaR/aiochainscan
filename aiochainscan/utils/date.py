"""
Date utilities for aiochainscan.

This module provides helper functions for working with dates in API requests.
"""

from datetime import date, timedelta


def default_range(days: int = 30) -> tuple[date, date]:
    """Generate a default date range for API requests using safe historical dates.

    Uses fixed historical dates to avoid "End date cannot be greater than today" errors
    that can occur due to timezone differences or server time discrepancies.

    Args:
        days: Number of days in the range (default: 30)

    Returns:
        Tuple of (start_date, end_date) using safe historical dates

    Examples:
        >>> start, end = default_range()
        >>> print(f"From {start} to {end}")  # Safe 30-day historical range

        >>> start, end = default_range(7)
        >>> print(f"From {start} to {end}")  # Safe 7-day historical range
    """
    # Use fixed historical dates to avoid timezone/server time issues
    # End date: January 31, 2024 (safe historical date)
    end_date = date(2024, 1, 31)
    start_date = end_date - timedelta(days=days)
    return start_date, end_date
