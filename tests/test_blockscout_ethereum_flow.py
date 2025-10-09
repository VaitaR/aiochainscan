"""Integration test that exercises the Blockscout flow end-to-end for Ethereum.

This test talks to the public Ethereum Blockscout instance. It downloads the
full log history for a busy contract, resolves the correct ABI (including the
proxy implementation when applicable) and decodes both logs and transaction
inputs to ensure that most payloads can be interpreted correctly.

The contract under test is USDT on Ethereum mainnet (0xdac17f958d2ee523a2206206994597c13d831ec7)
which has an enormous amount of transfer events making it a good stress case for
the batched pagination helpers.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

import pytest

pytest.importorskip(
    'aiohttp',
    reason='Blockscout end-to-end flow exercises the aiohttp transport dependency',
)

from aiochainscan.core.client import ChainscanClient  # noqa: E402
from aiochainscan.core.method import Method  # noqa: E402
from aiochainscan.decode import decode_log_data, decode_transaction_input  # noqa: E402
from aiochainscan.exceptions import ChainscanClientApiError  # noqa: E402

# Removed old fetch_all functions - using new unified interface

# USDT contract on Ethereum mainnet - very active contract with lots of events
CONTRACT_ADDRESS = '0xdac17f958d2ee523a2206206994597c13d831ec7'


async def _resolve_contract_abi(client: ChainscanClient, address: str) -> list[dict[str, object]]:
    """Fetch contract ABI, following the proxy implementation if needed."""

    source_entries = await client.call(Method.CONTRACT_SOURCE, address=address)
    implementation = next(
        (
            entry.get('Implementation')
            for entry in source_entries
            if isinstance(entry, dict) and entry.get('Implementation')
        ),
        None,
    )

    abi_target = implementation or address
    abi_raw = await client.call(Method.CONTRACT_ABI, address=abi_target)
    assert abi_raw and abi_raw != 'Contract source code not verified'

    # Blockscout returns ABI as JSON encoded string
    abi = json.loads(abi_raw)
    assert isinstance(abi, list)
    return abi


def _decode_logs(
    logs: Iterable[dict[str, object]], abi: list[dict[str, object]]
) -> tuple[int, int]:
    decoded = 0
    total = 0
    for log in logs:
        total += 1
        enriched = decode_log_data(dict(log), abi)
        if enriched.get('decoded_data'):
            decoded += 1
    return decoded, total


async def _decode_transactions(
    client: ChainscanClient,
    tx_hashes: Iterable[str],
    abi: list[dict[str, object]],
) -> tuple[int, int]:
    decoded = 0
    total = 0
    for tx_hash in tx_hashes:
        tx = await client.call(Method.TX_BY_HASH, txhash=tx_hash)
        if not isinstance(tx, dict):
            continue

        input_data = tx.get('input')
        if not isinstance(input_data, str) or len(input_data) <= 2:
            continue

        total += 1
        enriched = decode_transaction_input(dict(tx), abi)
        if enriched.get('decoded_func'):
            decoded += 1
    return decoded, total


@pytest.mark.asyncio
@pytest.mark.slow  # E2E test with real API calls
@pytest.mark.integration  # Requires network access
async def test_blockscout_ethereum_logs_and_decoding() -> None:
    """Test Blockscout Ethereum flow with USDT contract (E2E).

    This is an end-to-end integration test that:
    - Talks to real Blockscout Ethereum API
    - Fetches logs from USDT contract (highly active)
    - Tests decoding functionality with real data

    Note: This test fetches logs from a limited block range due to the
    extremely high activity of the USDT contract. Even a small range
    will provide plenty of data to test the decoding functionality.

    Marked as 'slow' and 'integration' to run separately from unit tests.
    Skipped by default - run explicitly with: pytest -m integration
    """
    try:
        client = ChainscanClient.from_config('blockscout', 'v1', 'ethereum')
    except ValueError as e:
        pytest.skip(f'Blockscout ETH configuration not available: {e}')
        return

    try:
        # Get latest block and use recent range to avoid timeout
        # USDT is extremely active, so even 100 blocks will give us many logs
        try:
            latest_block_info = await client.call(Method.BLOCK_BY_NUMBER, block_number='latest')
            latest_block = int(latest_block_info['number'], 16)
        except ChainscanClientApiError as e:
            if 'unknown module' in str(e).lower():
                pytest.skip(f"Blockscout Ethereum API doesn't support proxy module: {e}")
            raise

        # Use last 100 blocks to keep test fast and avoid timeout
        start_block = latest_block - 100

        logs = await _fetch_blockscout_logs_new(
            client=client,
            address=CONTRACT_ADDRESS,
            start_block=start_block,
            end_block=latest_block,
        )

        # USDT should have many transfer events even in a small block range
        assert len(logs) > 100, f'Expected at least 100 logs, got {len(logs)}'

        abi = await _resolve_contract_abi(client, CONTRACT_ADDRESS)

        decoded_logs, total_logs = _decode_logs(logs, abi)
        assert total_logs == len(logs)
        # USDT Transfer events should decode well
        assert decoded_logs / total_logs >= 0.7, (
            f'Expected at least 70% decode rate, got {decoded_logs}/{total_logs} '
            f'= {decoded_logs / total_logs:.1%}'
        )

        unique_tx_hashes = {
            hash_value
            for log in logs
            for hash_value in [log.get('transactionHash')]
            if isinstance(hash_value, str)
        }

        # Sample a subset of transactions to avoid rate limiting
        sample_size = min(30, len(unique_tx_hashes))
        decoded_txs, total_txs = await _decode_transactions(
            client, list(unique_tx_hashes)[:sample_size], abi
        )

        # Ensure we decoded a substantial portion of the sampled transactions
        assert total_txs >= 10, f'Expected at least 10 transactions, got {total_txs}'
        assert decoded_txs / total_txs >= 0.5, (
            f'Expected at least 50% decode rate, got {decoded_txs}/{total_txs} '
            f'= {decoded_txs / total_txs:.1%}'
        )
    finally:
        await client.close()


async def _fetch_blockscout_logs_new(
    *,
    client: ChainscanClient,
    address: str,
    start_block: int = 0,
    end_block: int | None = None,
) -> list[dict[str, object]]:
    # Use the new unified interface with pagination
    results: list[dict[str, object]] = []
    page = 1
    while True:
        try:
            page_logs = await client.call(
                Method.EVENT_LOGS,
                start_block=start_block,
                end_block=end_block or 'latest',
                address=address,
                page=page,
                offset=200,
            )
        except ChainscanClientApiError as exc:
            if _is_no_logs_error(exc):
                break
            raise

        if not isinstance(page_logs, list) or not page_logs:
            break

        results.extend([entry for entry in page_logs if isinstance(entry, dict)])
        if len(page_logs) < 200:
            break
        page += 1

    return results


def _is_no_logs_error(exc: ChainscanClientApiError) -> bool:
    message = (exc.message or '').lower() if exc.message else ''
    return 'no logs found' in message or 'no records found' in message
