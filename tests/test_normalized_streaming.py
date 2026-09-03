"""Composition test: normalized models + guaranteed-complete pagination together.

The two headline features (Track C completeness, Track D normalized models)
were built independently and never proven to compose — see
``docs/V1_PLAN.md`` "Status (2026-09-02)", open item 1. This file proves the
composition, not merely that both shapes exist:

- the ``iter_*_normalized`` / ``get_all_*_normalized`` paths yield normalized
  model instances, not dicts;
- run against the SAME truncating stub scanner the pagination-guarantee
  tests use, they still recover the complete record set under
  ``guarantee_complete=True`` and still truncate (proving the guard is real,
  not vacuous) under ``guarantee_complete=False``;
- normalization happens batch-by-batch as data streams in, never after the
  full raw list has been collected (the constant-memory claim).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import patch

import pytest

from aiochainscan.chain_registry import resolve_scanner_target
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.streaming import STREAMING_SPECS_BY_NAME
from aiochainscan.domain.normalized import InternalTransaction, Log, TokenTransfer, Transaction

WINDOW = 50
"""Stub result window; small enough to overflow with a handful of pages."""


class TruncatingExplorer:
    """Page/offset explorer that silently stops at ``result_window`` records.

    Mirrors the ``TruncatingExplorer`` of the pagination-guarantee tests
    (kept as a separate copy so this file stands alone) — a request for
    ``[start_block, end_block]`` sees only the first ``result_window`` matching
    records, exactly the silent-truncation failure mode Track C exists for.
    Items carry every field the ``domain.normalize`` mappers read for
    transactions/token-transfers/internal-transactions/logs so normalization
    is exercised on realistic shapes, not bare stubs.
    """

    def __init__(self, blocks: dict[int, int], result_window: int = WINDOW) -> None:
        self.result_window = result_window
        self.items: list[dict[str, Any]] = [
            {
                'blockNumber': str(block),
                'hash': f'0x{block:064x}{index:0x}',
                'transactionHash': f'0x{block:064x}{index:0x}',
                'from': '0x0000000000000000000000000000000000000001',
                'to': '0x0000000000000000000000000000000000000002',
                'value': str(1000 + index),
                'timeStamp': str(1_700_000_000 + block),
                'logIndex': str(index),
                'topics': ['0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'],
                'data': '0x',
                'id': f'{block}-{index}',
            }
            for block in sorted(blocks)
            for index in range(blocks[block])
        ]
        self.requests: list[tuple[int, int, int]] = []

    @property
    def all_ids(self) -> list[str]:
        return [item['id'] for item in self.items]

    async def fetch(
        self, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        start = int(params['start_block'])
        end = int(params['end_block'])
        page = int(params.get('page', 1))
        offset = int(params['offset'])
        self.requests.append((start, end, page))

        matching = [item for item in self.items if start <= int(item['blockNumber']) <= end]
        served = matching[: self.result_window]
        lo = (page - 1) * offset
        chunk = served[lo : lo + offset]
        cursor = {'page': page + 1, 'offset': offset} if len(chunk) == offset else None
        return chunk, cursor


def spread(blocks: range, per_block: int) -> dict[int, int]:
    return dict.fromkeys(blocks, per_block)


class _StubScanner:
    """Minimal page provider with a declared result window."""

    def __init__(self, explorer: TruncatingExplorer) -> None:
        self.explorer = explorer
        self.result_window = explorer.result_window

    def supports_block_range(self, method: Any) -> bool:
        return True  # emulates an Etherscan-like provider (ranged specs)

    async def fetch_page(
        self, method: Any, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        return await self.explorer.fetch(params)


@pytest.fixture
def stub_client() -> tuple[ChainscanClient, TruncatingExplorer]:
    explorer = TruncatingExplorer(spread(range(0, 26), per_block=5))
    with patch('aiochainscan.core.client.get_scanner_class'):
        client = ChainscanClient(resolve_scanner_target('etherscan', 'ethereum', api_key='key'))
    client._scanner = _StubScanner(explorer)  # type: ignore[assignment]
    return client, explorer


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_transactions_normalized_is_complete_by_default(
    stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    client, explorer = stub_client

    txs = await client.get_all_transactions_normalized('0xABC', from_block=0, to_block=999)

    # (a) normalized model instances, not dicts
    assert all(isinstance(tx, Transaction) for tx in txs)
    # (b) completeness recovered despite the stub's WINDOW=50 cap per range
    assert [tx.provider_data['id'] for tx in txs] == explorer.all_ids
    assert len(txs) > WINDOW


@pytest.mark.asyncio
async def test_get_all_transactions_normalized_opt_out_still_truncates(
    stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    """The guard is non-vacuous: turning it off must still lose data here."""
    client, explorer = stub_client

    txs = await client.get_all_transactions_normalized(
        '0xABC', from_block=0, to_block=999, guarantee_complete=False
    )

    assert all(isinstance(tx, Transaction) for tx in txs)
    assert len(txs) == WINDOW
    assert len(txs) < len(explorer.all_ids)


@pytest.mark.asyncio
async def test_iter_transactions_normalized_yields_normalized_batches(
    stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    client, explorer = stub_client

    seen: list[Transaction] = []
    async for batch in client.iter_transactions_normalized(
        '0xABC', from_block=0, to_block=999, batch_size=10
    ):
        assert all(isinstance(tx, Transaction) for tx in batch)
        assert len(batch) <= 10
        seen.extend(batch)

    assert [tx.provider_data['id'] for tx in seen] == explorer.all_ids


@pytest.mark.asyncio
async def test_normalization_happens_per_batch_not_after_full_collection(
    stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    """Constant-memory claim, made observable: ``normalize_transaction`` must
    be called again after *every* fetch, not only once at the very end after
    every page has been retrieved. If normalization ran on the fully
    collected raw list, every ``normalize_transaction`` call would land after
    the LAST fetch — this test fails in that case.

    The spy wraps the twin row's ``normalizer`` in the streaming registry
    (the seam ``stream_normalized_batches`` reads per batch); the spec is
    frozen, so the spied row is swapped in via ``patch.dict``.
    """
    client, explorer = stub_client
    calls_after_fetch_count: list[int] = []

    spec = STREAMING_SPECS_BY_NAME['iter_transactions_normalized']
    real_normalize = spec.normalizer

    def spy(item: Any) -> Transaction:
        calls_after_fetch_count.append(len(explorer.requests))
        return real_normalize(item)  # type: ignore[misc, call-arg]

    with patch.dict(
        STREAMING_SPECS_BY_NAME,
        {'iter_transactions_normalized': replace(spec, normalizer=spy)},
    ):
        await client.get_all_transactions_normalized('0xABC', from_block=0, to_block=999)

    total_fetches = len(explorer.requests)
    assert total_fetches > 1, 'stub setup must produce multiple pages to be a real test'
    assert calls_after_fetch_count, 'the spy must observe the normalizer actually running'
    # Some normalize_transaction calls must have happened while fewer than
    # the total number of fetches had occurred yet — i.e. normalization
    # interleaves with fetching rather than following it.
    assert any(count < total_fetches for count in calls_after_fetch_count)


# ---------------------------------------------------------------------------
# Token transfers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_token_transfers_normalized_is_complete_by_default(
    stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    client, explorer = stub_client

    transfers = await client.get_all_token_transfers_normalized(
        '0xABC', from_block=0, to_block=999
    )

    assert all(isinstance(t, TokenTransfer) for t in transfers)
    assert [t.provider_data['id'] for t in transfers] == explorer.all_ids


@pytest.mark.asyncio
async def test_get_all_token_transfers_normalized_opt_out_still_truncates(
    stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    client, explorer = stub_client

    transfers = await client.get_all_token_transfers_normalized(
        '0xABC', from_block=0, to_block=999, guarantee_complete=False
    )

    assert len(transfers) == WINDOW
    assert len(transfers) < len(explorer.all_ids)


# ---------------------------------------------------------------------------
# Internal transactions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_internal_transactions_normalized_is_complete_by_default(
    stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    client, explorer = stub_client

    itxs = await client.get_all_internal_transactions_normalized(
        '0xABC', from_block=0, to_block=999
    )

    assert all(isinstance(itx, InternalTransaction) for itx in itxs)
    assert [itx.provider_data['id'] for itx in itxs] == explorer.all_ids


@pytest.mark.asyncio
async def test_get_all_internal_transactions_normalized_opt_out_still_truncates(
    stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    client, explorer = stub_client

    itxs = await client.get_all_internal_transactions_normalized(
        '0xABC', from_block=0, to_block=999, guarantee_complete=False
    )

    assert len(itxs) == WINDOW
    assert len(itxs) < len(explorer.all_ids)


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


class _LogsStubScanner:
    """Minimal page provider for EVENT_LOGS (from_block/to_block params)."""

    def __init__(self, explorer: TruncatingExplorer) -> None:
        self.explorer = explorer
        self.result_window = explorer.result_window

    def supports_block_range(self, method: Any) -> bool:
        return True  # emulates an Etherscan-like provider (ranged specs)

    async def fetch_page(
        self, method: Any, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        remapped = {
            'start_block': params['from_block'],
            'end_block': params['to_block'],
            'page': params.get('page', 1),
            'offset': params['offset'],
        }
        return await self.explorer.fetch(remapped)


@pytest.fixture
def logs_stub_client() -> tuple[ChainscanClient, TruncatingExplorer]:
    explorer = TruncatingExplorer(spread(range(0, 26), per_block=5))
    with patch('aiochainscan.core.client.get_scanner_class'):
        client = ChainscanClient(resolve_scanner_target('etherscan', 'ethereum', api_key='key'))
    client._scanner = _LogsStubScanner(explorer)  # type: ignore[assignment]
    return client, explorer


@pytest.mark.asyncio
async def test_get_all_logs_normalized_is_complete_by_default(
    logs_stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    client, explorer = logs_stub_client

    logs = await client.get_all_logs_normalized('0xABC', from_block=0, to_block=999)

    assert all(isinstance(log, Log) for log in logs)
    assert [log.provider_data['id'] for log in logs] == explorer.all_ids


@pytest.mark.asyncio
async def test_get_all_logs_normalized_opt_out_still_truncates(
    logs_stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    client, explorer = logs_stub_client

    logs = await client.get_all_logs_normalized(
        '0xABC', from_block=0, to_block=999, guarantee_complete=False
    )

    assert len(logs) == WINDOW
    assert len(logs) < len(explorer.all_ids)
