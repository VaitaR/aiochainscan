#!/usr/bin/env python3
"""
05_pydantic_typed_responses.py - Type-Safe Data with Pydantic

Advanced example using Pydantic V2 DTOs for type-safe data extraction.
Perfect for Data Engineers building robust ETL pipelines.

Benefits:
- Automatic hex→int conversion
- Data validation
- IDE autocompletion
- Schema documentation
"""

import asyncio
from datetime import datetime

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

# Import Pydantic V2 DTOs for type-safe responses
from aiochainscan.domain.dto_v2 import (
    TransactionDTO,
)


async def main():
    """Demonstrate type-safe data extraction with Pydantic models."""

    address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    try:
        print('🔷 Type-Safe Blockchain Data Extraction')
        print('=' * 50)

        # Fetch raw response
        raw_response = await client.call(Method.ACCOUNT_TRANSACTIONS, address=address)

        # Parse into Pydantic models - BlockScout V2 returns list directly
        items = raw_response if isinstance(raw_response, list) else raw_response.get('items', [])

        print(f'\n📦 Parsing {len(items)} transactions into typed DTOs...\n')

        # Convert raw dicts to Pydantic models
        transactions = []
        for item in items[:5]:
            try:
                # Map BlockScout V2 response to DTO
                # Note: Field mapping depends on API version
                tx = TransactionDTO(
                    tx_hash=item.get('hash', ''),
                    block_number=item.get('block_number'),
                    from_address=item.get('from', {}).get('hash', ''),
                    to_address=item.get('to', {}).get('hash', '') if item.get('to') else None,
                    value=int(item.get('value', 0)),
                    gas=int(item.get('gas_limit', 0)),
                    gas_used=int(item.get('gas_used', 0)) if item.get('gas_used') else None,
                    timestamp=int(
                        datetime.fromisoformat(
                            item.get('timestamp', '1970-01-01T00:00:00').replace('Z', '+00:00')
                        ).timestamp()
                    )
                    if item.get('timestamp')
                    else None,
                    input_data=item.get('raw_input', ''),
                )
                transactions.append(tx)
            except Exception as e:
                print(f'⚠️ Failed to parse: {e}')

        # Now we have typed data!
        print('✅ Parsed Transactions (with types):\n')

        for tx in transactions:
            # IDE knows all fields and their types!
            print(f'  📄 Transaction: {tx.tx_hash[:20]}...')
            print(f'     Block: {tx.block_number}')
            print(f'     From: {tx.from_address[:16]}...')
            print(f'     To: {tx.to_address[:16] if tx.to_address else "Contract Creation"}...')
            print(f'     Value: {tx.value / 1e18:.6f} ETH')
            print(f'     Gas Used: {tx.gas_used:,}' if tx.gas_used else '     Gas Used: N/A')
            print()

        # Type-safe aggregations
        print('📊 Aggregations (type-safe):')
        total_value = sum(tx.value for tx in transactions)
        total_gas = sum(tx.gas_used or 0 for tx in transactions)

        print(f'   Total Value Transferred: {total_value / 1e18:.6f} ETH')
        print(f'   Total Gas Used: {total_gas:,}')

        # Export to dict for JSON/CSV
        print('\n📤 Export to dict (for serialization):')
        if transactions:
            export = transactions[0].model_dump()
            print(f'   Fields: {list(export.keys())}')

    finally:
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
