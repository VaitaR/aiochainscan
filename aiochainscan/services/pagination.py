"""Deep pagination engine for aiochainscan.

ONE module owning every paginated loop in the codebase. Built on the
``Scanner.fetch_page`` seam (the cursor contract from ``scanners/base.py``):

- a page fetch returns ``(items, next_cursor)``;
- ``next_cursor is None`` terminates pagination;
- a non-``None`` cursor is opaque and merges into the next request's params
  (``{**params, **cursor}``).

Public interface:

- :func:`normalize_items` — coerce a parsed response into a list of items.
- :func:`page_fetcher` — bind a scanner and a method into a :data:`PageFetch`.
- :func:`iter_pages` — async generator yielding page batches.
- :func:`iter_items` — async generator yielding single items (flattened,
  with an optional per-item decode hook).
- :func:`collect_all` — materialize batches into one list with the
  large-aggregation warning.

Every ``iter_*``/``get_all_*`` convenience method on ``ChainscanClient`` is a
thin wrapper over this engine; page-fetch level retries stay in the Network
layer (each :data:`PageFetch` call lands there), never at generator level.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal

from ..core.method import Method
from ..core.types import JSONDict
from ..ports.progress import ProgressCallback
from ..scanners.base import Scanner

__all__ = [
    'Cursor',
    'ItemDecode',
    'PageFetch',
    'StopMode',
    'collect_all',
    'iter_items',
    'iter_pages',
    'normalize_items',
    'page_fetcher',
]

type Cursor = dict[str, Any] | None
"""Opaque page cursor; ``None`` terminates pagination."""

type PageFetch = Callable[[dict[str, Any]], Awaitable[tuple[list[JSONDict], Cursor]]]
"""Async page fetch: params in, ``(items, next_cursor)`` out."""

type ItemDecode = Callable[[JSONDict], JSONDict]
"""Per-item hook applied when flattening batches (e.g. ABI decoding)."""

type StopMode = Literal['cursor', 'page_size']
"""When to stop paginating (see :func:`iter_pages`)."""


def normalize_items(response: Any) -> list[JSONDict]:
    """Coerce a parsed API response into a list of item dicts.

    Accepts the shapes explorers actually return: a plain list, an envelope
    dict with an ``'items'`` key, or anything else (treated as no data).

    Args:
        response: Parsed response from ``Scanner.call`` or similar.

    Returns:
        List of item dictionaries (possibly empty; never ``None``).
    """
    if isinstance(response, list):
        return list(response)
    if isinstance(response, dict):
        items = response.get('items')
        return list(items) if items else []
    return []


def page_fetcher(scanner: Scanner, method: Method) -> PageFetch:
    """Bind ``scanner`` and ``method`` into a :data:`PageFetch`.

    The only sanctioned bridge between the engine and the scanner port: every
    page fetch flows through ``Scanner.fetch_page``, which routes through the
    scanner's injected Network client (so retries apply per page fetch).

    Args:
        scanner: Scanner instance carrying the cursor logic.
        method: Logical method to execute for every page.

    Returns:
        A :data:`PageFetch` callable taking params and returning
        ``(items, next_cursor)``.
    """

    async def fetch(params: dict[str, Any]) -> tuple[list[JSONDict], Cursor]:
        return await scanner.fetch_page(method, params)

    return fetch


async def iter_pages(
    fetch: PageFetch,
    params: dict[str, Any],
    *,
    stop: StopMode = 'cursor',
    page_size: int | None = None,
    on_progress: ProgressCallback | None = None,
    operation: str = 'fetch',
) -> AsyncIterator[list[JSONDict]]:
    """Iterate over all pages, yielding one batch per non-empty page.

    Loop invariant (identical for every caller):

    1. Fetch a page via ``fetch(params)``.
    2. An empty page terminates silently (no yield, no progress).
    3. Accumulate the fetched count and invoke ``on_progress`` (if given)
       *before* yielding the batch.
    4. Decide whether another page follows:

       - ``stop='cursor'``: continue iff the scanner returned a cursor
         (the scanner is the sole pagination authority).
       - ``stop='page_size'``: additionally stop when the page was short
         (``len(items) < page_size``) even if a cursor was returned — the
         classic "last page is partial" heuristic, kept for callers whose
         params pin an explicit ``page``/``offset`` window.

    5. Merge the cursor into ``params`` and advance the page counter.

    Args:
        fetch: Async page fetch (see :func:`page_fetcher`).
        params: Initial request params; may include ``page``/``offset`` for
            page-numbered APIs. Non-``None`` cursors are merged on top.
        stop: Stop strategy; ``'page_size'`` requires ``page_size``.
        page_size: Page size used for the short-page check and progress
            accounting context (required when ``stop='page_size'``).
        on_progress: Optional callback invoked once per non-empty page with
            ``(fetched, total_expected=None, current_page, operation)``.
        operation: Operation label forwarded to ``on_progress``.

    Yields:
        Batches (lists) of item dictionaries.

    Raises:
        Any exception raised by ``fetch`` propagates unchanged.
    """
    page = 1
    fetched = 0
    while True:
        items, cursor = await fetch(params)
        if not items:
            return
        fetched += len(items)
        if on_progress is not None:
            await on_progress(
                fetched=fetched,
                total_expected=None,
                current_page=page,
                operation=operation,
            )
        yield items
        if stop == 'page_size':
            if cursor is None or (page_size is not None and len(items) < page_size):
                return
        elif cursor is None:
            return
        params = {**params, **cursor}
        page += 1


async def iter_items(
    fetch: PageFetch,
    params: dict[str, Any],
    *,
    stop: StopMode = 'cursor',
    page_size: int | None = None,
    decode: ItemDecode | None = None,
) -> AsyncIterator[JSONDict]:
    """Iterate over all items one by one (flattened batches).

    ``decode`` is applied lazily per item at yield time — items already
    consumed survive a decode failure on a later item, matching the
    historical per-item iteration semantics.

    Args:
        fetch: Async page fetch (see :func:`page_fetcher`).
        params: Initial request params (cursor-merged per page).
        stop: Stop strategy (see :func:`iter_pages`).
        page_size: Page size for the ``'page_size'`` stop strategy.
        decode: Optional per-item hook (e.g. ABI decoding). Receives the raw
            item and must return the item to yield.

    Yields:
        Item dictionaries (decoded when ``decode`` is given).
    """
    async for batch in iter_pages(fetch, params, stop=stop, page_size=page_size):
        for item in batch:
            yield decode(item) if decode is not None else item


async def collect_all(
    batches: AsyncIterator[list[JSONDict]],
    *,
    threshold: int,
    warning: str,
    logger: logging.Logger,
) -> list[JSONDict]:
    """Materialize batches into one list, warning at the memory threshold.

    The aggregation half of the engine: extends the result with every batch
    and logs ``warning`` exactly once when the accumulated length *hits*
    ``threshold`` (the historical ``len(items) == threshold`` trigger).

    Args:
        batches: Async iterator of batches (typically an ``iter_*_streaming``
            generator).
        threshold: Item count at which the warning fires.
        warning: Complete warning message to log.
        logger: Logger used for the warning (caller's module logger).

    Returns:
        All items from all batches, in order.
    """
    items: list[JSONDict] = []
    async for batch in batches:
        items.extend(batch)
        if len(items) == threshold:
            logger.warning(warning)
    return items
