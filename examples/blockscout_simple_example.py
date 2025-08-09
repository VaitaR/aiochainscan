#!/usr/bin/env python3
"""
Blockscout fetch-all example (technical, minimal output)
"""

import asyncio
import sys
import time
from contextlib import suppress
from pathlib import Path

# Allow running directly from the repo without installation
_REPO_ROOT = Path(__file__).resolve().parents[1]
if (_REPO_ROOT / 'aiochainscan').exists():  # first-party
    sys.path.insert(0, str(_REPO_ROOT))

from aiochainscan import (  # noqa: E402  (import after sys.path tweak)
    AiohttpClient,
    ExponentialBackoffRetry,
    SimpleRateLimiter,
    StructlogTelemetry,
    UrlBuilderEndpoint,
    get_all_transactions_optimized,
)


async def fetch_all_transactions_optimized_demo(*, address: str) -> list[dict]:
    """Call fetch-all facade (services layer, Blockscout)."""
    api_kind = 'blockscout_eth'
    network = 'eth'
    api_key = ''

    # DI: default adapters
    http = AiohttpClient()
    endpoint = UrlBuilderEndpoint()
    telemetry = StructlogTelemetry()
    # Blockscout ~10 rps → minimal interval 0.1s
    rate_limiter = SimpleRateLimiter(min_interval_seconds=0.1)
    retry = ExponentialBackoffRetry(max_attempts=3, base_delay_seconds=0.3)

    stats: dict[str, int] = {}
    started = time.time()
    txs = await get_all_transactions_optimized(
        address=address,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        endpoint_builder=endpoint,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        max_concurrent=5,
        max_offset=10_000,
        min_range_width=1_000,
        max_attempts_per_range=3,
        stats=stats,
    )
    elapsed = time.time() - started

    # Derived metrics
    rps = len(txs) / elapsed if elapsed > 0 and txs else 0.0
    print('\nPerformance summary')
    print(f'duration_s={elapsed:.2f}')
    print(f'items={len(txs)}')
    print(f'throughput_tps={rps:.1f}')
    if stats:
        print('ranges:')
        print(f'  seeded={stats.get("ranges_seeded", 0)}')
        print(f'  processed={stats.get("ranges_processed", 0)}')
        print(f'  split={stats.get("ranges_split", 0)}')
        print(f'  retries={stats.get("retries", 0)}')
        print(f'  errors={stats.get("errors", 0)}')
        print(f'  failed={stats.get("ranges_failed", 0)}')
        print(f'  items_total={stats.get("items_total", 0)}')
    await http.aclose()
    return txs


async def analyze_all_transactions(transactions):
    """Minimal technical summary over fetched transactions."""
    if not transactions:
        return

    total_value = 0
    total_gas = 0
    unique_from = set()
    unique_to = set()
    contract_calls = 0
    simple_transfers = 0

    for tx in transactions:
        # Values
        if 'value' in tx:
            with suppress(ValueError, TypeError):
                total_value += int(tx['value'])

        # Gas
        if 'gasUsed' in tx:
            with suppress(ValueError, TypeError):
                total_gas += int(tx['gasUsed'])

        # Unique addresses
        if 'from' in tx:
            unique_from.add(tx['from'])
        if 'to' in tx:
            unique_to.add(tx['to'])

        # Transaction type
        if 'input' in tx:
            if tx['input'] == '0x' or tx['input'] == '':
                simple_transfers += 1
            else:
                contract_calls += 1

    total_eth = total_value / 10**18

    print('\nResult summary')
    print(f'total_txs={len(transactions)}')
    print(f'total_value_eth={total_eth:.6f}')
    print(f'total_gas={total_gas}')
    print(f'unique_from={len(unique_from)}')
    print(f'unique_to={len(unique_to)}')
    print(f'simple_transfers={simple_transfers}')
    print(f'contract_calls={contract_calls}')

    # Первая/последняя транзакции
    if len(transactions) > 0:
        first_tx = transactions[0]
        value_eth = int(first_tx.get('value', 0)) / 10**18
        print('first_tx:')
        print(f'  hash={first_tx.get("hash", "N/A")}')
        print(f'  block={first_tx.get("blockNumber", "N/A")}')
        print(f'  value_eth={value_eth:.6f}')

        if len(transactions) > 1:
            last_tx = transactions[-1]
            value_eth = int(last_tx.get('value', 0)) / 10**18
            print('last_tx:')
            print(f'  hash={last_tx.get("hash", "N/A")}')
            print(f'  block={last_tx.get("blockNumber", "N/A")}')
            print(f'  value_eth={value_eth:.6f}')


async def main():
    """Main entrypoint."""
    # Address
    address = '0x8236a87084f8B84306f72007F36F2618A5634494'
    print(f'start: provider=blockscout_eth network=eth address={address}')

    try:
        # Получаем ВСЕ транзакции оптимизированным сервисом
        start_time = time.time()
        all_transactions = await fetch_all_transactions_optimized_demo(address=address)
        duration = time.time() - start_time
        print(f'done: duration_s={duration:.2f}')

        await analyze_all_transactions(all_transactions)
    except Exception as e:
        print(f'error: {e}')


if __name__ == '__main__':
    asyncio.run(main())
