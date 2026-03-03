"""
Stream transactions to CSV and count event logs using aiochainscan.
"""

import asyncio
import csv
import logging

from aiochainscan import ChainscanClient
from aiochainscan.exceptions import PaginationDataLossError

logger = logging.getLogger(__name__)


async def stream_to_csv(address: str, output_path: str) -> int:
    """
    Stream all transactions for *address* to a CSV file.

    Uses iter_transactions_streaming (batch_size=500) so RAM usage stays
    constant regardless of wallet size.

    Columns written: hash, from_addr, to_addr, value_eth, timestamp

    Returns the total number of transactions written.
    """
    total = 0

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(
                f, fieldnames=['hash', 'from_addr', 'to_addr', 'value_eth', 'timestamp']
            )
            writer.writeheader()

            try:
                async for batch in client.iter_transactions_streaming(address, batch_size=500):
                    rows = []
                    for tx in batch:
                        from_field = tx.get('from') or {}
                        to_field = tx.get('to') or {}
                        rows.append(
                            {
                                'hash': tx.get('hash'),
                                'from_addr': from_field.get('hash')
                                if isinstance(from_field, dict)
                                else from_field,
                                'to_addr': to_field.get('hash')
                                if isinstance(to_field, dict)
                                else to_field,
                                'value_eth': int(tx.get('value', 0)) / 10**18,
                                'timestamp': tx.get('timestamp'),
                            }
                        )
                    writer.writerows(rows)
                    total += len(batch)

            except PaginationDataLossError as exc:
                logger.warning(
                    'PaginationDataLossError encountered after %d transactions — '
                    'some data may be missing: %s',
                    total,
                    exc,
                )

    return total


async def count_logs(contract_address: str, from_block: int, topic0: str) -> int:
    """
    Count the total number of event logs emitted by *contract_address*
    matching *topic0* starting from *from_block*.

    Uses etherscan scanner (requires ETHERSCAN_KEY env var).
    """
    total = 0

    async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
        async for batch in client.iter_logs_streaming(
            contract_address,
            from_block=from_block,
            topic0=topic0,
            batch_size=1000,
        ):
            total += len(batch)

    return total


if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO)

    address = sys.argv[1] if len(sys.argv) > 1 else '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
    output = sys.argv[2] if len(sys.argv) > 2 else 'transactions.csv'

    written = asyncio.run(stream_to_csv(address, output))
    print(f'Written {written} transactions to {output}')
