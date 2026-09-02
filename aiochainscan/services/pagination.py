"""Deep pagination engine for aiochainscan.

ONE cursor loop, built on a structural page-provider seam:

- a page fetch returns ``(items, next_cursor)``;
- ``next_cursor is None`` terminates pagination;
- a non-``None`` cursor is opaque and merges into the next request's params
  (``{**params, **cursor}``).

Everything paginated in the codebase consumes that one loop — including the
guaranteed-complete path (adaptive block-range splitting), which lives in
:mod:`aiochainscan.services.pagination_guarantee` and is re-exported here
for import compatibility.

Public interface:

- :func:`normalize_items` — coerce a parsed response into a list of items.
- :func:`page_fetcher` — bind a scanner and a method into a
  :class:`BoundPageFetch` (callable like :data:`PageFetch`, carrying the
  provider's ``result_window`` and an optional :class:`PaginationContext`).
- :func:`iter_pages` — async generator yielding page batches (the ONE
  cursor loop; delegates to :func:`iter_pages_complete` when
  ``guarantee_complete`` is set and a result window is known).
- :func:`iter_items` — async generator yielding single items (flattened,
  with an optional per-item decode hook).
- :func:`collect_all` — materialize batches into one list with the
  large-aggregation warning.
- Re-exported from :mod:`aiochainscan.services.pagination_guarantee`:
  :func:`iter_pages_complete`, :func:`detect_block_range`,
  :func:`split_window`, :class:`PaginationContext`, :data:`BlockRange`.

Request params speak the PUBLIC dialect (``start_block``/``end_block``,
``from_block``/``to_block``): scanner ``EndpointSpec.param_map``\\ s
translate public names to wire names, so no caller needs to know them.

Every ``iter_*``/``get_all_*`` convenience method on ``ChainscanClient`` is a
thin wrapper over this engine; page-fetch level retries stay in the Network
layer (each page fetch lands there), never at generator level.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..core.endpoint import coerce_response_items
from ..core.types import JSONDict
from ..domain.method import Method
from ..exceptions import ChainscanDataError
from ..ports.progress import ProgressCallback
from .pagination_guarantee import (
    BlockRange,
    PaginationContext,
    detect_block_range,
    iter_pages_complete,
    split_window,
)

logger = logging.getLogger(__name__)

__all__ = [
    'BlockRange',
    'BoundPageFetch',
    'Cursor',
    'PaginationContext',
    'ItemDecode',
    'PageFetch',
    'collect_all',
    'detect_block_range',
    'iter_items',
    'iter_pages',
    'iter_pages_complete',
    'normalize_items',
    'page_fetcher',
    'split_window',
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
    # Canonical implementation lives in core (importing scanners here would
    # break the layering this module documents); Scanner._coerce_items and
    # this wrapper are the same coercion, maintained once.
    return coerce_response_items(response)


@dataclass(frozen=True, slots=True)
class BoundPageFetch:
    """A :data:`PageFetch` plus the provider facts the guarantee path needs.

    ``iter_pages``/``iter_items`` read ``result_window`` and ``context``
    from the bound fetch unless the caller passes explicit ``result_window=``
    / ``context=`` overrides — so client call sites bind once (via
    :func:`page_fetcher`) and stop threading parallel kwargs into every
    engine call. Still callable exactly like a bare :data:`PageFetch`.

    Attributes:
        fetch: The underlying page fetch.
        result_window: The provider's ``page * offset`` cap, when it declares
            one (``Scanner.result_window``); ``None`` means "no window".
        context: Identity used for honest incompleteness error messages.
    """

    fetch: PageFetch
    result_window: int | None = None
    context: PaginationContext | None = None

    async def __call__(self, params: dict[str, Any]) -> tuple[list[JSONDict], Cursor]:
        return await self.fetch(params)


def page_fetcher(
    provider: PageProvider,
    method: Method,
    *,
    context: PaginationContext | None = None,
) -> BoundPageFetch:
    """Bind a page provider and method into a :class:`BoundPageFetch`.

    Every page fetch flows through the provider's injected Network client (so
    retries apply per page fetch). The provider's declared ``result_window``
    (when it exposes one — the :class:`~aiochainscan.scanners.base.Scanner`
    base always does) rides along on the binding, so guaranteed callers no
    longer thread it as a parallel kwarg; pass ``context=`` to name the
    method/provider in incompleteness errors.

    Args:
        provider: Object satisfying the local page-provider protocol.
        method: Logical method to execute for every page.
        context: Optional :class:`PaginationContext` for error messages.

    Returns:
        A :class:`BoundPageFetch` callable taking params and returning
        ``(items, next_cursor)``.
    """
    # ``result_window_for`` is the per-method window (a scanner may bound one
    # endpoint tighter than the rest); the plain attribute is the fallback for
    # page providers that predate it, e.g. test doubles.
    per_method = getattr(provider, 'result_window_for', None)
    declared: Any = (
        per_method(method) if callable(per_method) else getattr(provider, 'result_window', None)
    )
    result_window = declared if isinstance(declared, int) else None

    async def fetch(params: dict[str, Any]) -> tuple[list[JSONDict], Cursor]:
        return await provider.fetch_page(method, params)

    return BoundPageFetch(fetch=fetch, result_window=result_window, context=context)


def _resolve_binding(
    fetch: PageFetch,
    result_window: int | None,
    context: PaginationContext | None,
) -> tuple[int | None, PaginationContext | None]:
    """Fill unset engine kwargs from a :class:`BoundPageFetch`, if any.

    Explicit non-``None`` kwargs win over the binding; the binding wins over
    nothing at all (a bare callable fetch carries neither fact).
    """
    if isinstance(fetch, BoundPageFetch):
        if result_window is None:
            result_window = fetch.result_window
        if context is None:
            context = fetch.context
    return result_window, context


async def _notify_progress(
    on_progress: ProgressCallback | None,
    *,
    fetched: int,
    page: int,
    operation: str,
) -> None:
    """Invoke one progress callback, never letting a failure stop delivery.

    The single copy of the progress-callback block: the plain cursor loop
    (:func:`iter_pages`) and the guaranteed path
    (:func:`aiochainscan.services.pagination_guarantee.iter_pages_complete`)
    both route through here.
    """
    if on_progress is None:
        return
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


async def iter_pages(
    fetch: PageFetch,
    params: dict[str, Any],
    *,
    on_progress: ProgressCallback | None = None,
    operation: str = 'fetch',
    guarantee_complete: bool = False,
    result_window: int | None = None,
    context: PaginationContext | None = None,
) -> AsyncIterator[list[JSONDict]]:
    """Iterate over all pages, yielding one batch per non-empty page.

    Loop invariant (identical for every caller — this is the ONE cursor loop
    in the codebase):

    1. Fetch a page via ``fetch(params)``.
    2. An empty page produces no yield or progress callback.
    3. Accumulate the fetched count and invoke ``on_progress`` (if given)
       *before* yielding the batch.
    4. Continue iff the scanner returned a cursor. Merge it into ``params``;
       if that does not change the request parameters, raise a data error.
    5. Advance the page counter.

    Args:
        fetch: Async page fetch (see :func:`page_fetcher`). A
            :class:`BoundPageFetch` also supplies defaults for
            ``result_window``/``context`` when they are not passed.
        params: Initial request params; may include ``page``/``offset`` for
            page-numbered APIs. Non-``None`` cursors are merged on top.
        on_progress: Optional callback invoked once per non-empty page with
            ``(fetched, total_expected=None, current_page, operation)``.
        operation: Operation label forwarded to ``on_progress``.
        guarantee_complete: Enforce "every matching record, or an exception"
            by delegating to :func:`iter_pages_complete`. Requires
            ``result_window``; without one there is nothing to detect, and the
            plain loop runs (see ``Scanner.result_window``).
        result_window: The provider's ``page * offset`` cap, if it declares
            one. Overrides the value bound to ``fetch``.
        context: Forwarded to :func:`iter_pages_complete` for error messages.
            Overrides the value bound to ``fetch``.

    Yields:
        Batches (lists) of item dictionaries.

    Raises:
        Any exception raised by ``fetch`` propagates unchanged.
        PaginationDataLossError: Only in guaranteed mode, when a block range
            over the cap cannot be narrowed further.
        CompletenessUnavailableError: Only in guaranteed mode, when the request
            has no block range to narrow.
    """
    result_window, context = _resolve_binding(fetch, result_window, context)

    # ``isinstance`` rather than ``is not None``: a scanner double may expose a
    # non-numeric attribute, and the guaranteed path must never engage on one.
    if guarantee_complete and isinstance(result_window, int) and result_window > 0:
        async for guaranteed_batch in iter_pages_complete(
            fetch,
            params,
            result_window=result_window,
            on_progress=on_progress,
            operation=operation,
            context=context,
        ):
            yield guaranteed_batch
        return

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
            await _notify_progress(on_progress, fetched=fetched, page=page, operation=operation)
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
    guarantee_complete: bool = False,
    result_window: int | None = None,
    context: PaginationContext | None = None,
) -> AsyncIterator[JSONDict]:
    """Iterate over all items one by one (flattened batches).

    ``decode`` is applied lazily per item at yield time — items already
    consumed survive a decode failure on a later item, matching the
    historical per-item iteration semantics.

    Args:
        fetch: Async page fetch (see :func:`page_fetcher`). A
            :class:`BoundPageFetch` also supplies defaults for
            ``result_window``/``context`` when they are not passed.
        params: Initial request params (cursor-merged per page).
        decode: Optional per-item hook (e.g. ABI decoding). Receives the raw
            item and must return the item to yield.
        guarantee_complete: Forwarded to :func:`iter_pages`.
        result_window: Forwarded to :func:`iter_pages`.
        context: Forwarded to :func:`iter_pages`.

    Yields:
        Item dictionaries (decoded when ``decode`` is given).
    """
    result_window, context = _resolve_binding(fetch, result_window, context)
    async for batch in iter_pages(
        fetch,
        params,
        guarantee_complete=guarantee_complete,
        result_window=result_window,
        context=context,
    ):
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
