"""
Analytics service with Polars DataFrame support.

Provides high-performance data export for Data Engineers and AI agents.
Install with: pip install aiochainscan[data]
"""

import asyncio
import logging
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


logger = logging.getLogger(__name__)
OOM_WARNING_THRESHOLD = 100_000


def require_polars() -> None:
    """Ensure Polars optional dependency is available."""
    if not POLARS_AVAILABLE:
        raise PolarsNotAvailableError()


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
    require_polars()

    # Collect from async iterator if needed
    if hasattr(transactions, '__aiter__'):
        tx_list = []
        i = 0
        async for tx in transactions:
            tx_list.append(tx)
            i += 1
            if i % 1000 == 0:
                await asyncio.sleep(0)
    else:
        tx_list = list(transactions)

    if len(tx_list) >= OOM_WARNING_THRESHOLD:
        logger.warning(
            'Materializing %s transactions in-memory for DataFrame conversion. '
            'For very large datasets, prefer streaming to NDJSON/Parquet and scan with Polars.',
            len(tx_list),
        )

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

    rows: list[dict[str, Any]] = []
    for tx in tx_list:
        # Handle nested address objects (BlockScout V2 format)
        from_addr = tx.get('from', {})
        to_addr = tx.get('to', {})

        value_wei = str(int(tx.get('value', 0)))
        from_value = from_addr.get('hash') if isinstance(from_addr, dict) else from_addr
        to_value = to_addr.get('hash') if isinstance(to_addr, dict) else to_addr

        rows.append(
            {
                'hash': tx.get('hash', ''),
                'block_number': tx.get('block_number') or tx.get('blockNumber'),
                'from_address': from_value,
                'to_address': to_value or '',
                'value_wei': value_wei,
                'value_eth': int(value_wei) / 1e18,
                'gas_used': str(int(tx.get('gas_used', 0) or tx.get('gasUsed', 0))),
                'timestamp': tx.get('timestamp', tx.get('timeStamp', '')),
            }
        )
        # Store Wei as string to prevent integer overflow (Int64 max ~ 9.22 ETH)

    return pl.from_dicts(
        rows,
        schema_overrides={
            'hash': pl.Utf8,
            'block_number': pl.Int64,
            'from_address': pl.Utf8,
            'to_address': pl.Utf8,
            'value_wei': pl.Utf8,
            'value_eth': pl.Float64,
            'gas_used': pl.Utf8,
            'timestamp': pl.Utf8,
        },
    )


async def token_portfolio_to_dataframe(tokens: list[dict[str, Any]]) -> 'pl.DataFrame':
    """
    Convert token portfolio to a Polars DataFrame.

    Args:
        tokens: List of token holding dicts

    Returns:
        Polars DataFrame with token data
    """
    require_polars()

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

    rows: list[dict[str, Any]] = []
    for item in tokens:
        token_info = item.get('token', {})
        decimals = int(token_info.get('decimals', 18))
        value = int(item.get('value', 0))

        # Handle both Etherscan (uses 'address') and BlockScout V2 (uses 'address_hash')
        contract_addr = token_info.get('address_hash') or token_info.get('address', '')

        rows.append(
            {
                'symbol': token_info.get('symbol', ''),
                'name': token_info.get('name', ''),
                'contract_address': contract_addr,
                'balance': value / (10**decimals) if decimals > 0 else float(value),
                'decimals': decimals,
            }
        )

    return pl.from_dicts(
        rows,
        schema_overrides={
            'symbol': pl.Utf8,
            'name': pl.Utf8,
            'contract_address': pl.Utf8,
            'balance': pl.Float64,
            'decimals': pl.Int64,
        },
    )


# Convenience function for ChainscanClient integration
def is_polars_available() -> bool:
    """Check if Polars is installed and available."""
    return POLARS_AVAILABLE
