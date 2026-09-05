"""
Analytics service with Polars DataFrame support.

Provides high-performance data export for Data Engineers and AI agents.
Install with: pip install aiochainscan[data]
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..convert import to_decimal_amount, wei_to_ether
from ..domain.normalize import (
    BLOCK_NUMBER_KEYS,
    GAS_USED_KEYS,
    TIMESTAMP_KEYS,
    first_field,
    flat_address,
    int_or_default,
)

if TYPE_CHECKING:
    import polars as pl

# Check for Polars availability
try:
    import polars as pl

    POLARS_AVAILABLE = True

    # Transaction DataFrame schema, declared once and shared by the empty-case
    # constructor and the populated-case builder. NOTE: Wei/gas columns are
    # Utf8 on purpose — Int64 overflows at ~9.22 ETH (1 ETH = 10^18 Wei).
    _TRANSACTIONS_SCHEMA: dict[str, Any] = {
        'hash': pl.Utf8,
        'block_number': pl.Int64,
        'from_address': pl.Utf8,
        'to_address': pl.Utf8,
        'value_wei': pl.Utf8,  # String to prevent overflow (Wei > Int64 max)
        'value_eth': pl.Float64,
        'gas_used': pl.Utf8,  # String for consistency with Wei values
        'timestamp': pl.Utf8,
    }
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
        return pl.DataFrame(schema=_TRANSACTIONS_SCHEMA)

    rows: list[dict[str, Any]] = []
    for tx in tx_list:
        # Provider field dialect (owned by domain/normalize.py): alias-first
        # lookup keeps a falsy 0 (a genesis row keeps its block number), and
        # nested BlockScout-V2 address objects flatten to their hash string.
        from_value = flat_address(tx.get('from'))
        to_value = flat_address(tx.get('to'))

        value_wei = str(int_or_default(tx.get('value'), default=0))

        rows.append(
            {
                'hash': tx.get('hash', ''),
                'block_number': first_field(tx, *BLOCK_NUMBER_KEYS),
                'from_address': from_value,
                'to_address': to_value or '',
                'value_wei': value_wei,
                'value_eth': float(wei_to_ether(value_wei)),
                'gas_used': str(int_or_default(first_field(tx, *GAS_USED_KEYS), default=0)),
                'timestamp': first_field(tx, *TIMESTAMP_KEYS) or '',
            }
        )
        # Store Wei as string to prevent integer overflow (Int64 max ~ 9.22 ETH)

    return pl.from_dicts(rows, schema_overrides=_TRANSACTIONS_SCHEMA)


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
        # A provider may answer ``token: null`` (BlockScout V2 does, for a token
        # whose metadata it could not read) and ``decimals: null`` with it. A
        # null scale is not 18 — it is unknown, so the row keeps its identity
        # and reports a null balance instead of a number scaled by a guess.
        raw_token = item.get('token')
        token_info: dict[str, Any] = raw_token if isinstance(raw_token, dict) else {}
        decimals = int_or_default(token_info.get('decimals', 18), None)
        value = int_or_default(item.get('value', 0), None)

        # Handle both Etherscan (uses 'address') and BlockScout V2 (uses 'address_hash')
        contract_addr = first_field(token_info, 'address_hash', 'address') or ''

        rows.append(
            {
                'symbol': token_info.get('symbol') or '',
                'name': token_info.get('name') or '',
                'contract_address': contract_addr,
                'balance': (
                    float(to_decimal_amount(value, decimals))
                    if value is not None and decimals is not None
                    else None
                ),
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


async def transactions_to_dataframe_arrow(
    calldatas: list[bytes],
    abi_json: str,
) -> 'pl.DataFrame':
    """Convert decoded transaction data directly to Polars DataFrame via Arrow zero-copy.

    This bypasses JSON serialization entirely. Data flows:
    Rust decode → Arrow columns → Polars DataFrame (zero copy).

    Args:
        calldatas: List of raw calldata bytes
        abi_json: Contract ABI as JSON string

    Returns:
        Polars DataFrame with decoded function calls

    Raises:
        PolarsNotAvailableError: If Polars is not installed
        ImportError: If fastabi with Arrow support is not available
    """
    require_polars()

    from aiochainscan.decode import ARROW_AVAILABLE

    if not ARROW_AVAILABLE:
        raise ImportError(
            'Arrow zero-copy requires fastabi with Arrow support. '
            'Rebuild with: cd aiochainscan/fastabi && maturin develop --release'
        )

    # Run Rust decode + Arrow construction in thread pool
    import asyncio

    from aiochainscan.decode import _fast_decode_to_arrow

    record_batch = await asyncio.to_thread(_fast_decode_to_arrow, calldatas, abi_json)

    # Zero-copy conversion: Arrow RecordBatch → Polars DataFrame
    df = pl.from_arrow(record_batch)
    assert isinstance(df, pl.DataFrame)  # RecordBatch always yields DataFrame
    return df


# Convenience function for ChainscanClient integration
def is_polars_available() -> bool:
    """Check if Polars is installed and available."""
    return POLARS_AVAILABLE
