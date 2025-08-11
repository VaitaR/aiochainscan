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
)
from aiochainscan.services.unified_fetch import fetch_all  # noqa: E402


async def fetch_all_transactions_optimized_demo(*, address: str) -> list[dict]:
    """Run both strategies for Blockscout and Etherscan (ETH) and print timings."""
    # Blockscout demo calls are commented below; keep placeholders local if uncommented later
    # api_kind = 'blockscout_eth'
    # network = 'eth'
    # api_key = ''

    # DI: default adapters
    # Use aggressive but bounded timeout to prevent long hangs
    http = AiohttpClient()
    endpoint = UrlBuilderEndpoint()
    telemetry = StructlogTelemetry()
    # rate_limiter = SimpleRateLimiter(min_interval_seconds=0.0, burst=16)  # unthrottled for benchmark
    retry = ExponentialBackoffRetry(max_attempts=2, base_delay_seconds=0.2)

    try:
        txs_es_fast: list[dict] = []
        # print('--- Blockscout (fast) ---')
        # started = time.time()
        # print('sending batch: provider=blockscout_eth max_concurrent=16 offset=10000')
        # txs_bs_fast = await fetch_all_transactions_fast(
        #     address=address,
        #     start_block=None,
        #     end_block=None,
        #     api_kind=api_kind,
        #     network=network,
        #     api_key=api_key,
        #     http=http,
        #     endpoint_builder=endpoint,
        #     rate_limiter=rate_limiter,
        #     retry=retry,
        #     telemetry=telemetry,
        #     max_offset=10_000,
        #     max_concurrent=16,
        # )
        # elapsed = time.time() - started
        # print(f'duration_s={elapsed:.2f} items={len(txs_bs_fast)} tps={len(txs_bs_fast)/max(elapsed,1e-6):.1f}')

        # # Internal transactions (Blockscout, fast)
        # print('--- Blockscout internal (fast) ---')
        # started = time.time()
        # print('sending batch: internal fast (blockscout_eth)')
        # internals_bs_fast = await fetch_all_internal_fast(
        #     address=address,
        #     start_block=None,
        #     end_block=None,
        #     api_kind=api_kind,
        #     network=network,
        #     api_key=api_key,
        #     http=http,
        #     endpoint_builder=endpoint,
        #     rate_limiter=rate_limiter,
        #     retry=retry,
        #     telemetry=telemetry,
        #     max_offset=10_000,
        #     max_concurrent=8,
        # )
        # elapsed = time.time() - started
        # print(f'duration_s={elapsed:.2f} items={len(internals_bs_fast)} tps={len(internals_bs_fast)/max(elapsed,1e-6):.1f}')

        # # ERC-20 transfers (Blockscout, fast)
        # print('--- Blockscout ERC20 (fast) ---')
        # started = time.time()
        # print('sending batch: erc20 fast (blockscout_eth)')
        # erc20_bs_fast = await fetch_all_token_transfers_fast(
        #     address=address,
        #     start_block=None,
        #     end_block=None,
        #     api_kind=api_kind,
        #     network=network,
        #     api_key=api_key,
        #     http=http,
        #     endpoint_builder=endpoint,
        #     rate_limiter=rate_limiter,
        #     retry=retry,
        #     telemetry=telemetry,
        #     max_offset=10_000,
        #     max_concurrent=8,
        #     token_standard='erc20',
        # )
        # elapsed = time.time() - started
        # print(f'duration_s={elapsed:.2f} items={len(erc20_bs_fast)} tps={len(erc20_bs_fast)/max(elapsed,1e-6):.1f}')

        # Etherscan test (requires ETHERSCAN_KEY)
        print('--- Etherscan (fast sliding bi-directional) ---')
        import os

        eth_key = os.getenv('ETHERSCAN_KEY', '')
        if eth_key:
            started = time.time()
            print('sending batch: etherscan sliding_bi (max_offset=10000, page=1)')
            txs_es_fast = await fetch_all(
                data_type='transactions',
                address=address,
                start_block=0,
                end_block=None,
                api_kind='eth',
                network='main',
                api_key=eth_key,
                http=http,
                endpoint_builder=endpoint,
                rate_limiter=SimpleRateLimiter(min_interval_seconds=0.2, burst=1),  # 5 rps
                retry=retry,
                telemetry=telemetry,
                strategy='fast',
                max_offset=10_000,
                max_concurrent=1,
            )
            elapsed = time.time() - started
            print(
                f'duration_s={elapsed:.2f} items={len(txs_es_fast)} tps={len(txs_es_fast)/max(elapsed,1e-6):.1f}'
            )

        #     # Internal transactions (Etherscan-style sliding, using fast engine policy)
        #     print('--- Etherscan internal (sliding fast) ---')
        #     started = time.time()
        #     print('sending batch: internal fast (eth) sliding window')
        #     internals_es_fast = await fetch_all_internal_fast(
        #         address=address,
        #         start_block=0,
        #         end_block=None,
        #         api_kind='eth',
        #         network='main',
        #         api_key=eth_key,
        #         http=http,
        #         endpoint_builder=endpoint,
        #         rate_limiter=SimpleRateLimiter(min_interval_seconds=0.2, burst=1),
        #         retry=retry,
        #         telemetry=telemetry,
        #         max_offset=10_000,
        #         max_concurrent=1,
        #     )
        #     elapsed = time.time() - started
        #     print(f'duration_s={elapsed:.2f} items={len(internals_es_fast)} tps={len(internals_es_fast)/max(elapsed,1e-6):.1f}')

        #     # ERC-20 transfers (Etherscan, fast engine policy)
        #     print('--- Etherscan ERC20 (fast) ---')
        #     started = time.time()
        #     print('sending batch: erc20 fast (eth) sliding window')
        #     erc20_es_fast = await fetch_all_token_transfers_fast(
        #         address=address,
        #         start_block=0,
        #         end_block=None,
        #         api_kind='eth',
        #         network='main',
        #         api_key=eth_key,
        #         http=http,
        #         endpoint_builder=endpoint,
        #         rate_limiter=SimpleRateLimiter(min_interval_seconds=0.2, burst=1),
        #         retry=retry,
        #         telemetry=telemetry,
        #         max_offset=10_000,
        #         max_concurrent=1,
        #         token_standard='erc20',
        #     )
        #     elapsed = time.time() - started
        #     print(f'duration_s={elapsed:.2f} items={len(erc20_es_fast)} tps={len(erc20_es_fast)/max(elapsed,1e-6):.1f}')
        # else:
        #     print('ETHERSCAN_KEY not set; skipping etherscan test')

        # Return latest etherscan fast result (Blockscout demo is commented above)
        return txs_es_fast
    finally:
        # Always close the HTTP session even on errors
        await http.aclose()


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
        print(f'error: {type(e).__name__}: {e!r}')


if __name__ == '__main__':
    asyncio.run(main())
