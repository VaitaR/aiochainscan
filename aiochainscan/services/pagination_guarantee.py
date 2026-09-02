"""Guaranteed-complete pagination: adaptive block-range splitting.

The completeness half of the pagination engine. Where
:func:`aiochainscan.services.pagination.iter_pages` walks a cursor until it
runs dry, this module adds the contract *"every matching record was
returned, or an exception was raised"* for providers that cap what a single
page/offset query can reach (``Scanner.result_window``).

Design in one paragraph: a window is materialized through the ONE cursor
loop (:func:`aiochainscan.services.pagination.iter_pages` — never a private
re-implementation) before anything is yielded, because a window that turns
out to have overflowed must be discarded and re-fetched as two narrower
windows; yielding first would duplicate items. Reaching the provider's
result window is the overflow signal — the weakest one that cannot be
fooled, since a capped explorer answers a partial page byte-identical to
the end of the data. The split point is *observed* (the block of the last
record the provider served), not fixed, and both halves are strictly
narrower, which is what makes the recursion terminate.

Public interface (also re-exported from
:mod:`aiochainscan.services.pagination`):

- :func:`iter_pages_complete` — the guaranteed generator.
- :func:`detect_block_range` — find the block-range params of a request.
- :func:`split_window` — adaptive two-way split of an overflowing range.
- :class:`PaginationContext` — who is being paginated, for honest errors.
- :data:`BlockRange` — inclusive ``(start_block, end_block)`` window.

Error contract:

- :class:`~aiochainscan.exceptions.PaginationDataLossError` — a single
  block still exceeds the cap (splitting worked and ran out).
- :class:`~aiochainscan.exceptions.CompletenessUnavailableError` — the
  endpoint has no splittable dimension at all on this provider.

Block-range params speak the PUBLIC dialect only (``start_block``/
``end_block`` or ``from_block``/``to_block``); wire spellings
(``startblock``, ``fromBlock``, ...) belong to scanner ``param_map``\\ s and
are translated before requests are built.
"""

from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, NamedTuple

from ..constants import MAX_BLOCK_NUMBER
from ..core.types import JSONDict
from ..exceptions import (
    CompletenessUnavailableError,
    PaginationDataLossError,
)
from ..ports.progress import ProgressCallback

if TYPE_CHECKING:
    from .pagination import Cursor, PageFetch

__all__ = [
    'BlockRange',
    'PaginationContext',
    'detect_block_range',
    'iter_pages_complete',
    'split_window',
]

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
    from .pagination import iter_pages  # local import: pagination re-exports this module

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
    from .pagination import _notify_progress  # local import: see module docstring

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
