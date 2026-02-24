"""
Analytics service with Polars DataFrame support.

Provides high-performance data export for Data Engineers and AI agents.
Install with: pip install aiochainscan[data]
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl
else:
    pl = Any  # type: ignore[misc,assignment]

# Check for Polars availability
try:
    import polars as pl

    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False


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
        # NOTE: value_wei stored as String to prevent integer overflow
        # (1 ETH = 10^18 Wei, Int64 max = ~9.2 ETH)
        return pl.DataFrame(
            schema={
                'hash': pl.Utf8,
                'block_number': pl.Int64,
                'from_address': pl.Utf8,
                'to_address': pl.Utf8,
                'value_wei': pl.Utf8,  # String to prevent overflow (Wei > Int64 max)
                'value_eth': pl.Float64,
                'gas_used': pl.Utf8,  # String for consistency with Wei values
                'timestamp': pl.Utf8,
            }
        )

    # Normalize transaction data using column-oriented construction for performance
    columns: dict[str, list[Any]] = {
        'hash': [],
        'block_number': [],
        'from_address': [],
        'to_address': [],
        'value_wei': [],
        'value_eth': [],
        'gas_used': [],
        'timestamp': [],
    }

    for tx in tx_list:
        # Handle nested address objects (BlockScout V2 format)
        from_addr = tx.get('from', {})
        to_addr = tx.get('to', {})

        columns['hash'].append(tx.get('hash', ''))
        columns['block_number'].append(tx.get('block_number') or tx.get('blockNumber'))
        columns['from_address'].append(
            from_addr.get('hash') if isinstance(from_addr, dict) else from_addr
        )
        columns['to_address'].append(
            to_addr.get('hash') if isinstance(to_addr, dict) else to_addr or ''
        )
        # Store Wei as string to prevent integer overflow (Int64 max ~ 9.22 ETH)
        columns['value_wei'].append(str(int(tx.get('value', 0))))
        columns['value_eth'].append(int(tx.get('value', 0)) / 1e18)
        columns['gas_used'].append(str(int(tx.get('gas_used', 0) or tx.get('gasUsed', 0))))
        columns['timestamp'].append(tx.get('timestamp', tx.get('timeStamp', '')))

    return pl.DataFrame(columns)


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

    # Use column-oriented construction for performance
    columns: dict[str, list[Any]] = {
        'symbol': [],
        'name': [],
        'contract_address': [],
        'balance': [],
        'decimals': [],
    }

    for item in tokens:
        token_info = item.get('token', {})
        decimals = int(token_info.get('decimals', 18))
        value = int(item.get('value', 0))

        # Handle both Etherscan (uses 'address') and BlockScout V2 (uses 'address_hash')
        contract_addr = token_info.get('address_hash') or token_info.get('address', '')

        columns['symbol'].append(token_info.get('symbol', ''))
        columns['name'].append(token_info.get('name', ''))
        columns['contract_address'].append(contract_addr)
        columns['balance'].append(value / (10**decimals) if decimals > 0 else float(value))
        columns['decimals'].append(decimals)

    return pl.DataFrame(columns)


# Convenience function for ChainscanClient integration
def is_polars_available() -> bool:
    """Check if Polars is installed and available."""
    return POLARS_AVAILABLE
