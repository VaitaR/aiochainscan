"""Deep pagination engine for aiochainscan.

ONE cursor loop, built on a structural page-provider seam:

- a page fetch returns ``(items, next_cursor)``;
- ``next_cursor is None`` terminates pagination;
- a non-``None`` cursor is opaque and merges into the next request's params
  (``{**params, **cursor}``).

The module is both halves of the engine. Where :func:`iter_pages` walks a
cursor until it runs dry, :func:`iter_pages_complete` adds the contract
*"every matching record was returned, or an exception was raised"* for
providers that cap what a single page/offset query can reach
(``Scanner.result_window``).

Design of the guaranteed path in one paragraph: a window is materialized
through the ONE cursor loop (:func:`iter_pages` — never a private
re-implementation) before anything is yielded, because a window that turns
out to have overflowed must be discarded and re-fetched as two narrower
windows; yielding first would duplicate items. Reaching the provider's
result window is the overflow signal — the weakest one that cannot be
fooled, since a capped explorer answers a partial page byte-identical to
the end of the data. The split point is *observed* (the block of the last
record the provider served), not fixed, and both halves are strictly
narrower, which is what makes the recursion terminate.

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
- :func:`iter_pages_complete` — the guaranteed generator.
- :func:`detect_block_range` — find the block-range params of a request.
- :func:`split_window` — adaptive two-way split of an overflowing range.
- :class:`PaginationContext` — who is being paginated, for honest errors.
- :data:`BlockRange` — inclusive ``(start_block, end_block)`` window.

Error contract of the guaranteed path:

- :class:`~aiochainscan.exceptions.PaginationDataLossError` — a single
  block still exceeds the cap (splitting worked and ran out).
- :class:`~aiochainscan.exceptions.CompletenessUnavailableError` — the
  endpoint has no splittable dimension at all on this provider.

Request params speak the PUBLIC dialect (``start_block``/``end_block``,
``from_block``/``to_block``): scanner ``EndpointSpec.param_map``\\ s
translate public names to wire names, so no caller needs to know them.
Wire spellings (``startblock``, ``fromBlock``, ...) belong to the scanners
and are translated before requests are built.

Every ``iter_*``/``get_all_*`` convenience method on ``ChainscanClient`` is a
thin wrapper over this engine; page-fetch level retries stay in the Network
layer (each page fetch lands there), never at generator level.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple, Protocol, runtime_checkable

from ..constants import MAX_BLOCK_NUMBER
from ..core.endpoint import coerce_response_items
from ..core.types import JSONDict
from ..domain.method import Method
from ..exceptions import (
    ChainscanDataError,
    CompletenessUnavailableError,
    PaginationDataLossError,
)
from ..ports.progress import ProgressCallback

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
    (:func:`iter_pages_complete`) both route through here.
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


# ---------------------------------------------------------------------------
# Guaranteed-complete pagination: adaptive block-range splitting
# ---------------------------------------------------------------------------

type BlockRange = tuple[int, int]
"""Inclusive ``(start_block, end_block)`` window."""


class _RangeKeys(NamedTuple):
    """The two param names carrying a block range for one request shape."""

    start: str
    end: str


#: Block-range param spellings recognized in engine params — the PUBLIC
#: dialect only. Wire spellings (``startblock``/``fromBlock``/...) are the
#: scanners' business: ``EndpointSpec.param_map`` translates public names to
#: wire names, so anything reaching this engine already speaks public names.
_BLOCK_RANGE_KEYS: tuple[_RangeKeys, ...] = (
    _RangeKeys('start_block', 'end_block'),
    _RangeKeys('from_block', 'to_block'),
)

#: Item fields holding a block number, in the order they are tried.
_ITEM_BLOCK_KEYS: tuple[str, ...] = ('blockNumber', 'block_number', 'block')


def _as_block_number(value: Any) -> int | None:
    """Coerce a block-range param or item field to an ``int``.

    ``'latest'``/``None`` mean "the chain tip", represented by
    :data:`MAX_BLOCK_NUMBER` so an unbounded end can still be split.
    Anything unrecognised returns ``None`` (treated as "cannot split").
    """
    if value is None or value == 'latest':
        return MAX_BLOCK_NUMBER
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 16) if text.lower().startswith('0x') else int(text)
        except ValueError:
            return None
    return None


def detect_block_range(params: dict[str, Any]) -> tuple[_RangeKeys, BlockRange] | None:
    """Find the block-range params of a request, if it has any.

    Returns the param names plus the resolved inclusive range, or ``None``
    when the request carries no splittable block range (token holders, or a
    range whose bounds cannot be parsed).
    """
    for keys in _BLOCK_RANGE_KEYS:
        if keys.start not in params or keys.end not in params:
            continue
        start = _as_block_number(params[keys.start])
        end = _as_block_number(params[keys.end])
        if start is None or end is None or end < start:
            return None
        return keys, (start, end)
    return None


def _item_block_number(item: JSONDict) -> int | None:
    """Block number of an item, or ``None`` if it carries none we recognise."""
    for key in _ITEM_BLOCK_KEYS:
        if key in item:
            return _as_block_number(item[key])
    return None


def split_window(
    window: BlockRange, items: list[JSONDict]
) -> tuple[BlockRange, BlockRange] | None:
    """Split an overflowing window into two, adaptively.

    The split point is *observed*, not fixed: the block of the last item the
    truncated page set returned bounds the part the provider was able to
    serve, so it is where the range is cut. Both halves are strictly narrower
    than ``window``, which is what makes the recursion terminate.

    Falls back to an arithmetic bisect when items carry no usable block
    number. Returns ``None`` when the window is a single block — the caller
    must then raise :class:`PaginationDataLossError` rather than truncate.
    """
    start, end = window
    if start >= end:
        return None

    boundary = _item_block_number(items[-1]) if items else None
    if boundary is not None and start < boundary <= end:
        return (start, boundary - 1), (boundary, end)

    mid = start + (end - start) // 2
    if start <= mid < end:
        return (start, mid), (mid + 1, end)
    return None


def _chunked(items: list[JSONDict], size: int) -> list[list[JSONDict]]:
    """Split a materialized window into caller-sized batches."""
    if size < 1:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


class _Overflow(Enum):
    """How a window ended relative to the provider's result window."""

    NONE = 'none'
    """Ended below the cap on the provider's own terms — complete."""

    CONFIRMED = 'confirmed'
    """Hit the cap with more records still offered — records are being lost."""

    AT_CAP = 'at_cap'
    """Ended exactly at the cap with no continuation — completeness unprovable."""


@dataclass(frozen=True, slots=True)
class PaginationContext:
    """Who is being paginated, so an incompleteness error can name names.

    The engine cannot reach the scanner registry (services must not import
    scanners), so the caller computes ``alternatives`` and passes it in.

    Attributes:
        method: Logical method name being paginated.
        provider: Label of the provider serving it.
        alternatives: Provider labels that can serve ``method`` completely.
    """

    method: str
    provider: str
    alternatives: tuple[str, ...] = ()


async def _fetch_window(
    fetch: PageFetch,
    params: dict[str, Any],
    *,
    result_window: int,
) -> tuple[list[JSONDict], _Overflow]:
    """Walk every page of one window; report whether it reached the result cap.

    The walk itself IS :func:`aiochainscan.services.pagination.iter_pages`
    (the one cursor loop in the codebase): the cycle guard, the
    does-not-advance check and the page fetch all live there. A thin wrapper
    only records the cursor of the most recent page so the overflow flavour
    can be told apart once the cap is reached:

    - :attr:`_Overflow.CONFIRMED` — the provider offered a next cursor at the
      cap, i.e. it says more records exist. Data is definitely being cut off.
    - :attr:`_Overflow.AT_CAP` — the window came back exactly full with no
      continuation. Possibly complete, possibly truncated; unprovable either
      way. No probe can settle it: the ambiguous case is precisely the one
      where the provider handed back no cursor, and cursors are opaque (see
      the module docstring), so there is nothing to request the next page
      with. Splitting resolves it for a ranged query; a rangeless one can
      only be reported as unproven.
    """
    collected: list[JSONDict] = []
    last_cursor: Cursor = None

    async def tracking_fetch(request: dict[str, Any]) -> tuple[list[JSONDict], Cursor]:
        nonlocal last_cursor
        items, cursor = await fetch(request)
        last_cursor = cursor
        return items, cursor

    async for batch in iter_pages(tracking_fetch, dict(params)):
        collected.extend(batch)
        if len(collected) >= result_window:
            return collected, _Overflow.CONFIRMED if last_cursor is not None else _Overflow.AT_CAP
    return collected, _Overflow.NONE


async def iter_pages_complete(
    fetch: PageFetch,
    params: dict[str, Any],
    *,
    result_window: int,
    on_progress: ProgressCallback | None = None,
    operation: str = 'fetch',
    context: PaginationContext | None = None,
) -> AsyncIterator[list[JSONDict]]:
    """Iterate pages with **no silent truncation**, splitting ranges as needed.

    Contract: every matching record is yielded, or an exception is raised.

    A window is materialized before anything is yielded (see
    :func:`_fetch_window`), so the buffer is bounded by ``result_window``
    items and the observed cost of the guarantee is up to one extra pass over
    each overflowing window.

    Args:
        fetch: Async page fetch (see
            :func:`aiochainscan.services.pagination.page_fetcher`).
        params: Initial request params. A block range in the public
            spellings of :data:`_BLOCK_RANGE_KEYS` makes the request
            splittable.
        result_window: The provider's ``page * offset`` cap
            (``Scanner.result_window``).
        on_progress: Optional callback, invoked per yielded batch.
        operation: Operation label forwarded to ``on_progress``.
        context: Method/provider identity used to name a working alternative
            when completeness is unattainable.

    Yields:
        Batches of item dictionaries, sized like the requested ``offset``.

    Raises:
        PaginationDataLossError: A single block still exceeds the cap, so the
            range cannot be narrowed further. Carries the range and the cap.
        CompletenessUnavailableError: The request has no block range to narrow,
            so splitting cannot apply on this provider at all.
        ChainscanDataError: Cursor state does not advance (as in
            :func:`aiochainscan.services.pagination.iter_pages`).
    """
    detected = detect_block_range(params)
    keys = detected[0] if detected is not None else None
    windows: deque[BlockRange | None] = deque([detected[1] if detected is not None else None])

    page_size = params.get('offset')
    batch_size = page_size if isinstance(page_size, int) and page_size > 0 else result_window
    fetched = 0
    page = 1

    while windows:
        window = windows.popleft()
        attempt = dict(params)
        if window is not None and keys is not None:
            attempt[keys.start] = window[0]
            attempt[keys.end] = window[1]
        if 'page' in attempt:
            attempt['page'] = 1

        items, overflow = await _fetch_window(fetch, attempt, result_window=result_window)

        if overflow is not _Overflow.NONE:
            if window is None:
                # No splittable dimension: narrowing cannot help here, and
                # another provider is the only real remedy.
                raise CompletenessUnavailableError(
                    method=context.method if context is not None else 'this request',
                    provider=context.provider if context is not None else 'the provider',
                    items_fetched=len(items),
                    api_limit=result_window,
                    alternatives=context.alternatives if context is not None else (),
                    confirmed=overflow is _Overflow.CONFIRMED,
                )
            halves = split_window(window, items)
            if halves is None:
                raise PaginationDataLossError(
                    block_number=window[0],
                    items_fetched=len(items),
                    api_limit=result_window,
                    start_block=window[0],
                    end_block=window[1],
                    confirmed=overflow is _Overflow.CONFIRMED,
                )
            windows.extendleft(reversed(halves))
            continue

        for batch in _chunked(items, batch_size):
            if not batch:
                continue
            fetched += len(batch)
            await _notify_progress(
                on_progress,
                fetched=fetched,
                page=page,
                operation=operation,
            )
            yield batch
            page += 1
