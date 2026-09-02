"""Guaranteed-complete pagination: adaptive range splitting and its guard.

The stub explorer here reproduces the failure mode the feature exists for: a
page/offset REST API that serves at most ``result_window`` records for a block
range and then stops **without any error**. Every test that claims the guard
works is paired with the same stub run in legacy mode, which loses data — so
the guarded assertions cannot pass vacuously.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from aiochainscan.constants import API_MAX_OFFSET_ETHERSCAN
from aiochainscan.core.client import ChainscanClient
from aiochainscan.exceptions import (
    CompletenessUnavailableError,
    PaginationDataLossError,
)
from aiochainscan.scanners._etherscan_like import EtherscanLikeScanner
from aiochainscan.scanners.base import Scanner
from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner
from aiochainscan.scanners.nodereal import NodeRealScanner
from aiochainscan.services.pagination import (
    PaginationContext,
    detect_block_range,
    iter_pages,
    split_window,
)

WINDOW = 50
"""Stub result window; small enough to overflow with a handful of pages."""


class TruncatingExplorer:
    """Page/offset explorer that silently stops at ``result_window`` records.

    ``blocks`` maps a block number to how many records it holds. A request for
    ``[startblock, endblock]`` sees only the first ``result_window`` matching
    records — exactly the silent truncation an Etherscan-family
    ``page * offset`` cap produces.
    """

    def __init__(self, blocks: dict[int, int], result_window: int = WINDOW) -> None:
        self.result_window = result_window
        self.items: list[dict[str, Any]] = [
            {'blockNumber': str(block), 'id': f'{block}-{index}'}
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
        start = int(params['startblock'])
        end = int(params['endblock'])
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


async def drain(agen: Any) -> list[dict[str, Any]]:
    return [item for batch in [b async for b in agen] for item in batch]


BASE_PARAMS: dict[str, Any] = {
    'address': '0xABC',
    'startblock': 0,
    'endblock': 999,
    'page': 1,
    'offset': 10,
    'sort': 'asc',
}


# ---------------------------------------------------------------------------
# Non-vacuity: the stub really does lose data without the guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_mode_truncates_silently() -> None:
    """Without the guarantee the stub returns a truncated set and no error."""
    explorer = TruncatingExplorer(spread(range(0, 26), per_block=5))  # 130 records
    assert len(explorer.all_ids) == 130

    collected = await drain(iter_pages(explorer.fetch, dict(BASE_PARAMS)))

    assert len(collected) == WINDOW  # 50 of 130 — the loss this track removes
    assert len(collected) < len(explorer.all_ids)


# ---------------------------------------------------------------------------
# The split path recovers the complete set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guarantee_recovers_every_record() -> None:
    explorer = TruncatingExplorer(spread(range(0, 26), per_block=5))

    collected = await drain(
        iter_pages(
            explorer.fetch,
            dict(BASE_PARAMS),
            guarantee_complete=True,
            result_window=explorer.result_window,
        )
    )

    ids = [item['id'] for item in collected]
    assert ids == explorer.all_ids  # complete, ordered, no duplicates


@pytest.mark.asyncio
async def test_guarantee_splits_adaptively_not_by_fixed_width() -> None:
    """Ranges requested after the first overflow are data-driven, not uniform."""
    explorer = TruncatingExplorer(spread(range(0, 26), per_block=5))

    await drain(
        iter_pages(
            explorer.fetch,
            dict(BASE_PARAMS),
            guarantee_complete=True,
            result_window=explorer.result_window,
        )
    )

    ranges = [(start, end) for start, end, _page in explorer.requests]
    assert ranges[0] == (0, 999)
    narrowed = {r for r in ranges if r != (0, 999)}
    assert narrowed, 'no narrower window was requested — nothing was split'
    widths = {end - start for start, end in narrowed}
    assert len(widths) > 1, f'windows are uniform width, not adaptive: {narrowed}'


@pytest.mark.asyncio
async def test_guarantee_is_inert_below_the_cap() -> None:
    """A range that fits under the cap is served without any extra request."""
    explorer = TruncatingExplorer({1: 4, 2: 3})

    guarded = await drain(
        iter_pages(
            explorer.fetch,
            dict(BASE_PARAMS),
            guarantee_complete=True,
            result_window=explorer.result_window,
        )
    )

    assert [item['id'] for item in guarded] == explorer.all_ids
    assert explorer.requests == [(0, 999, 1)]


@pytest.mark.asyncio
async def test_progress_callback_counts_only_yielded_items() -> None:
    explorer = TruncatingExplorer(spread(range(0, 26), per_block=5))
    seen: list[int] = []

    async def on_progress(**kwargs: Any) -> None:
        seen.append(int(kwargs['fetched']))

    await drain(
        iter_pages(
            explorer.fetch,
            dict(BASE_PARAMS),
            guarantee_complete=True,
            result_window=explorer.result_window,
            on_progress=on_progress,
        )
    )

    assert seen == sorted(seen)
    assert seen[-1] == len(explorer.all_ids)  # discarded attempts are not counted


# ---------------------------------------------------------------------------
# The error fires when splitting is exhausted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whale_block_raises_pagination_data_loss() -> None:
    """One block over the cap cannot be narrowed — it must raise, not truncate."""
    explorer = TruncatingExplorer({7: WINDOW + 10})

    with pytest.raises(PaginationDataLossError) as excinfo:
        await drain(
            iter_pages(
                explorer.fetch,
                dict(BASE_PARAMS),
                guarantee_complete=True,
                result_window=explorer.result_window,
            )
        )

    error = excinfo.value
    assert error.start_block == 7
    assert error.end_block == 7
    assert error.block_number == 7
    assert error.api_limit == WINDOW
    assert error.items_fetched == WINDOW
    assert error.confirmed is True
    assert 'block 7' in str(error)
    assert 'PAGINATION DATA LOSS' in str(error)


@pytest.mark.asyncio
async def test_whale_block_inside_a_wide_range_still_raises() -> None:
    """The split walks down to the offending block before giving up."""
    explorer = TruncatingExplorer({3: 5, 11: WINDOW + 1, 20: 5})

    with pytest.raises(PaginationDataLossError) as excinfo:
        await drain(
            iter_pages(
                explorer.fetch,
                dict(BASE_PARAMS),
                guarantee_complete=True,
                result_window=explorer.result_window,
            )
        )

    assert excinfo.value.start_block == excinfo.value.end_block == 11


HOLDERS_PARAMS: dict[str, Any] = {'contract_address': '0xTOKEN', 'page': 1, 'offset': 10}


def rangeless_fetch(explorer: TruncatingExplorer) -> Any:
    """A holder-list endpoint: capped, and with no block range to narrow."""

    async def fetch(params: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        return await explorer.fetch({**params, 'startblock': 0, 'endblock': 999})

    return fetch


@pytest.mark.asyncio
async def test_rangeless_endpoint_raises_the_sibling_type_not_data_loss() -> None:
    """No splittable dimension is a different failure from a whale block."""
    explorer = TruncatingExplorer({1: WINDOW + 5})

    with pytest.raises(CompletenessUnavailableError) as excinfo:
        await drain(
            iter_pages(
                rangeless_fetch(explorer),
                dict(HOLDERS_PARAMS),
                guarantee_complete=True,
                result_window=explorer.result_window,
                context=PaginationContext(
                    method='TOKEN_HOLDERS',
                    provider='etherscan/v2',
                    alternatives=('blockscout/v2',),
                ),
            )
        )

    error = excinfo.value
    assert not isinstance(error, PaginationDataLossError)
    assert error.method == 'TOKEN_HOLDERS'
    assert error.provider == 'etherscan/v2'
    assert error.alternatives == ('blockscout/v2',)
    assert error.api_limit == WINDOW

    message = str(error)
    assert 'TOKEN_HOLDERS' in message
    assert 'etherscan/v2' in message
    assert 'blockscout/v2' in message  # names a provider that CAN serve it
    assert 'guarantee_complete=False' in message


@pytest.mark.asyncio
async def test_range_endpoint_still_raises_data_loss_when_splits_exhaust() -> None:
    """The ranged branch is unaffected by the rangeless one."""
    explorer = TruncatingExplorer({7: WINDOW + 10})

    with pytest.raises(PaginationDataLossError) as excinfo:
        await drain(
            iter_pages(
                explorer.fetch,
                dict(BASE_PARAMS),
                guarantee_complete=True,
                result_window=explorer.result_window,
                context=PaginationContext(
                    method='ACCOUNT_TRANSACTIONS',
                    provider='etherscan/v2',
                    alternatives=('blockscout/v2',),
                ),
            )
        )

    assert not isinstance(excinfo.value, CompletenessUnavailableError)
    assert excinfo.value.start_block == excinfo.value.end_block == 7


@pytest.mark.asyncio
async def test_rangeless_message_degrades_without_a_known_alternative() -> None:
    explorer = TruncatingExplorer({1: WINDOW + 5})

    with pytest.raises(CompletenessUnavailableError) as excinfo:
        await drain(
            iter_pages(
                rangeless_fetch(explorer),
                dict(HOLDERS_PARAMS),
                guarantee_complete=True,
                result_window=explorer.result_window,
                context=PaginationContext(method='TOKEN_HOLDERS', provider='etherscan/v2'),
            )
        )

    assert 'No registered provider' in str(excinfo.value)


def test_alternatives_are_computed_from_the_scanner_registry() -> None:
    """The suggestion is derived from declared capability, not hardcoded."""
    from aiochainscan.domain.method import Method as DomainMethod
    from aiochainscan.scanners import scanners_serving_completely

    assert scanners_serving_completely(DomainMethod.TOKEN_HOLDERS) == ('blockscout/v2',)
    # etherscan declares TOKEN_HOLDERS but has a result window, so it is excluded.
    assert 'etherscan/v2' not in scanners_serving_completely(DomainMethod.TOKEN_HOLDERS)


# ---------------------------------------------------------------------------
# Exactly at the cap: reported as unproven, not as loss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exactly_at_cap_without_continuation_is_reported_as_unproven() -> None:
    """Complete data must never be described as lost.

    ``offset=15`` does not divide ``WINDOW=50``, so the run ends on a partial
    page with no cursor: the provider offers no way to tell a complete result
    of exactly 50 from one capped at 50, and the message must say so.
    """
    explorer = TruncatingExplorer({7: WINDOW})
    params = {**BASE_PARAMS, 'offset': 15}

    with pytest.raises(PaginationDataLossError) as excinfo:
        await drain(
            iter_pages(
                explorer.fetch,
                params,
                guarantee_complete=True,
                result_window=explorer.result_window,
            )
        )

    error = excinfo.value
    assert error.confirmed is False
    message = str(error)
    assert 'POSSIBLY truncated' in message
    assert 'COMPLETENESS UNPROVEN' in message
    assert 'DATA LOSS' not in message


@pytest.mark.asyncio
async def test_rangeless_exactly_at_cap_is_reported_as_unproven() -> None:
    explorer = TruncatingExplorer({1: WINDOW})

    with pytest.raises(CompletenessUnavailableError) as excinfo:
        await drain(
            iter_pages(
                rangeless_fetch(explorer),
                {**HOLDERS_PARAMS, 'offset': 15},
                guarantee_complete=True,
                result_window=explorer.result_window,
                context=PaginationContext(method='TOKEN_HOLDERS', provider='etherscan/v2'),
            )
        )

    assert excinfo.value.confirmed is False
    assert 'possibly truncated at exactly the cap' in str(excinfo.value)


@pytest.mark.asyncio
async def test_confirmed_overflow_is_distinguished_from_at_cap() -> None:
    """A provider that offers a continuation at the cap is a confirmed loss."""
    explorer = TruncatingExplorer({7: WINDOW + 10})  # offset 10 divides 50

    with pytest.raises(PaginationDataLossError) as excinfo:
        await drain(
            iter_pages(
                explorer.fetch,
                dict(BASE_PARAMS),
                guarantee_complete=True,
                result_window=explorer.result_window,
            )
        )

    assert excinfo.value.confirmed is True


# ---------------------------------------------------------------------------
# Cursor-paginating providers must be untouched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_declared_window_keeps_the_plain_loop() -> None:
    """``result_window is None`` (BlockScout V2, NodeReal) never splits."""
    explorer = TruncatingExplorer(spread(range(0, 26), per_block=5))

    collected = await drain(
        iter_pages(explorer.fetch, dict(BASE_PARAMS), guarantee_complete=True, result_window=None)
    )

    assert len(collected) == WINDOW
    assert {(start, end) for start, end, _ in explorer.requests} == {(0, 999)}


def test_declared_result_windows_per_scanner() -> None:
    """Only the page/offset family declares a cap; cursor scanners declare none."""
    assert EtherscanLikeScanner.result_window == API_MAX_OFFSET_ETHERSCAN
    assert BlockScoutV2Scanner.result_window is None
    assert NodeRealScanner.result_window is None
    assert Scanner.result_window is None


# ---------------------------------------------------------------------------
# Range detection and split arithmetic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('params', 'expected'),
    [
        ({'startblock': 5, 'endblock': 9}, (5, 9)),
        ({'start_block': '5', 'end_block': '9'}, (5, 9)),
        ({'fromBlock': 5, 'toBlock': 9}, (5, 9)),
        ({'from_block': 5, 'to_block': 9}, (5, 9)),
    ],
)
def test_detect_block_range_spellings(params: dict[str, Any], expected: tuple[int, int]) -> None:
    detected = detect_block_range(params)
    assert detected is not None
    assert detected[1] == expected


def test_detect_block_range_treats_latest_as_the_tip() -> None:
    detected = detect_block_range({'fromBlock': 100, 'toBlock': 'latest'})
    assert detected is not None
    start, end = detected[1]
    assert start == 100
    assert end > 10**9  # MAX_BLOCK_NUMBER sentinel, still splittable


@pytest.mark.parametrize(
    'params',
    [
        {'contract_address': '0xTOKEN'},
        {'startblock': 9, 'endblock': 5},
        {'startblock': 'not-a-number', 'endblock': 5},
    ],
)
def test_detect_block_range_rejects_unsplittable(params: dict[str, Any]) -> None:
    assert detect_block_range(params) is None


def test_split_window_uses_the_observed_boundary() -> None:
    items = [{'blockNumber': '10'}, {'blockNumber': '40'}]
    assert split_window((0, 1000), items) == ((0, 39), (40, 1000))


def test_split_window_falls_back_to_bisect_without_block_numbers() -> None:
    assert split_window((0, 10), [{'no': 'block'}]) == ((0, 5), (6, 10))


def test_split_window_refuses_a_single_block() -> None:
    assert split_window((7, 7), [{'blockNumber': '7'}]) is None


def test_split_window_halves_are_strictly_narrower() -> None:
    """Termination invariant: each half is narrower than its parent."""
    for window, items in (
        ((0, 1000), [{'blockNumber': '1000'}]),
        ((0, 1000), [{'blockNumber': '0'}]),
        ((0, 1), [{'blockNumber': '0'}]),
    ):
        halves = split_window(window, items)
        assert halves is not None
        parent = window[1] - window[0]
        for start, end in halves:
            assert end - start < parent
            assert window[0] <= start <= end <= window[1]


# ---------------------------------------------------------------------------
# End to end through ChainscanClient
# ---------------------------------------------------------------------------


class _StubScanner:
    """Minimal page provider with a declared result window."""

    def __init__(self, explorer: TruncatingExplorer) -> None:
        self.explorer = explorer
        self.result_window = explorer.result_window

    async def fetch_page(
        self, method: Any, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        return await self.explorer.fetch(params)


@pytest.fixture
def stub_client() -> tuple[ChainscanClient, TruncatingExplorer]:
    explorer = TruncatingExplorer(spread(range(0, 26), per_block=5))
    with patch('aiochainscan.core.client.get_scanner_class'):
        client = ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'key')
    client._scanner = _StubScanner(explorer)  # type: ignore[assignment]
    return client, explorer


@pytest.mark.asyncio
async def test_client_get_all_transactions_is_complete_by_default(
    stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    client, explorer = stub_client

    txs = await client.get_all_transactions('0xABC', from_block=0, to_block=999)

    assert [tx['id'] for tx in txs] == explorer.all_ids


@pytest.mark.asyncio
async def test_client_opt_out_restores_legacy_truncation(
    stub_client: tuple[ChainscanClient, TruncatingExplorer],
) -> None:
    client, explorer = stub_client

    txs = await client.get_all_transactions(
        '0xABC', from_block=0, to_block=999, guarantee_complete=False
    )

    assert len(txs) == WINDOW
    assert len(txs) < len(explorer.all_ids)


class _HoldersStubScanner:
    """Holder-list provider with a result window and no block-range params."""

    def __init__(self, explorer: TruncatingExplorer) -> None:
        self.explorer = explorer
        self.result_window = explorer.result_window

    async def fetch_page(
        self, method: Any, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        return await self.explorer.fetch({**params, 'startblock': 0, 'endblock': 999})


@pytest.mark.asyncio
async def test_client_get_all_token_holders_names_a_working_provider() -> None:
    """The documented break: Etherscan holders now fails with a real remedy."""
    explorer = TruncatingExplorer({1: WINDOW + 20})
    with patch('aiochainscan.core.client.get_scanner_class'):
        client = ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'key')
    client._scanner = _HoldersStubScanner(explorer)  # type: ignore[assignment]

    with pytest.raises(CompletenessUnavailableError) as excinfo:
        await client.get_all_token_holders('0x' + 'ab' * 20)

    error = excinfo.value
    assert error.method == 'TOKEN_HOLDERS'
    assert error.provider == 'etherscan/v2'
    assert error.alternatives == ('blockscout/v2',)  # computed from the registry
    assert 'blockscout/v2' in str(error)


@pytest.mark.asyncio
async def test_client_token_holders_opt_out_still_truncates() -> None:
    """Opting out is the deliberate way to accept a truncated holder list."""
    explorer = TruncatingExplorer({1: WINDOW + 20})
    with patch('aiochainscan.core.client.get_scanner_class'):
        client = ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'key')
    client._scanner = _HoldersStubScanner(explorer)  # type: ignore[assignment]

    holders = await client.get_all_token_holders('0x' + 'ab' * 20, guarantee_complete=False)

    assert len(holders) == WINDOW
    assert len(holders) < len(explorer.all_ids)
