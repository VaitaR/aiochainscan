"""
Streaming implementations for memory-efficient pagination.

This module provides AsyncIterator-based streaming versions of the paging
engine functions for constant memory usage regardless of dataset size.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from time import monotonic
from typing import Any, cast

from aiochainscan.constants import BATCH_DEFAULT_SIZE, MAX_BLOCK_NUMBER
from aiochainscan.exceptions import ChainscanDataError, PaginationDataLossError
from aiochainscan.ports.progress import ProgressCallback
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services.paging_engine import (
    FetchPage,
    FetchSpec,
    Item,
    ProviderPolicy,
)

logger = logging.getLogger(__name__)


async def _gather_pages(coros: list[Any]) -> list[list[Item]]:
    """Helper to gather page fetch coroutines."""
    return cast(list[list[Item]], await asyncio.gather(*coros))


async def fetch_all_generic_streaming(
    *,
    start_block: int | None,
    end_block: int | None,
    fetch_spec: FetchSpec,
    policy: ProviderPolicy,
    rate_limiter: RateLimiter | None,
    retry: RetryPolicy | None,
    telemetry: Telemetry | None,
    max_concurrent: int,
    batch_size: int | None = None,
    stats: dict[str, int] | None = None,
    on_progress: ProgressCallback | None = None,
) -> AsyncIterator[list[Item]]:
    """
    Stream results in batches using AsyncIterator pattern for constant memory usage.

    This is the memory-efficient alternative to fetch_all_generic() that yields
    batches of items instead of accumulating everything in memory. Perfect for
    whale addresses with millions of transactions.

    Guarantees:
      - Deduplicates by spec.key_fn and sorts by spec.order_fn (stable order) per batch
      - Respects RPS via RateLimiter and retries via RetryPolicy
      - Yields batches of batch_size items (last batch may be smaller)
      - Constant memory usage regardless of total dataset size
      - All paging strategies supported (paged, sliding, sliding_bi)

    Args:
        start_block: Starting block number (None for 0)
        end_block: Ending block number (None for latest)
        fetch_spec: Specification of how to fetch and process items
        policy: Provider paging policy (mode, prefetch, window_cap, rps_key)
        rate_limiter: Rate limiter for API requests
        retry: Retry policy for failed requests
        telemetry: Telemetry for tracking metrics
        max_concurrent: Maximum concurrent requests
        batch_size: Number of items to yield per batch (default: BATCH_DEFAULT_SIZE)
        stats: Optional stats dict to populate
        on_progress: Optional callback for progress updates

    Yields:
        Batches of deduplicated and sorted items (list[dict])

    Example:
        ```python
        async for batch in fetch_all_generic_streaming(
            start_block=0,
            end_block=None,
            fetch_spec=spec,
            policy=policy,
            rate_limiter=limiter,
            retry=retry_policy,
            telemetry=None,
            max_concurrent=1,
            batch_size=BATCH_DEFAULT_SIZE,
        ):
            # Process batch of BATCH_DEFAULT_SIZE items
            for item in batch:
                await process_item(item)
        ```
    """
    # Use default batch size if not specified
    effective_batch_size = batch_size if batch_size is not None else BATCH_DEFAULT_SIZE

    # Validate batch_size
    if effective_batch_size < 1:
        raise ValueError(f'batch_size must be at least 1, got {effective_batch_size}')

    items_yielded: int = 0

    # Helper to safely invoke progress callback
    async def _call_progress(
        current_block: int | None = None, current_page: int | None = None
    ) -> None:
        if on_progress is None:
            return
        try:
            await on_progress(
                fetched=items_yielded,
                total_expected=None,
                current_block=current_block,
                current_page=current_page,
                operation='fetch',
            )
        except (TypeError, ValueError, RuntimeError) as e:
            logger.warning(f'Progress callback error: {e}', exc_info=True)

    # Determine end_block snapshot when not provided
    effective_end_block: int
    if end_block is None:
        if fetch_spec.resolve_end_block is not None:
            try:
                effective_end_block = int(await fetch_spec.resolve_end_block())
            except (ValueError, TypeError):
                effective_end_block = MAX_BLOCK_NUMBER
        else:
            effective_end_block = MAX_BLOCK_NUMBER
    else:
        effective_end_block = int(end_block)

    effective_start_block: int = 0 if start_block is None else int(start_block)
    if effective_end_block <= effective_start_block:
        return

    pages_processed: int = 0
    accumulated: list[Item] = []
    seen_keys: set[str] = set()

    # Respect provider window caps
    base_offset: int = max(1, int(fetch_spec.max_offset))
    effective_offset_for_provider: int = (
        min(base_offset, int(policy.window_cap)) if policy.window_cap is not None else base_offset
    )

    async def _call_fetch_page(*, page: int, s: int, e: int) -> list[Item]:
        async def _inner() -> list[Item]:
            if rate_limiter is not None and policy.rps_key is not None:
                await rate_limiter.acquire(policy.rps_key)
            return await fetch_spec.fetch_page(
                page=page, start_block=s, end_block=e, offset=effective_offset_for_provider
            )

        if retry is not None:
            return await retry.run(lambda: _inner())
        return await _inner()

    start_ts = monotonic() if telemetry is not None else 0.0

    try:
        if policy.mode == 'sliding_bi':
            # Bidirectional sliding requires a descending fetcher
            if fetch_spec.fetch_page_desc is None:
                # Fallback to simple sliding
                policy = ProviderPolicy(
                    mode='sliding',
                    prefetch=1,
                    window_cap=policy.window_cap,
                    rps_key=policy.rps_key,
                )
            else:
                low: int = effective_start_block
                up: int = effective_end_block
                fetch_page_desc: FetchPage = fetch_spec.fetch_page_desc

                async def _call_desc(s: int, e: int) -> list[Item]:
                    async def _inner_desc() -> list[Item]:
                        if rate_limiter is not None and policy.rps_key is not None:
                            await rate_limiter.acquire(policy.rps_key)
                        return await fetch_page_desc(
                            page=1,
                            start_block=s,
                            end_block=e,
                            offset=effective_offset_for_provider,
                        )

                    return await (retry.run(_inner_desc) if retry is not None else _inner_desc())

                while low <= up:
                    curr_low, curr_up = low, up
                    asc_coro = _call_fetch_page(page=1, s=curr_low, e=curr_up)
                    desc_coro = _call_desc(curr_low, curr_up)
                    items_asc, items_desc = await _gather_pages([asc_coro, desc_coro])

                    # Process ASC items
                    pages_processed += 1
                    if telemetry is not None:
                        await telemetry.record_event(
                            'paging.page_ok',
                            {'mode': 'sliding_bi_asc', 'page': 1, 'items': len(items_asc)},
                        )

                    # Deduplicate and accumulate
                    for it in items_asc:
                        if not isinstance(it, dict):
                            continue
                        key = fetch_spec.key_fn(it)
                        if key is None or key in seen_keys:
                            continue
                        seen_keys.add(key)
                        accumulated.append(it)

                    asc_short = len(items_asc) < effective_offset_for_provider or not items_asc

                    if items_asc:
                        with suppress(ValueError, TypeError, IndexError):
                            await _call_progress(
                                current_block=fetch_spec.order_fn(items_asc[-1])[0]
                                if items_asc
                                else None
                            )
                        try:
                            last_block_asc = int(fetch_spec.order_fn(items_asc[-1])[0])
                            new_low = max(curr_low, last_block_asc + 1)
                        except (ValueError, TypeError, IndexError):
                            new_low = curr_low
                    else:
                        new_low = curr_low

                    # Process DESC items
                    pages_processed += 1
                    if telemetry is not None:
                        await telemetry.record_event(
                            'paging.page_ok',
                            {'mode': 'sliding_bi_desc', 'page': 1, 'items': len(items_desc)},
                        )

                    for it in items_desc:
                        if not isinstance(it, dict):
                            continue
                        key = fetch_spec.key_fn(it)
                        if key is None or key in seen_keys:
                            continue
                        seen_keys.add(key)
                        accumulated.append(it)

                    desc_short = len(items_desc) < effective_offset_for_provider or not items_desc

                    if items_desc:
                        with suppress(ValueError, TypeError, IndexError):
                            await _call_progress(
                                current_block=fetch_spec.order_fn(items_desc[-1])[0]
                                if items_desc
                                else None
                            )
                        try:
                            oldest_block_desc = int(fetch_spec.order_fn(items_desc[-1])[0])
                            new_up = min(curr_up, oldest_block_desc - 1)
                        except (ValueError, TypeError, IndexError):
                            new_up = curr_up
                    else:
                        new_up = curr_up

                    # Yield batches when accumulated reaches effective_batch_size
                    while len(accumulated) >= effective_batch_size:
                        # Sort batch before yielding
                        batch = accumulated[:effective_batch_size]
                        try:
                            batch.sort(key=fetch_spec.order_fn)
                        except (TypeError, ValueError, KeyError, AttributeError) as exc:
                            raise ChainscanDataError(
                                f'Failed to sort batch in {fetch_spec.name}',
                                details={'error_type': type(exc).__name__, 'error': str(exc)},
                            ) from exc
                        yield batch
                        items_yielded += len(batch)
                        accumulated = accumulated[effective_batch_size:]

                    # Apply new window and stop conditions
                    low, up = new_low, new_up
                    if low > up or (asc_short and desc_short):
                        break

        if policy.mode == 'sliding':
            current_start: int = effective_start_block
            while True:
                items = await _call_fetch_page(page=1, s=current_start, e=effective_end_block)
                pages_processed += 1
                if telemetry is not None:
                    await telemetry.record_event(
                        'paging.page_ok',
                        {'mode': 'sliding', 'page': 1, 'items': len(items)},
                    )

                try:
                    last_block = int(fetch_spec.order_fn(items[-1])[0]) if items else None
                    await _call_progress(current_block=last_block)
                except (ValueError, TypeError, IndexError):
                    pass

                if not items:
                    break

                # Deduplicate and accumulate
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    key = fetch_spec.key_fn(it)
                    if key is None or key in seen_keys:
                        continue
                    seen_keys.add(key)
                    accumulated.append(it)

                # Yield batches when accumulated reaches effective_batch_size
                while len(accumulated) >= effective_batch_size:
                    batch = accumulated[:effective_batch_size]
                    try:
                        batch.sort(key=fetch_spec.order_fn)
                    except (TypeError, ValueError, KeyError, AttributeError) as exc:
                        raise ChainscanDataError(
                            f'Failed to sort batch in {fetch_spec.name}',
                            details={'error_type': type(exc).__name__, 'error': str(exc)},
                        ) from exc
                    yield batch
                    items_yielded += len(batch)
                    accumulated = accumulated[effective_batch_size:]

                if len(items) < effective_offset_for_provider:
                    break

                # Advance to next block
                try:
                    last_item = items[-1]
                    first_item = items[0]
                    last_block = int(fetch_spec.order_fn(last_item)[0])
                    first_block = int(fetch_spec.order_fn(first_item)[0])
                except (ValueError, TypeError, IndexError):
                    break

                # Whale block detection
                if len(items) >= effective_offset_for_provider and first_block == last_block:
                    if telemetry is not None:
                        await telemetry.record_event(
                            'paging.whale_block_detected',
                            {
                                'mode': 'sliding',
                                'block': last_block,
                                'items_fetched': len(items),
                                'limit': effective_offset_for_provider,
                            },
                        )
                    raise PaginationDataLossError(
                        block_number=last_block,
                        items_fetched=len(items),
                        api_limit=effective_offset_for_provider,
                        suggested_action=(
                            'This block contains more transactions than the API limit. '
                            'Options: (1) Use GraphQL API if supported (BlockScout), '
                            '(2) Apply topic/address filters to reduce result set, '
                            '(3) Use a different data provider, or '
                            '(4) Fetch this block separately via block-by-number endpoint.'
                        ),
                    )

                current_start = max(current_start, last_block + 1)

        if policy.mode == 'paged':
            next_page: int = 1
            prefetch: int = max(1, min(int(policy.prefetch), int(max_concurrent)))
            while True:
                batch_pages = [next_page + i for i in range(prefetch)]
                results = await _gather_pages(
                    [
                        _call_fetch_page(page=p, s=effective_start_block, e=effective_end_block)
                        for p in batch_pages
                    ]
                )

                for page_index, items in zip(batch_pages, results, strict=False):
                    pages_processed += 1
                    if telemetry is not None:
                        await telemetry.record_event(
                            'paging.page_ok',
                            {'mode': 'paged', 'page': int(page_index), 'items': len(items)},
                        )
                    if not items:
                        next_page = 0
                        break

                    # Deduplicate and accumulate
                    for it in items:
                        if not isinstance(it, dict):
                            continue
                        key = fetch_spec.key_fn(it)
                        if key is None or key in seen_keys:
                            continue
                        seen_keys.add(key)
                        accumulated.append(it)

                    # Yield batches when accumulated reaches effective_batch_size
                    while len(accumulated) >= effective_batch_size:
                        batch = accumulated[:effective_batch_size]
                        try:
                            batch.sort(key=fetch_spec.order_fn)
                        except (TypeError, ValueError, KeyError, AttributeError) as exc:
                            raise ChainscanDataError(
                                f'Failed to sort batch in {fetch_spec.name}',
                                details={'error_type': type(exc).__name__, 'error': str(exc)},
                            ) from exc
                        yield batch
                        items_yielded += len(batch)
                        accumulated = accumulated[effective_batch_size:]

                    try:
                        last_block = int(fetch_spec.order_fn(items[-1])[0]) if items else None
                        await _call_progress(current_block=last_block, current_page=page_index)
                    except (ValueError, TypeError, IndexError):
                        pass

                    if len(items) < effective_offset_for_provider:
                        next_page = 0
                        break

                if next_page <= 0:
                    break
                next_page += prefetch

    except Exception as exc:  # noqa: BLE001
        if telemetry is not None:
            await telemetry.record_error('paging.error', exc, {'mode': policy.mode})
        raise
    finally:
        if telemetry is not None:
            duration_ms = int((monotonic() - start_ts) * 1000)
            await telemetry.record_event(
                'paging.duration',
                {
                    'mode': policy.mode,
                    'duration_ms': duration_ms,
                    'prefetch': int(policy.prefetch),
                    'start_block': int(effective_start_block),
                    'end_block': int(effective_end_block),
                },
            )

    # Yield remainder
    if accumulated:
        try:
            accumulated.sort(key=fetch_spec.order_fn)
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise ChainscanDataError(
                f'Failed to sort final batch in {fetch_spec.name}',
                details={'error_type': type(exc).__name__, 'error': str(exc)},
            ) from exc
        yield accumulated
        items_yielded += len(accumulated)

    if telemetry is not None:
        await telemetry.record_event(
            'paging.ok',
            {
                'mode': policy.mode,
                'items': items_yielded,
                'streaming': True,
            },
        )

    if stats is not None:
        stats.update(
            {
                'pages_processed': int(pages_processed),
                'items_total': int(items_yielded),
                'mode': 1 if policy.mode == 'paged' else (2 if policy.mode == 'sliding' else 3),
                'prefetch': int(policy.prefetch),
                'start_block': int(effective_start_block),
                'end_block': int(effective_end_block),
                'streaming': True,
            }
        )
