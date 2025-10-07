"""Integration test that exercises the Blockscout flow end-to-end.

This test talks to the public Polygon Blockscout instance. It downloads the
full log history for a busy contract, resolves the correct ABI (including the
proxy implementation when applicable) and decodes both logs and transaction
inputs to ensure that most payloads can be interpreted correctly.

The contract under test (0x34beb65E41F6f0A36275Fe85F4f4574CE9237231) has more
than two thousand emitted logs which makes it a good stress case for the
batched pagination helpers.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

import pytest

pytest.importorskip(
    'aiohttp',
    reason='Blockscout end-to-end flow exercises the aiohttp transport dependency',
)

from aiochainscan import Client
from aiochainscan.exceptions import ChainscanClientApiError
from aiochainscan.decode import decode_log_data, decode_transaction_input
from aiochainscan.modules.base import _facade_injection, _resolve_api_context
from aiochainscan.services.fetch_all import fetch_all_logs_basic, fetch_all_logs_fast

CONTRACT_ADDRESS = '0x34beb65E41F6f0A36275Fe85F4f4574CE9237231'


async def _resolve_contract_abi(client: Client, address: str) -> list[dict[str, object]]:
    """Fetch contract ABI, following the proxy implementation if needed."""

    source_entries = await client.contract.contract_source_code(address=address)
    implementation = next(
        (
            entry.get('Implementation')
            for entry in source_entries
            if isinstance(entry, dict) and entry.get('Implementation')
        ),
        None,
    )

    abi_target = implementation or address
    abi_raw = await client.contract.contract_abi(address=abi_target)
    assert abi_raw and abi_raw != 'Contract source code not verified'

    # Blockscout returns ABI as JSON encoded string
    abi = json.loads(abi_raw)
    assert isinstance(abi, list)
    return abi


def _decode_logs(logs: Iterable[dict[str, object]], abi: list[dict[str, object]]) -> tuple[int, int]:
    decoded = 0
    total = 0
    for log in logs:
        total += 1
        enriched = decode_log_data(dict(log), abi)
        if enriched.get('decoded_data'):
            decoded += 1
    return decoded, total


async def _decode_transactions(
    client: Client, tx_hashes: Iterable[str], abi: list[dict[str, object]],
) -> tuple[int, int]:
    decoded = 0
    total = 0
    for tx_hash in tx_hashes:
        tx = await client.transaction.get_by_hash(tx_hash)
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
async def test_blockscout_polygon_logs_and_decoding() -> None:
    client = Client.from_config('blockscout_polygon', 'polygon')
    try:
        http_adapter, endpoint_builder = _facade_injection(client)
        api_kind, network, api_key = _resolve_api_context(client)

        logs = await _fetch_blockscout_logs(
            client=client,
            address=CONTRACT_ADDRESS,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http_adapter,
            endpoint_builder=endpoint_builder,
        )

        assert len(logs) > 2_000

        abi = await _resolve_contract_abi(client, CONTRACT_ADDRESS)

        decoded_logs, total_logs = _decode_logs(logs, abi)
        assert total_logs == len(logs)
        assert decoded_logs / total_logs >= 0.7

        unique_tx_hashes = {
            hash_value
            for log in logs
            for hash_value in [log.get('transactionHash')]
            if isinstance(hash_value, str)
        }
        decoded_txs, total_txs = await _decode_transactions(
            client, list(unique_tx_hashes)[:50], abi
        )

        # Ensure we decoded a substantial portion of the sampled transactions
        assert total_txs >= 10
        assert decoded_txs / total_txs >= 0.6
    finally:
        await client.close()


async def _fetch_blockscout_logs(
    *,
    client: Client,
    address: str,
    api_kind: str,
    network: str,
    api_key: str,
    http,
    endpoint_builder,
) -> list[dict[str, object]]:
    try:
        logs = await fetch_all_logs_fast(
            address=address,
            start_block=0,
            end_block=None,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            endpoint_builder=endpoint_builder,
            rate_limiter=None,
            retry=None,
            telemetry=None,
            max_offset=1_000,
            max_concurrent=4,
        )
    except ChainscanClientApiError as exc:
        if _is_no_logs_error(exc):
            logs = await fetch_all_logs_basic(
                address=address,
                start_block=0,
                end_block=None,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                endpoint_builder=endpoint_builder,
                rate_limiter=None,
                retry=None,
                telemetry=None,
                max_offset=1_000,
            )
        else:
            raise

    if logs:
        return logs

    # Slow-path fallback that pages through the REST endpoint when the paged helpers
    # report an empty result set (Blockscout occasionally responds with empty pages
    # even when data exists).
    results: list[dict[str, object]] = []
    page = 1
    while True:
        try:
            page_logs = await client.logs.get_logs(
                start_block=0,
                end_block='latest',
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
