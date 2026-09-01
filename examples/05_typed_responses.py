#!/usr/bin/env python3
"""
05_typed_responses.py - Typed Data Without Pydantic ("typing-lite")

Responses are plain dicts of string scalars. This example shows how to layer
exact typing on top of them with the module-level conversion helpers from
``aiochainscan.convert``:

- ``wei_to_ether`` / ``to_decimal_amount`` — exact ``Decimal`` token math
- ``hex_to_int`` — hex-or-decimal string fields (proxy vs REST)
- ``to_datetime`` / ``to_iso`` — unix timestamps (tz-aware UTC)

A full Pydantic DTO layer is planned but not implemented; dict responses plus
these helpers give the same guarantees (no float step) without the dependency.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime

from aiochainscan import ChainscanClient, to_datetime, wei_to_ether


@dataclass(frozen=True)
class TypedTransaction:
    """A transaction page item with Python-native, exactly-converted types."""

    tx_hash: str
    from_address: str
    to_address: str | None
    value_eth: str  # Decimal-rendered string, exact — never float
    timestamp: datetime | None


def parse_transaction(item: dict) -> TypedTransaction:
    """Map one raw dict item to typed fields via ``aiochainscan.convert``."""
    ts = item.get('timeStamp') or item.get('timestamp')
    return TypedTransaction(
        tx_hash=item.get('hash', ''),
        from_address=item.get('from', ''),
        to_address=item.get('to') or None,
        value_eth=str(wei_to_ether(item.get('value', '0'))),
        timestamp=to_datetime(ts) if ts else None,
    )


async def main():
    address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    try:
        print('Typed Blockchain Data Extraction (dict + convert helpers)')
        print('=' * 60)

        # Single page of raw dict items
        raw_items = await client.get_transactions(address)

        print(f'\nParsing {len(raw_items)} transactions into typed records...\n')

        transactions = [parse_transaction(item) for item in raw_items[:5]]

        for tx in transactions:
            print(f'  Transaction: {tx.tx_hash[:20]}...')
            print(f'     Block time: {tx.timestamp.isoformat() if tx.timestamp else "N/A"}')
            print(f'     From: {tx.from_address[:16]}...')
            print(f'     To:   {(tx.to_address or "Contract Creation")[:16]}...')
            print(f'     Value: {tx.value_eth} ETH (exact Decimal)')
            print()

        # Type-safe aggregation — Decimal-exact, no float error
        total = sum(wei_to_ether(item.get('value', '0')) for item in raw_items[:5])
        print(f'Total value transferred: {total} ETH')
    finally:
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
