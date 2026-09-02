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
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple, Protocol, runtime_checkable

from ..constants import MAX_BLOCK_NUMBER
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
    guarantee_complete: bool = False,
    result_window: int | None = None,
    context: PaginationContext | None = None,
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
        guarantee_complete: Enforce "every matching record, or an exception"
            by delegating to :func:`iter_pages_complete`. Requires
            ``result_window``; without one there is nothing to detect, and the
            plain loop runs (see ``Scanner.result_window``).
        result_window: The provider's ``page * offset`` cap, if it declares one.
        context: Forwarded to :func:`iter_pages_complete` for error messages.

    Yields:
        Batches (lists) of item dictionaries.

    Raises:
        Any exception raised by ``fetch`` propagates unchanged.
        PaginationDataLossError: Only in guaranteed mode, when a block range
            over the cap cannot be narrowed further.
        CompletenessUnavailableError: Only in guaranteed mode, when the request
            has no block range to narrow.
    """
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
    guarantee_complete: bool = False,
    result_window: int | None = None,
    context: PaginationContext | None = None,
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
        guarantee_complete: Forwarded to :func:`iter_pages`.
        result_window: Forwarded to :func:`iter_pages`.
        context: Forwarded to :func:`iter_pages`.

    Yields:
        Item dictionaries (decoded when ``decode`` is given).
    """
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
# Guaranteed-complete pagination (adaptive block-range splitting)
# ---------------------------------------------------------------------------

type BlockRange = tuple[int, int]
"""Inclusive ``(start_block, end_block)`` window."""


class _RangeKeys(NamedTuple):
    """The two param names carrying a block range for one request shape."""

    start: str
    end: str


#: Block-range param spellings used across scanner SPECS and the client's
#: streaming methods (wire names first, public names second).
_BLOCK_RANGE_KEYS: tuple[_RangeKeys, ...] = (
    _RangeKeys('startblock', 'endblock'),
    _RangeKeys('start_block', 'end_block'),
    _RangeKeys('fromBlock', 'toBlock'),
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

    Overflow signal, deliberately the weakest one that cannot be fooled:
    ``result_window`` records have been walked. Nothing stronger is available.
    A page/offset explorer that has hit its cap answers a *partial or empty*
    page — byte-identical to genuinely reaching the end of the data — and the
    cap need not fall on a page boundary, so neither "the last page was full"
    nor "a next cursor was offered" catches every real truncation.

    Reaching the cap is therefore always treated as overflow, but the two ways
    of reaching it are not equally certain, and :class:`_Overflow` keeps them
    apart so the error message can be honest:

    - :attr:`_Overflow.CONFIRMED` — the provider offered a next cursor at the
      cap, i.e. it says more records exist. Data is definitely being cut off.
    - :attr:`_Overflow.AT_CAP` — the window came back exactly full with no
      continuation. Possibly complete, possibly truncated; unprovable either
      way. No probe can settle it: the ambiguous case is precisely the one
      where the provider handed back no cursor, and cursors are opaque (see
      the module docstring), so there is nothing to request the next page
      with. Splitting resolves it for a ranged query; a rangeless one can only
      be reported as unproven.
    """
    collected: list[JSONDict] = []
    current = dict(params)
    seen_states: set[str] = set()
    while True:
        fingerprint = _request_fingerprint(current)
        if fingerprint in seen_states:
            raise ChainscanDataError('Pagination cursor repeats a prior request state.')
        seen_states.add(fingerprint)

        items, cursor = await fetch(current)
        collected.extend(items)
        if len(collected) >= result_window:
            return collected, _Overflow.CONFIRMED if cursor is not None else _Overflow.AT_CAP
        if cursor is None:
            return collected, _Overflow.NONE
        next_params = {**current, **cursor}
        if next_params == current:
            raise ChainscanDataError('Pagination cursor does not advance request parameters.')
        current = next_params


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

    A window is materialized before anything is yielded, because a window
    that turns out to have overflowed must be discarded and re-fetched as two
    narrower windows — yielding first would duplicate items. The buffer is
    therefore bounded by ``result_window`` items, and the observed cost of
    the guarantee is up to one extra pass over each overflowing window.

    Args:
        fetch: Async page fetch (see :func:`page_fetcher`).
        params: Initial request params. A block range in any of the spellings
            in :data:`_BLOCK_RANGE_KEYS` makes the request splittable.
        result_window: The provider's ``page * offset`` cap (``Scanner.result_window``).
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
        ChainscanDataError: Cursor state does not advance (as in :func:`iter_pages`).
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
            yield batch
            page += 1
