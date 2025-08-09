from __future__ import annotations

import asyncio
import heapq
from collections.abc import Awaitable, Callable
from typing import Any

from aiochainscan.ports.telemetry import Telemetry


async def fetch_all_ranges_optimized(
    *,
    start_block: int,
    end_block: int,
    max_concurrent: int,
    max_offset: int,
    min_range_width: int,
    max_attempts_per_range: int,
    fetch_range: Callable[[int, int], Awaitable[list[dict[str, Any]]]],
    dedup_key: Callable[[dict[str, Any]], str | None],
    sort_key: Callable[[dict[str, Any]], Any],
    telemetry: Telemetry | None = None,
    telemetry_prefix: str = 'aggregator',
    stats: dict[str, int] | None = None,
    edges_first: bool = True,
) -> list[dict[str, Any]]:
    """Generic optimized range fetcher using priority queue + dynamic splitting.

    Caller supplies a ``fetch_range(start, end)`` coroutine, dedup/sort key functions,
    and tuning parameters. This function orchestrates concurrency, retries and
    deduplication/sorting. It does not perform latest-block resolution.

    Optimizations implemented:
    - Edge-first kickoff: fetch bottom and top edges in parallel before center.
    - Density-driven splitting: when a range hits ``max_offset``, estimate tx density
      and split by a targeted pivot so the next left chunk returns around ``max_offset``
      items instead of naive 50/50.
    - Guardrails: minimum range width, bounded attempts per range, robust dedup and stable sort.
    """

    if end_block <= start_block:
        return []

    semaphore = asyncio.Semaphore(max(1, max_concurrent))

    async def _run_fetch(s: int, e: int) -> tuple[int, int, list[dict[str, Any]]]:
        async with semaphore:
            items = await fetch_range(s, e)
            return s, e, items if isinstance(items, list) else []

    # Stats and accumulation containers
    local_stats: dict[str, int] = {
        'ranges_seeded': 0,
        'ranges_processed': 0,
        'ranges_split': 0,
        'retries': 0,
        'errors': 0,
        'ranges_failed': 0,
        'items_total': 0,
    }

    all_items: list[dict[str, Any]] = []

    # Priority queue of ranges: (-size, counter, start, end)
    range_queue: list[tuple[int, int, int, int]] = []
    counter = 0

    def push_range(s: int, e: int) -> None:
        nonlocal counter
        if e < s:
            return
        heapq.heappush(range_queue, (-(e - s), counter, s, e))
        counter += 1

    total_range = end_block - start_block
    left_end = start_block + min(total_range // 4, 50_000)
    right_start = max(end_block - total_range // 4, left_end + 1)
    # Optionally fetch edges first to accelerate convergence from both ends
    if edges_first:
        # Fetch left and right concurrently before seeding the center into the queue
        edge_tasks = []
        if start_block <= left_end:
            edge_tasks.append(_run_fetch(start_block, left_end))
        if right_start <= end_block:
            edge_tasks.append(_run_fetch(right_start, end_block))

        results = await asyncio.gather(*edge_tasks, return_exceptions=True)
        local_items: list[tuple[int, int, list[dict[str, Any]]]] = []
        left_done = False
        right_done = False
        for res in results:
            if isinstance(res, BaseException):
                # If edge fetch failed, it will be re-queued below
                continue
            s2, e2, items = res
            local_items.append((s2, e2, items))
            if s2 == start_block and e2 == left_end:
                left_done = True
            if s2 == right_start and e2 == end_block:
                right_done = True

        # Process edge fetch results (split or accept)
        for s2, e2, items in local_items:
            blocks = max(1, e2 - s2 + 1)
            if len(items) >= max_offset and e2 > s2 and (e2 - s2) > min_range_width:
                # density-driven pivot
                density = max(1e-9, len(items) / blocks)
                target_len = int((max_offset / density) * 1.15)
                target_len = max(min_range_width, min(target_len, e2 - s2))
                pivot = min(e2 - 1, s2 + target_len - 1)
                push_range(s2, pivot)
                push_range(pivot + 1, e2)
                local_stats['ranges_split'] += 1
                if telemetry is not None:
                    await telemetry.record_event(
                        f'{telemetry_prefix}.range_split',
                        {'start': s2, 'end': e2, 'pivot': pivot},
                    )
            else:
                all_items.extend(items)
                local_stats['items_total'] += len(items)
                if telemetry is not None:
                    await telemetry.record_event(
                        f'{telemetry_prefix}.range_ok',
                        {'start': s2, 'end': e2, 'items': len(items)},
                    )

        # Seed the center range into the queue (and re-queue only failed edges)
        center_start = left_end + 1
        center_end = right_start - 1
        if center_start <= center_end:
            push_range(center_start, center_end)
        # Re-queue edges only if they failed
        if start_block <= left_end and not left_done:
            push_range(start_block, left_end)
        if right_start <= end_block and not right_done:
            push_range(right_start, end_block)
    else:
        push_range(start_block, left_end)
        if left_end + 1 <= right_start - 1:
            push_range(left_end + 1, right_start - 1)
        push_range(right_start, end_block)

    # Stats
    # Approximate seeded ranges count (best-effort)
    if edges_first:
        seeded = 0
        center_start = left_end + 1
        center_end = right_start - 1
        if center_start <= center_end:
            seeded += 1
        # Edges always attempted (either run now or re-queued on failure)
        seeded += 2
        local_stats['ranges_seeded'] = seeded
    else:
        local_stats['ranges_seeded'] = 3
    if stats is not None:
        stats.update(
            {
                'max_concurrent': int(max_concurrent),
                'max_offset': int(max_offset),
                'min_range_width': int(min_range_width),
                'max_attempts_per_range': int(max_attempts_per_range),
                'start_block': int(start_block),
                'end_block': int(end_block),
            }
        )

    attempts: dict[tuple[int, int], int] = {}

    if telemetry is not None:
        start_ts = __import__('time').monotonic()

    # (moved earlier)

    while range_queue:
        batch = [heapq.heappop(range_queue) for _ in range(min(max_concurrent, len(range_queue)))]
        tasks = [_run_fetch(s, e) for _neg, _c, s, e in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for idx, res in enumerate(results):
            _neg, _c, s, e = batch[idx]
            if isinstance(res, BaseException):
                key = (s, e)
                curr = attempts.get(key, 0) + 1
                attempts[key] = curr
                local_stats['errors'] += 1
                if telemetry is not None:
                    await telemetry.record_error(
                        f'{telemetry_prefix}.range_error',
                        res,
                        {'start': s, 'end': e, 'attempt': curr},
                    )
                if curr < max_attempts_per_range:
                    local_stats['retries'] += 1
                    heapq.heappush(range_queue, (-(e - s), counter, s, e))
                    counter += 1
                    if telemetry is not None:
                        await telemetry.record_event(
                            f'{telemetry_prefix}.range_retry',
                            {'start': s, 'end': e, 'attempt': curr},
                        )
                else:
                    local_stats['ranges_failed'] += 1
                continue

            s2, e2, items = res
            local_stats['ranges_processed'] += 1
            if len(items) >= max_offset and e2 > s2 and (e2 - s2) > min_range_width:
                # density-driven pivot
                density = max(1e-9, len(items) / max(1, e2 - s2 + 1))
                target_len = int((max_offset / density) * 1.15)
                target_len = max(min_range_width, min(target_len, e2 - s2))
                pivot = min(e2 - 1, s2 + target_len - 1)
                push_range(s2, pivot)
                push_range(pivot + 1, e2)
                local_stats['ranges_split'] += 1
                if telemetry is not None:
                    await telemetry.record_event(
                        f'{telemetry_prefix}.range_split',
                        {'start': s2, 'end': e2, 'pivot': pivot},
                    )
            else:
                all_items.extend(items)
                local_stats['items_total'] += len(items)
                if telemetry is not None:
                    await telemetry.record_event(
                        f'{telemetry_prefix}.range_ok',
                        {'start': s2, 'end': e2, 'items': len(items)},
                    )

    # Deduplicate and sort
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for it in all_items:
        if not isinstance(it, dict):
            continue
        k = dedup_key(it)
        if not isinstance(k, str):
            continue
        if k in seen:
            continue
        seen.add(k)
        unique.append(it)

    from contextlib import suppress

    with suppress(Exception):
        unique.sort(key=sort_key)

    if telemetry is not None:
        end_ts = __import__('time').monotonic()
        await telemetry.record_event(
            f'{telemetry_prefix}.duration',
            {'duration_ms': int((end_ts - start_ts) * 1000)},
        )
        await telemetry.record_event(
            f'{telemetry_prefix}.ok',
            {'items': len(unique)},
        )

    if stats is not None:
        stats.update(local_stats)

    return unique
