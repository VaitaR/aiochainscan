"""Unit tests for the pagination engine (``aiochainscan/services/pagination.py``).

Covers the small public surface over the ``Scanner.fetch_page`` seam:
- ``normalize_items`` — response → items coercion
- ``page_fetcher`` — binding a scanner port into a PageFetch
- ``iter_pages`` — batch iteration, cursor merging, stop conditions, progress
- ``iter_items`` — flattening + per-item decode hook
- ``collect_all`` — materialization + 100k aggregation warning
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from aiochainscan.domain.method import Method
from aiochainscan.exceptions import ChainscanDataError
from aiochainscan.scanners.base import Scanner
from aiochainscan.services.pagination import (
    collect_all,
    iter_items,
    iter_pages,
    normalize_items,
    page_fetcher,
)


class FakePageFetch:
    """Scripted PageFetch: records params, replays (items, cursor) pages."""

    def __init__(self, pages: list[tuple[list[dict[str, Any]], dict[str, Any] | None]]) -> None:
        self.pages = list(pages)
        self.seen_params: list[dict[str, Any]] = []

    async def __call__(self, params: dict[str, Any]) -> tuple[list[dict[str, Any]], Any]:
        self.seen_params.append(dict(params))
        if not self.pages:
            raise AssertionError('fetched more pages than the fake provides')
        return self.pages.pop(0)


class ProgressRecorder:
    """Async progress callback recording its keyword calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class FakeScanner(Scanner):
    """Minimal scanner whose fetch_page is a recorded stub."""

    name = 'fake'
    version = 'test'
    supported_networks = {'main'}

    def __init__(self, pages: list[tuple[list[dict[str, Any]], dict[str, Any] | None]]) -> None:
        self.fetch = FakePageFetch(pages)

    async def fetch_page(  # type: ignore[override]
        self, method: Method, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        assert method == Method.ACCOUNT_TRANSACTIONS
        return await self.fetch(params)


# ---------------------------------------------------------------------------
# normalize_items
# ---------------------------------------------------------------------------


class TestNormalizeItems:
    def test_list_passthrough(self) -> None:
        items = [{'a': 1}]
        assert normalize_items(items) == items
        assert normalize_items(items) is not items  # defensive copy

    def test_dict_with_items(self) -> None:
        assert normalize_items({'items': [{'x': 1}, {'x': 2}]}) == [{'x': 1}, {'x': 2}]

    def test_dict_without_items(self) -> None:
        assert normalize_items({'foo': 'bar'}) == []

    def test_dict_with_empty_items(self) -> None:
        assert normalize_items({'items': []}) == []

    def test_dict_with_none_items(self) -> None:
        assert normalize_items({'items': None}) == []

    def test_scalar_response(self) -> None:
        assert normalize_items('No records found') == []

    def test_none_response(self) -> None:
        assert normalize_items(None) == []


# ---------------------------------------------------------------------------
# page_fetcher
# ---------------------------------------------------------------------------


class TestPageFetcher:
    @pytest.mark.asyncio
    async def test_binds_scanner_and_method(self) -> None:
        scanner = FakeScanner([([{'h': 1}], None)])
        fetch = page_fetcher(scanner, Method.ACCOUNT_TRANSACTIONS)

        items, cursor = await fetch({'address': '0xabc'})

        assert items == [{'h': 1}]
        assert cursor is None
        assert scanner.fetch.seen_params == [{'address': '0xabc'}]

    @pytest.mark.asyncio
    async def test_cursor_returned_verbatim(self) -> None:
        cursor = {'page': 2, 'offset': 50}
        scanner = FakeScanner([([{'h': 1}], cursor)])
        fetch = page_fetcher(scanner, Method.ACCOUNT_TRANSACTIONS)

        _, next_cursor = await fetch({'page': 1, 'offset': 50})

        assert next_cursor == cursor


# ---------------------------------------------------------------------------
# iter_pages: cursor mode
# ---------------------------------------------------------------------------


class TestIterPagesCursorMode:
    @pytest.mark.asyncio
    async def test_yields_batches_in_order_and_stops_on_none_cursor(self) -> None:
        fetch = FakePageFetch(
            [
                ([{'h': 1}, {'h': 2}], {'page': 2}),
                ([{'h': 3}], None),
            ]
        )

        batches: list[list[dict[str, Any]]] = []
        async for batch in iter_pages(fetch, {'address': '0xabc'}):
            batches.append(batch)

        assert batches == [[{'h': 1}, {'h': 2}], [{'h': 3}]]

    @pytest.mark.asyncio
    async def test_cursor_merges_into_next_params(self) -> None:
        fetch = FakePageFetch(
            [
                ([{'h': 1}], {'page': 2, 'keep': 'x'}),
                ([{'h': 2}], None),
            ]
        )

        async for _ in iter_pages(fetch, {'address': '0xabc', 'page': 1}):
            pass

        assert fetch.seen_params[0] == {'address': '0xabc', 'page': 1}
        assert fetch.seen_params[1] == {'address': '0xabc', 'page': 2, 'keep': 'x'}

    @pytest.mark.asyncio
    async def test_empty_first_page_stops_without_yield(self) -> None:
        fetch = FakePageFetch([([], None)])

        batches = [batch async for batch in iter_pages(fetch, {})]

        assert batches == []
        assert len(fetch.seen_params) == 1

    @pytest.mark.asyncio
    async def test_cursor_none_after_items_stops(self) -> None:
        fetch = FakePageFetch([([{'h': 1}], None)])

        batches = [batch async for batch in iter_pages(fetch, {})]

        assert batches == [[{'h': 1}]]
        assert len(fetch.seen_params) == 1

    @pytest.mark.asyncio
    async def test_fetch_exception_propagates(self) -> None:
        class ExplodingFetch:
            async def __call__(self, params: dict[str, Any]) -> Any:
                raise RuntimeError('boom')

        with pytest.raises(RuntimeError, match='boom'):
            async for _ in iter_pages(ExplodingFetch(), {}):  # type: ignore[arg-type]
                pass


# ---------------------------------------------------------------------------
# iter_pages: cursor integrity
# ---------------------------------------------------------------------------


class TestIterPagesCursorIntegrity:
    @pytest.mark.asyncio
    async def test_short_page_with_cursor_continues(self) -> None:
        fetch = FakePageFetch(
            [
                ([{'h': 1}], {'page': 2}),
                ([{'h': 2}], None),
            ]
        )

        batches = [batch async for batch in iter_pages(fetch, {'page': 1, 'offset': 10})]

        assert batches == [[{'h': 1}], [{'h': 2}]]
        assert len(fetch.seen_params) == 2
        assert fetch.seen_params[1]['page'] == 2

    @pytest.mark.asyncio
    async def test_empty_page_with_cursor_continues_without_yield_or_progress(self) -> None:
        fetch = FakePageFetch([([], {'page': 2}), ([{'h': 2}], None)])
        progress = ProgressRecorder()

        batches = [batch async for batch in iter_pages(fetch, {'page': 1}, on_progress=progress)]

        assert batches == [[{'h': 2}]]
        assert fetch.seen_params == [{'page': 1}, {'page': 2}]
        assert progress.calls == [
            {
                'fetched': 1,
                'total_expected': None,
                'current_page': 2,
                'operation': 'fetch',
            }
        ]

    @pytest.mark.asyncio
    async def test_repeated_cursor_raises_data_error_after_non_empty_page(self) -> None:
        fetch = FakePageFetch(
            [
                ([{'h': 1}], {'page': 2}),
                ([{'h': 2}], {'page': 2}),
            ]
        )

        batches: list[list[dict[str, Any]]] = []
        with pytest.raises(ChainscanDataError, match='does not advance'):
            async for batch in iter_pages(fetch, {'page': 1}):
                batches.append(batch)

        assert batches == [[{'h': 1}], [{'h': 2}]]
        assert len(fetch.seen_params) == 2

    @pytest.mark.asyncio
    async def test_cursor_cycle_raises_before_duplicate_request(self) -> None:
        fetch = FakePageFetch(
            [
                ([{'h': 1}], {'cursor': {'state': ['b']}}),
                ([{'h': 2}], {'cursor': {'state': ['a']}}),
            ]
        )

        batches: list[list[dict[str, Any]]] = []
        with pytest.raises(ChainscanDataError, match='repeats'):
            async for batch in iter_pages(fetch, {'cursor': {'state': ['a']}}):
                batches.append(batch)

        assert batches == [[{'h': 1}], [{'h': 2}]]
        assert len(fetch.seen_params) == 2


# ---------------------------------------------------------------------------
# progress callback
# ---------------------------------------------------------------------------


class TestIterPagesProgress:
    @pytest.mark.asyncio
    async def test_progress_called_per_page_before_yield(self) -> None:
        fetch = FakePageFetch(
            [
                ([{'h': 1}, {'h': 2}], {'page': 2}),
                ([{'h': 3}], None),
            ]
        )
        progress = ProgressRecorder()

        seen_sizes: list[int] = []
        async for batch in iter_pages(fetch, {}, on_progress=progress, operation='transactions'):
            seen_sizes.append(len(batch))

        assert seen_sizes == [2, 1]
        assert progress.calls == [
            {
                'fetched': 2,
                'total_expected': None,
                'current_page': 1,
                'operation': 'transactions',
            },
            {
                'fetched': 3,
                'total_expected': None,
                'current_page': 2,
                'operation': 'transactions',
            },
        ]

    @pytest.mark.asyncio
    async def test_no_progress_on_empty_page_or_default_operation(self) -> None:
        fetch = FakePageFetch([([{'h': 1}], None)])
        progress = ProgressRecorder()

        async for _ in iter_pages(fetch, {}, on_progress=progress):
            pass

        assert len(progress.calls) == 1
        assert progress.calls[0]['operation'] == 'fetch'

    @pytest.mark.asyncio
    async def test_no_callback_no_crash(self) -> None:
        fetch = FakePageFetch([([{'h': 1}], None)])

        batches = [batch async for batch in iter_pages(fetch, {})]

        assert batches == [[{'h': 1}]]

    @pytest.mark.asyncio
    async def test_progress_callback_failure_does_not_stop_page_delivery(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        fetch = FakePageFetch(
            [
                ([{'h': 1}], {'page': 2}),
                ([{'h': 2}], None),
            ]
        )

        async def failing_progress(**_kwargs: Any) -> None:
            raise RuntimeError('progress failed')

        with caplog.at_level(logging.WARNING):
            batches = [
                batch
                async for batch in iter_pages(
                    fetch, {'page': 1}, on_progress=failing_progress, operation='transactions'
                )
            ]

        assert batches == [[{'h': 1}], [{'h': 2}]]
        assert 'Progress callback failed during pagination' in caplog.text


# ---------------------------------------------------------------------------
# iter_items
# ---------------------------------------------------------------------------


class TestIterItems:
    @pytest.mark.asyncio
    async def test_flattens_batches_across_pages(self) -> None:
        fetch = FakePageFetch(
            [
                ([{'h': 1}, {'h': 2}], {'page': 2}),
                ([{'h': 3}], None),
            ]
        )

        items = [item async for item in iter_items(fetch, {})]

        assert items == [{'h': 1}, {'h': 2}, {'h': 3}]

    @pytest.mark.asyncio
    async def test_decode_applied_per_item_in_order(self) -> None:
        fetch = FakePageFetch([([{'h': 1}, {'h': 2}], None)])

        def decode(item: dict[str, Any]) -> dict[str, Any]:
            return {**item, 'decoded': True}

        items = [item async for item in iter_items(fetch, {}, decode=decode)]

        assert items == [
            {'h': 1, 'decoded': True},
            {'h': 2, 'decoded': True},
        ]

    @pytest.mark.asyncio
    async def test_no_decode_yields_originals(self) -> None:
        original = {'h': 1}
        fetch = FakePageFetch([([original], None)])

        items = [item async for item in iter_items(fetch, {})]

        assert items == [original]
        assert items[0] is original


# ---------------------------------------------------------------------------
# collect_all
# ---------------------------------------------------------------------------


class TestCollectAll:
    @pytest.mark.asyncio
    async def test_concatenates_batches_in_order(self) -> None:
        async def batches() -> Any:
            yield [{'h': 1}, {'h': 2}]
            yield [{'h': 3}]

        result = await collect_all(
            batches(),
            threshold=100_000,
            warning='w',
            logger=logging.getLogger('test'),
        )

        assert result == [{'h': 1}, {'h': 2}, {'h': 3}]

    @pytest.mark.asyncio
    async def test_warning_fires_exactly_when_hitting_threshold(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def batches() -> Any:
            yield [{'h': 1}, {'h': 2}]
            yield [{'h': 3}, {'h': 4}]

        with caplog.at_level(logging.WARNING, logger='test'):
            result = await collect_all(
                batches(),
                threshold=4,
                warning='Aggregating >100k items in memory.',
                logger=logging.getLogger('test'),
            )

        assert len(result) == 4
        assert caplog.text.count('Aggregating >100k items in memory.') == 1

    @pytest.mark.asyncio
    async def test_no_warning_below_threshold(self, caplog: pytest.LogCaptureFixture) -> None:
        async def batches() -> Any:
            yield [{'h': 1}]

        with caplog.at_level(logging.WARNING, logger='test'):
            await collect_all(
                batches(),
                threshold=100,
                warning='never',
                logger=logging.getLogger('test'),
            )

        assert 'never' not in caplog.text

    @pytest.mark.asyncio
    async def test_warning_not_repeated_after_threshold(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def batches() -> Any:
            yield [{'h': i} for i in range(2)]
            yield [{'h': i} for i in range(2, 4)]
            yield [{'h': 4}]

        with caplog.at_level(logging.WARNING, logger='test'):
            result = await collect_all(
                batches(),
                threshold=4,
                warning='once',
                logger=logging.getLogger('test'),
            )

        assert len(result) == 5
        assert caplog.text.count('once') == 1

    @pytest.mark.asyncio
    async def test_empty_stream_returns_empty_list(self) -> None:
        async def batches() -> Any:
            return
            yield  # pragma: no cover

        result = await collect_all(
            batches(),
            threshold=10,
            warning='w',
            logger=logging.getLogger('test'),
        )

        assert result == []
