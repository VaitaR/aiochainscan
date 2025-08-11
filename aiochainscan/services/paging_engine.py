from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from time import monotonic
from typing import Any, Literal, Protocol

from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry

Item = dict[str, Any]


class FetchPage(Protocol):
    async def __call__(
        self, *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[Item]: ...


ResolveEndBlock = Callable[[], Awaitable[int]]
KeyFn = Callable[[Item], str | None]
OrderFn = Callable[[Item], tuple[int, int]]


@dataclass(slots=True)
class FetchSpec:
    """Specification of how to fetch, deduplicate and sort items.

    Attributes:
        name: Logical name for telemetry grouping.
        fetch_page: Async function to fetch a single page given paging/window args.
        key_fn: Unique key extractor for deduplication.
        order_fn: Stable ordering key extractor; first element MUST be block number.
        max_offset: Page size to request from the provider.
        resolve_end_block: Optional async supplier of an end_block snapshot.
    """

    name: str
    fetch_page: FetchPage
    key_fn: KeyFn
    order_fn: OrderFn
    max_offset: int
    # Optional alternative page fetcher using reverse order (e.g., sort='desc')
    fetch_page_desc: FetchPage | None = None
    resolve_end_block: ResolveEndBlock | None = None


@dataclass(slots=True)
class ProviderPolicy:
    """Provider paging policy and rate-limiting key.

    Attributes:
        mode: 'paged' to request pages p..p+N; 'sliding' to keep page=1 and slide start_block.
        prefetch: Number of pages to prefetch in parallel (effective for paged mode).
        window_cap: Optional provider page window cap (e.g., Etherscan 10_000). Informational.
        rps_key: Key to use with RateLimiter.acquire before outbound calls.
    """

    mode: Literal['paged', 'sliding', 'sliding_bi']
    prefetch: int
    window_cap: int | None
    rps_key: str | None


def resolve_policy_for_provider(
    *, api_kind: str, network: str, max_concurrent: int
) -> ProviderPolicy:
    """Return a reasonable default paging policy for a given provider string.

    - Etherscan family ('eth'): sliding window, window_cap=10_000, prefetch=1
    - Blockscout (api_kind startswith 'blockscout_'): paged, prefetch=max_concurrent
    - Others: paged, prefetch=1
    """

    if api_kind == 'eth':
        return ProviderPolicy(
            mode='sliding', prefetch=1, window_cap=10_000, rps_key=f'{api_kind}:{network}:fetch'
        )
    if isinstance(api_kind, str) and api_kind.startswith('blockscout_'):
        prefetch = max(1, int(max_concurrent))
        return ProviderPolicy(
            mode='paged', prefetch=prefetch, window_cap=None, rps_key=f'{api_kind}:{network}:fetch'
        )
    return ProviderPolicy(
        mode='paged', prefetch=1, window_cap=None, rps_key=f'{api_kind}:{network}:fetch'
    )


async def fetch_all_generic(
    *,
    start_block: int | None,
    end_block: int | None,
    fetch_spec: FetchSpec,
    policy: ProviderPolicy,
    rate_limiter: RateLimiter | None,
    retry: RetryPolicy | None,
    telemetry: Telemetry | None,
    max_concurrent: int,
    stats: dict[str, int] | None = None,
) -> list[Item]:
    """Generic paging engine that drives page fetching by policy and spec.

    Guarantees:
      - Deduplicates by spec.key_fn and sorts by spec.order_fn (stable order)
      - Respects RPS via RateLimiter (policy.rps_key) and retries via RetryPolicy
      - Paged: fetches batches of pages in parallel; Sliding: keeps page=1 and advances start_block

    Stop conditions:
      - Empty page or len(items) < offset
    """

    # Determine end_block snapshot when not provided.
    effective_end_block: int
    if end_block is None:
        if fetch_spec.resolve_end_block is not None:
            try:
                effective_end_block = int(await fetch_spec.resolve_end_block())
            except Exception:
                effective_end_block = 99_999_999
        else:
            effective_end_block = 99_999_999
    else:
        effective_end_block = int(end_block)

    effective_start_block: int = 0 if start_block is None else int(start_block)
    if effective_end_block <= effective_start_block:
        return []

    pages_processed: int = 0
    all_items: list[Item] = []
    # Respect provider window caps (e.g., Etherscan 10_000) by clamping requested offset
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

                # Parallel ASC and DESC per step over the same window
                while low <= up:
                    curr_low, curr_up = low, up
                    asc_coro = _call_fetch_page(page=1, s=curr_low, e=curr_up)
                    desc_coro = _call_desc(curr_low, curr_up)
                    items_asc, items_desc = await _gather_pages([asc_coro, desc_coro])

                    # ASC bookkeeping
                    pages_processed += 1
                    if telemetry is not None:
                        await telemetry.record_event(
                            'paging.page_ok',
                            {'mode': 'sliding_bi_asc', 'page': 1, 'items': len(items_asc)},
                        )
                    asc_short = False
                    if items_asc:
                        all_items.extend(items_asc)
                        if len(items_asc) < effective_offset_for_provider:
                            asc_short = True
                        try:
                            last_block_asc = int(fetch_spec.order_fn(items_asc[-1])[0])
                            new_low = max(curr_low, last_block_asc + 1)
                        except Exception:
                            new_low = curr_low
                    else:
                        asc_short = True
                        new_low = curr_low

                    # DESC bookkeeping
                    pages_processed += 1
                    if telemetry is not None:
                        await telemetry.record_event(
                            'paging.page_ok',
                            {'mode': 'sliding_bi_desc', 'page': 1, 'items': len(items_desc)},
                        )
                    desc_short = False
                    if items_desc:
                        all_items.extend(items_desc)
                        if len(items_desc) < effective_offset_for_provider:
                            desc_short = True
                        try:
                            oldest_block_desc = int(fetch_spec.order_fn(items_desc[-1])[0])
                            new_up = min(curr_up, oldest_block_desc - 1)
                        except Exception:
                            new_up = curr_up
                    else:
                        desc_short = True
                        new_up = curr_up

                    # Apply new window and stop conditions
                    low, up = new_low, new_up
                    if low > up or (asc_short and desc_short):
                        break
        elif policy.mode == 'sliding':
            current_start: int = effective_start_block
            while True:
                items = await _call_fetch_page(page=1, s=current_start, e=effective_end_block)
                pages_processed += 1
                if telemetry is not None:
                    await telemetry.record_event(
                        'paging.page_ok',
                        {'mode': 'sliding', 'page': 1, 'items': len(items)},
                    )
                if not items:
                    break
                all_items.extend(items)
                if len(items) < effective_offset_for_provider:
                    break
                # Advance to the next block after last item; order_fn's first element must be block number
                try:
                    last_item = items[-1]
                    last_block = int(fetch_spec.order_fn(last_item)[0])
                except Exception:
                    break
                current_start = max(current_start, last_block + 1)
        else:  # paged
            next_page: int = 1
            prefetch: int = max(1, min(int(policy.prefetch), int(max_concurrent)))
            while True:
                batch_pages = [next_page + i for i in range(prefetch)]
                # Fire in parallel; RPS limiter will provide backpressure
                results = await _gather_pages(
                    [
                        _call_fetch_page(page=p, s=effective_start_block, e=effective_end_block)
                        for p in batch_pages
                    ]
                )
                # Maintain order by page
                for page_index, items in zip(batch_pages, results, strict=False):
                    pages_processed += 1
                    if telemetry is not None:
                        await telemetry.record_event(
                            'paging.page_ok',
                            {'mode': 'paged', 'page': int(page_index), 'items': len(items)},
                        )
                    if not items:
                        # Stop at the first empty page in sequence
                        next_page = 0  # sentinel to exit outer loop
                        break
                    all_items.extend(items)
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

    # Deduplicate and stable sort
    seen: set[str] = set()
    unique: list[Item] = []
    for it in all_items:
        if not isinstance(it, dict):
            continue
        key = fetch_spec.key_fn(it)
        if key is None or key in seen:
            continue
        seen.add(key)
        unique.append(it)

    with suppress(Exception):
        unique.sort(key=fetch_spec.order_fn)

    if telemetry is not None:
        await telemetry.record_event(
            'paging.ok',
            {
                'mode': policy.mode,
                'items': len(unique),
            },
        )

    if stats is not None:
        stats.update(
            {
                'pages_processed': int(pages_processed),
                'items_total': int(len(all_items)),
                'mode': 1 if policy.mode == 'paged' else 2,
                'prefetch': int(policy.prefetch),
                'start_block': int(effective_start_block),
                'end_block': int(effective_end_block),
            }
        )

    return unique


async def _gather_pages(coros: list[Awaitable[list[Item]]]) -> list[list[Item]]:
    return await asyncio.gather(*coros)


async def fetch_all_sliding_bi(
    *,
    start_block: int | None,
    end_block: int | None,
    fetch_spec: FetchSpec,
    policy: ProviderPolicy,
    rate_limiter: RateLimiter | None,
    retry: RetryPolicy | None,
    telemetry: Telemetry | None,
    stats: dict[str, int] | None = None,
) -> list[Item]:
    """Bidirectional sliding window using asc+desc page fetchers.

    Requirements:
      - fetch_spec.fetch_page: ascending order (oldest→newest)
      - fetch_spec.fetch_page_desc: descending order (newest→oldest)
      - Dedup and stable sort are applied at the end
    """

    if fetch_spec.fetch_page_desc is None:
        # No descending fetcher available; fallback to normal sliding
        return await fetch_all_generic(
            start_block=start_block,
            end_block=end_block,
            fetch_spec=fetch_spec,
            policy=ProviderPolicy(
                mode='sliding', prefetch=1, window_cap=policy.window_cap, rps_key=policy.rps_key
            ),
            rate_limiter=rate_limiter,
            retry=retry,
            telemetry=telemetry,
            max_concurrent=1,
            stats=stats,
        )

    # Determine snapshot end_block
    if end_block is None:
        if fetch_spec.resolve_end_block is not None:
            try:
                effective_end = int(await fetch_spec.resolve_end_block())
            except Exception:
                effective_end = 99_999_999
        else:
            effective_end = 99_999_999
    else:
        effective_end = int(end_block)
    low = 0 if start_block is None else int(start_block)
    up = effective_end
    if up <= low:
        return []

    # Offset clamp by provider window cap
    base_offset: int = max(1, int(fetch_spec.max_offset))
    effective_offset: int = (
        min(base_offset, int(policy.window_cap)) if policy.window_cap is not None else base_offset
    )

    async def _call(fetcher: FetchPage, *, s: int, e: int) -> list[Item]:
        async def _inner() -> list[Item]:
            if rate_limiter is not None and policy.rps_key is not None:
                await rate_limiter.acquire(policy.rps_key)
            return await fetcher(page=1, start_block=s, end_block=e, offset=effective_offset)

        return await (retry.run(_inner) if retry is not None else _inner())

    all_items: list[Item] = []
    pages_processed: int = 0
    start_ts = monotonic() if telemetry is not None else 0.0

    while low <= up:
        asc_items = await _call(fetch_spec.fetch_page, s=low, e=up)
        pages_processed += 1
        if telemetry is not None:
            await telemetry.record_event(
                'paging.page_ok', {'mode': 'sliding_bi_asc', 'page': 1, 'items': len(asc_items)}
            )
        if not asc_items:
            break
        all_items.extend(asc_items)
        if len(asc_items) < effective_offset:
            break
        try:
            # order_fn first element is block number
            last_block = int(fetch_spec.order_fn(asc_items[-1])[0])
        except Exception:
            break
        low = max(low, last_block + 1)
        if low > up:
            break

        # mypy: fetch_page_desc is not None here due to earlier check
        from typing import cast

        desc_fetcher = cast(FetchPage, fetch_spec.fetch_page_desc)
        desc_items = await _call(desc_fetcher, s=low, e=up)
        pages_processed += 1
        if telemetry is not None:
            await telemetry.record_event(
                'paging.page_ok', {'mode': 'sliding_bi_desc', 'page': 1, 'items': len(desc_items)}
            )
        if not desc_items:
            break
        all_items.extend(desc_items)
        if len(desc_items) < effective_offset:
            break
        try:
            oldest_block = int(fetch_spec.order_fn(desc_items[-1])[0])
        except Exception:
            break
        up = min(up, oldest_block - 1)

    if telemetry is not None:
        await telemetry.record_event(
            'paging.duration',
            {
                'mode': 'sliding_bi',
                'duration_ms': int((monotonic() - start_ts) * 1000),
                'start_block': int(low),
                'end_block': int(up),
            },
        )

    # Dedup and stable sort
    seen: set[str] = set()
    unique: list[Item] = []
    for it in all_items:
        if not isinstance(it, dict):
            continue
        key = fetch_spec.key_fn(it)
        if key is None or key in seen:
            continue
        seen.add(key)
        unique.append(it)
    with suppress(Exception):
        unique.sort(key=fetch_spec.order_fn)

    if telemetry is not None:
        await telemetry.record_event('paging.ok', {'mode': 'sliding_bi', 'items': len(unique)})
    if stats is not None:
        stats.update(
            {
                'pages_processed': pages_processed,
                'items_total': len(all_items),
                'mode': 3,
                'prefetch': 1,
            }
        )
    return unique
