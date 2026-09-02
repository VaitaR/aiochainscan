#!/usr/bin/env python3
"""
02_export_to_csv.py - Export Blockchain Data to CSV

A practical example for Data Engineers: Extract transaction history
and export to CSV format for further analysis in pandas, DuckDB, or BI tools.

Use case: Build a data pipeline for wallet activity analysis.
"""

import asyncio
import csv
from datetime import datetime
from pathlib import Path

from aiochainscan.core.client import ChainscanClient
from aiochainscan.domain.method import Method


async def fetch_transactions(client: ChainscanClient, address: str, limit: int = 100):
    """Fetch transactions from BlockScout V2 API.

    Note: BlockScout V2 returns transactions as a list directly.
    For large-scale pagination, use the services/paging_engine.py
    """

    response = await client.call(Method.ACCOUNT_TRANSACTIONS, address=address)

    # BlockScout V2 returns list directly
    items = response if isinstance(response, list) else response.get('items', [])

    return items[:limit]


def normalize_transaction(tx: dict) -> dict:
    """Transform raw API response to clean CSV row."""

    timestamp = tx.get('timestamp')
    if timestamp:
        # Parse ISO format timestamp
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
    else:
        date_str = ''

    value_wei = int(tx.get('value', 0))

    # Fee can be dict with 'value' or direct value
    fee_data = tx.get('fee')
    if isinstance(fee_data, dict):
        fee_wei = int(fee_data.get('value', 0))
    elif fee_data:
        fee_wei = int(fee_data)
    else:
        fee_wei = 0

    # Handle nested address objects
    from_addr = tx.get('from', {})
    to_addr = tx.get('to', {})

    return {
        'hash': tx.get('hash', ''),
        'block_number': tx.get('block_number', ''),
        'timestamp': date_str,
        'from_address': from_addr.get('hash', '')
        if isinstance(from_addr, dict)
        else str(from_addr),
        'to_address': to_addr.get('hash', '')
        if isinstance(to_addr, dict)
        else str(to_addr)
        if to_addr
        else '',
        'value_eth': value_wei / 1e18,
        'fee_eth': fee_wei / 1e18,
        'status': tx.get('status', ''),
        'tx_type': tx.get('transaction_types', [''])[0] if tx.get('transaction_types') else '',
        'method': tx.get('method', ''),
    }


async def main():
    """Export wallet transactions to CSV file."""

    # Configuration
    address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'  # Vitalik
    output_dir = Path('./exports')
    output_dir.mkdir(exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f'transactions_{address[:10]}_{timestamp}.csv'

    print(f'🔄 Fetching transactions for {address[:10]}...')

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    try:
        # Fetch transactions
        raw_txs = await fetch_transactions(client, address, limit=50)
        print(f'📦 Fetched {len(raw_txs)} transactions')

        # Normalize and export
        normalized = [normalize_transaction(tx) for tx in raw_txs]

        # Write CSV
        if normalized:
            fieldnames = normalized[0].keys()

            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(normalized)

            print(f'✅ Exported to: {output_file}')
            print(f'   Rows: {len(normalized)}')
            print(f'   Columns: {", ".join(fieldnames)}')

            # Show sample
            print('\n📊 Sample data (first 3 rows):')
            for row in normalized[:3]:
                print(f'  {row["hash"][:16]}... | {row["value_eth"]:.4f} ETH | {row["timestamp"]}')
        else:
            print('⚠️ No transactions found')

    finally:
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
