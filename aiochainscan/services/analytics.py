"""
Analytics service with Polars DataFrame support.

Provides high-performance data export for Data Engineers and AI agents.
Install with: pip install aiochainscan[data]
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl

# Check for Polars availability
try:
    import polars as pl

    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False
    pl = None  # type: ignore[assignment]


class PolarsNotAvailableError(ImportError):
    """Raised when Polars is not installed but DataFrame features are requested."""

    def __init__(self) -> None:
        super().__init__(
            'Polars not installed. Install with: pip install aiochainscan[data] '
            'or pip install polars'
        )


async def transactions_to_dataframe(
    transactions: list[dict[str, Any]] | AsyncIterator[dict[str, Any]],
) -> 'pl.DataFrame':
    """
    Convert transactions to a Polars DataFrame.

    Args:
        transactions: List of transaction dicts or async iterator

    Returns:
        Polars DataFrame with normalized transaction data

    Raises:
        PolarsNotAvailableError: If Polars is not installed
    """
    if not POLARS_AVAILABLE:
        raise PolarsNotAvailableError()

    # Collect from async iterator if needed
    if hasattr(transactions, '__aiter__'):
        tx_list = [tx async for tx in transactions]
    else:
        tx_list = list(transactions)

    if not tx_list:
        # Return empty DataFrame with expected schema
        return pl.DataFrame(
            schema={
                'hash': pl.Utf8,
                'block_number': pl.Int64,
                'from_address': pl.Utf8,
                'to_address': pl.Utf8,
                'value_wei': pl.Int64,
                'value_eth': pl.Float64,
                'gas_used': pl.Int64,
                'timestamp': pl.Utf8,
            }
        )

    # Normalize transaction data
    normalized = []
    for tx in tx_list:
        # Handle nested address objects (BlockScout V2 format)
        from_addr = tx.get('from', {})
        to_addr = tx.get('to', {})

        normalized.append(
            {
                'hash': tx.get('hash', ''),
                'block_number': tx.get('block_number') or tx.get('blockNumber'),
                'from_address': from_addr.get('hash')
                if isinstance(from_addr, dict)
                else from_addr,
                'to_address': to_addr.get('hash') if isinstance(to_addr, dict) else to_addr or '',
                'value_wei': int(tx.get('value', 0)),
                'value_eth': int(tx.get('value', 0)) / 1e18,
                'gas_used': int(tx.get('gas_used', 0) or tx.get('gasUsed', 0)),
                'timestamp': tx.get('timestamp', tx.get('timeStamp', '')),
            }
        )

    return pl.DataFrame(normalized)


async def token_portfolio_to_dataframe(tokens: list[dict[str, Any]]) -> 'pl.DataFrame':
    """
    Convert token portfolio to a Polars DataFrame.

    Args:
        tokens: List of token holding dicts

    Returns:
        Polars DataFrame with token data
    """
    if not POLARS_AVAILABLE:
        raise PolarsNotAvailableError()

    if not tokens:
        return pl.DataFrame(
            schema={
                'symbol': pl.Utf8,
                'name': pl.Utf8,
                'contract_address': pl.Utf8,
                'balance': pl.Float64,
                'decimals': pl.Int64,
            }
        )

    normalized = []
    for item in tokens:
        token_info = item.get('token', {})
        decimals = int(token_info.get('decimals', 18))
        value = int(item.get('value', 0))

        normalized.append(
            {
                'symbol': token_info.get('symbol', ''),
                'name': token_info.get('name', ''),
                'contract_address': token_info.get('address', ''),
                'balance': value / (10**decimals) if decimals > 0 else float(value),
                'decimals': decimals,
            }
        )

    return pl.DataFrame(normalized)


# Convenience function for ChainscanClient integration
def is_polars_available() -> bool:
    """Check if Polars is installed and available."""
    return POLARS_AVAILABLE
