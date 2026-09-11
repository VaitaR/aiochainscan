#!/usr/bin/env python3
"""Export an address's transaction history to CSV.

Self-contained — needs nothing but the published package:

    pip install aiochainscan
    python 02_export_to_csv.py [address] [--all]

Without ``--all`` one provider page is exported (fast). With it, the complete
history is streamed and written batch by batch, so memory stays flat no matter
how large the account is.

The normalized surface (`iter_transactions_normalized`) is what keeps the CSV
schema stable: raw provider items differ per explorer (`from` is a string on
Etherscan and a nested object on Blockscout v2), the normalized dataclass does
not. Wei values are written as integer strings — a spreadsheet or a float
column would silently round them.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

from aiochainscan import ChainscanClient
from aiochainscan.domain.normalized import Transaction
from aiochainscan.exceptions import ChainscanClientError, ChainscanRateLimitError

SCANNER = 'blockscout_v2'
CHAIN = 'ethereum'

VITALIK = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

COLUMNS = (
    'hash',
    'block_number',
    'timestamp',
    'from_address',
    'to_address',
    'value_wei',
    'gas_used',
    'gas_price_wei',
    'is_error',
)


def to_row(tx: Transaction) -> dict[str, object]:
    return {
        'hash': tx.hash or '',
        'block_number': tx.block_number if tx.block_number is not None else '',
        'timestamp': tx.timestamp.isoformat() if tx.timestamp else '',
        'from_address': tx.from_address or '',
        'to_address': tx.to_address or '',
        'value_wei': str(tx.value_wei),
        'gas_used': tx.gas_used if tx.gas_used is not None else '',
        'gas_price_wei': tx.gas_price_wei if tx.gas_price_wei is not None else '',
        'is_error': '' if tx.is_error is None else int(tx.is_error),
    }


async def export(address: str, output: Path, *, complete: bool) -> int:
    written = 0
    with output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()

        async with ChainscanClient.from_config(SCANNER, CHAIN) as client:
            if complete:
                # Complete history or an exception — never a silent partial
                # result (guarantee_complete defaults to True).
                async for batch in client.iter_transactions_normalized(address, batch_size=1_000):
                    writer.writerows(to_row(tx) for tx in batch)
                    written += len(batch)
                    print(f'  {written} rows written…')
            else:
                page = await client.get_transactions_normalized(address)
                writer.writerows(to_row(tx) for tx in page)
                written = len(page)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('address', nargs='?', default=VITALIK)
    parser.add_argument(
        '--all', action='store_true', help='Export the complete history, not one page'
    )
    parser.add_argument('--output', type=Path, help='CSV path (default: <address>.csv)')
    args = parser.parse_args()

    output = args.output or Path(f'{args.address[:10]}_transactions.csv')
    scope = 'complete history (guaranteed)' if args.all else 'one provider page'
    print(f'Exporting {args.address} -> {output}')
    print(f'  {SCANNER}/{CHAIN}, {scope}')

    try:
        written = asyncio.run(export(args.address, output, complete=args.all))
    except ChainscanRateLimitError:
        raise SystemExit(
            f'{SCANNER} rate-limited this export. Retry later, or set ETHERSCAN_KEY '
            f"and switch SCANNER to 'etherscan'."
        ) from None
    except ChainscanClientError as exc:
        # Public Blockscout instances answer a burst with 403 or a
        # bot-protection page; both arrive here, not as a traceback.
        raise SystemExit(f'{SCANNER} refused the export: {exc}') from None

    print(f'Done: {written} rows in {output}')
    if not args.all:
        print('This is ONE page. Re-run with --all for the complete history.')


if __name__ == '__main__':
    main()
