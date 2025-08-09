from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable, Literal, Protocol

from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry


Item = dict[str, Any]


class FetchPage(Protocol):
    async def __call__(
        self, *, page: int, start_block: int, end_block: int, offset: int
    ) -> list[Item]:
        ...


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

    mode: Literal['paged', 'sliding']
    prefetch: int
    window_cap: int | None
    rps_key: str | None


def resolve_policy_for_provider(*, api_kind: str, network: str, max_concurrent: int) -> ProviderPolicy:
    """Return a reasonable default paging policy for a given provider string.

    - Etherscan family ('eth'): sliding window, window_cap=10_000, prefetch=1
    - Blockscout (api_kind startswith 'blockscout_'): paged, prefetch=max_concurrent
    - Others: paged, prefetch=1
    """

    if api_kind == 'eth':
        return ProviderPolicy(mode='sliding', prefetch=1, window_cap=10_000, rps_key=f'{api_kind}:{network}:fetch')
    if isinstance(api_kind, str) and api_kind.startswith('blockscout_'):
        prefetch = max(1, int(max_concurrent))
        return ProviderPolicy(mode='paged', prefetch=prefetch, window_cap=None, rps_key=f'{api_kind}:{network}:fetch')
    return ProviderPolicy(mode='paged', prefetch=1, window_cap=None, rps_key=f'{api_kind}:{network}:fetch')


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
    offset: int = max(1, int(fetch_spec.max_offset))

    async def _call_fetch_page(*, page: int, s: int, e: int) -> list[Item]:
        async def _inner() -> list[Item]:
            if rate_limiter is not None and policy.rps_key is not None:
                await rate_limiter.acquire(policy.rps_key)
            return await fetch_spec.fetch_page(page=page, start_block=s, end_block=e, offset=offset)

        if retry is not None:
            return await retry.run(lambda: _inner())
        return await _inner()

    start_ts = monotonic() if telemetry is not None else 0.0

    try:
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
                if not items:
                    break
                all_items.extend(items)
                if len(items) < offset:
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
                    [_call_fetch_page(page=p, s=effective_start_block, e=effective_end_block) for p in batch_pages]
                )
                # Maintain order by page
                for page_index, items in zip(batch_pages, results):
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
                    if len(items) < offset:
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

    try:
        unique.sort(key=fetch_spec.order_fn)
    except Exception:
        # Best-effort: keep insertion order
        pass

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
    # Local small helper to avoid importing asyncio in global scope.
    import asyncio

    return await asyncio.gather(*coros)


