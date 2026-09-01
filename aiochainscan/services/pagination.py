"""Deep pagination engine for aiochainscan.

ONE module owning every paginated loop in the codebase. Built on a structural
page-provider seam:

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

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from ..core.types import JSONDict
from ..domain.method import Method
from ..exceptions import ChainscanDataError
from ..ports.progress import ProgressCallback

logger = logging.getLogger(__name__)

__all__ = [
    'Cursor',
    'ItemDecode',
    'PageFetch',
    'collect_all',
    'iter_items',
    'iter_pages',
    'normalize_items',
    'page_fetcher',
    'validate_batch_size',
]

type Cursor = dict[str, Any] | None
"""Opaque page cursor; ``None`` terminates pagination."""

type PageFetch = Callable[[dict[str, Any]], Awaitable[tuple[list[JSONDict], Cursor]]]
"""Async page fetch: params in, ``(items, next_cursor)`` out."""

type ItemDecode = Callable[[JSONDict], JSONDict]
"""Per-item hook applied when flattening batches (e.g. ABI decoding)."""


def validate_batch_size(batch_size: int) -> None:
    """Validate the positive page size required by public streaming methods."""
    if batch_size < 1:
        raise ValueError(f'batch_size must be at least 1, got {batch_size}')


def _request_fingerprint(params: dict[str, Any]) -> str:
    """Create a deterministic fingerprint for a JSON-like request state."""
    try:
        return json.dumps(params, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ChainscanDataError(
            'Pagination request parameters must be JSON-like to detect cursor cycles.'
        ) from exc


@runtime_checkable
class PageProvider(Protocol):
    """Structural port for fetching one page and its opaque next cursor."""

    async def fetch_page(
        self, method: Method, params: dict[str, Any]
    ) -> tuple[list[JSONDict], Cursor]: ...


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


def page_fetcher(provider: PageProvider, method: Method) -> PageFetch:
    """Bind a page provider and method into a :data:`PageFetch`.

    Every page fetch flows through the provider's injected Network client (so
    retries apply per page fetch).

    Args:
        provider: Object satisfying the local page-provider protocol.
        method: Logical method to execute for every page.

    Returns:
        A :data:`PageFetch` callable taking params and returning
        ``(items, next_cursor)``.
    """

    async def fetch(params: dict[str, Any]) -> tuple[list[JSONDict], Cursor]:
        return await provider.fetch_page(method, params)

    return fetch


async def iter_pages(
    fetch: PageFetch,
    params: dict[str, Any],
    *,
    on_progress: ProgressCallback | None = None,
    operation: str = 'fetch',
) -> AsyncIterator[list[JSONDict]]:
    """Iterate over all pages, yielding one batch per non-empty page.

    Loop invariant (identical for every caller):

    1. Fetch a page via ``fetch(params)``.
    2. An empty page produces no yield or progress callback.
    3. Accumulate the fetched count and invoke ``on_progress`` (if given)
       *before* yielding the batch.
    4. Continue iff the scanner returned a cursor. Merge it into ``params``;
       if that does not change the request parameters, raise a data error.
    5. Advance the page counter.

    Args:
        fetch: Async page fetch (see :func:`page_fetcher`).
        params: Initial request params; may include ``page``/``offset`` for
            page-numbered APIs. Non-``None`` cursors are merged on top.
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
    seen_states: set[str] = set()
    while True:
        fingerprint = _request_fingerprint(params)
        if fingerprint in seen_states:
            raise ChainscanDataError('Pagination cursor repeats a prior request state.')
        seen_states.add(fingerprint)

        items, cursor = await fetch(params)
        if items:
            fetched += len(items)
            if on_progress is not None:
                try:
                    await on_progress(
                        fetched=fetched,
                        total_expected=None,
                        current_page=page,
                        operation=operation,
                    )
                except Exception:
                    logger.warning(
                        'Progress callback failed during pagination; continuing.',
                        exc_info=True,
                    )
            yield items
        if cursor is None:
            return
        next_params = {**params, **cursor}
        if next_params == params:
            raise ChainscanDataError('Pagination cursor does not advance request parameters.')
        params = next_params
        page += 1


async def iter_items(
    fetch: PageFetch,
    params: dict[str, Any],
    *,
    decode: ItemDecode | None = None,
) -> AsyncIterator[JSONDict]:
    """Iterate over all items one by one (flattened batches).

    ``decode`` is applied lazily per item at yield time — items already
    consumed survive a decode failure on a later item, matching the
    historical per-item iteration semantics.

    Args:
        fetch: Async page fetch (see :func:`page_fetcher`).
        params: Initial request params (cursor-merged per page).
        decode: Optional per-item hook (e.g. ABI decoding). Receives the raw
            item and must return the item to yield.

    Yields:
        Item dictionaries (decoded when ``decode`` is given).
    """
    async for batch in iter_pages(fetch, params):
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
