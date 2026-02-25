from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.adapters.smart_data_provider import SmartDataProvider
from aiochainscan.constants import MAX_BLOCK_NUMBER
from aiochainscan.core.context import ProviderContext
from aiochainscan.domain.dto_v2 import LogEventDTO
from aiochainscan.domain.models import Address
from aiochainscan.exceptions import ChainscanClientApiError
from aiochainscan.services._executor import make_hashed_cache_key, run_with_policies
from aiochainscan.services.constants import CACHE_TTL_LOGS_SECONDS as CACHE_TTL_SECONDS
from aiochainscan.services.pagination import encode_rest_cursor


async def get_logs(
    *,
    ctx: ProviderContext,
    start_block: int | str,
    end_block: int | str,
    address: Address,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
    page: int | str | None = None,
    offset: int | str | None = None,
    extra_params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'logs',
        'action': 'getLogs',
        'fromBlock': start_block,
        'toBlock': end_block,
        'address': str(address),
        'page': page,
        'offset': offset,
    }

    if topics:
        # topics[0..3]
        for idx, topic in enumerate(topics[:4]):
            params[f'topic{idx}'] = topic
    if topic_operators:
        for idx, op in enumerate(topic_operators[:3]):
            params[f'topic{idx}_{idx + 1}_opr'] = op

    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    # Build deterministic cache key using hashed payload to avoid huge keys and non-determinism
    payload = {
        'api_kind': str(ctx.api_kind),
        'network': str(ctx.network),
        'address': str(address),
        'start_block': str(start_block),
        'end_block': str(end_block),
        'topics': [str(t) for t in (topics or [])],
        'topic_operators': [str(op) for op in (topic_operators or [])],
        'page': None if page is None else str(page),
        'offset': None if offset is None else str(offset),
    }
    cache_key = make_hashed_cache_key(prefix='logs', payload=payload, length=24)
    if ctx.cache is not None:
        cached = await ctx.cache.get(cache_key)
        if isinstance(cached, list):
            return cached

    try:
        response: Any = await run_with_policies(
            do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
            telemetry=ctx.telemetry,
            telemetry_name='logs.get_logs',
            api_kind=ctx.api_kind,
            network=ctx.network,
            rate_limiter=ctx.rate_limiter,
            rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:logs',
            retry_policy=ctx.retry,
        )
    except ChainscanClientApiError as exc:
        if _is_no_log_payload(exc):
            if ctx.telemetry is not None:
                await ctx.telemetry.record_event(
                    'logs.get_logs.ok',
                    {'api_kind': ctx.api_kind, 'network': ctx.network, 'items': 0},
                )
            return []
        raise

    out: list[dict[str, Any]] = []
    if isinstance(response, dict):
        candidates: tuple[list[dict[str, Any]] | list[Any] | None, ...] = (
            response.get('result'),
            response.get('items'),
            response.get('data'),
        )
        for candidate in candidates:
            if isinstance(candidate, list):
                out = [entry for entry in candidate if isinstance(entry, dict)]
                if out:
                    break

    if ctx.telemetry is not None:
        await ctx.telemetry.record_event(
            'logs.get_logs.ok',
            {'api_kind': ctx.api_kind, 'network': ctx.network, 'items': len(out)},
        )

    if ctx.cache is not None and out:
        await ctx.cache.set(cache_key, out, ttl_seconds=CACHE_TTL_SECONDS)

    return out


def _is_no_log_payload(exc: ChainscanClientApiError) -> bool:
    message = (exc.message or '').strip().lower()
    if not message:
        return False
    no_data_markers = (
        'no logs found',
        'no records found',
        'no transactions found',
    )
    return any(marker in message for marker in no_data_markers)


async def get_logs_page(
    *,
    ctx: ProviderContext,
    start_block: int | str,
    end_block: int | str,
    address: Address,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
    page: int | str | None = None,
    offset: int | str | None = None,
    cursor: str | None = None,
    page_size: int | None = None,
    extra_params: Mapping[str, Any] | None = None,
    gql_headers: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch logs with pagination awareness.

    Chooses GraphQL when federator indicates support and required DI is provided,
    otherwise falls back to REST. Returns (items, next_cursor).
    """
    provider = SmartDataProvider(ctx)

    async def _rest_fallback() -> tuple[list[dict[str, Any]], str | None]:
        items = await get_logs(
            ctx=ctx,
            start_block=start_block,
            end_block=end_block,
            address=address,
            topics=topics,
            topic_operators=topic_operators,
            page=page,
            offset=offset,
            extra_params=extra_params,
        )
        next_cursor = encode_rest_cursor(
            page=int(page) if isinstance(page, int | str) and str(page).isdigit() else None,
            offset=int(offset)
            if isinstance(offset, int | str) and str(offset).isdigit()
            else None,
        )
        return items, next_cursor

    return await provider.fetch_logs_page(
        address=address,
        start_block=start_block,
        end_block=end_block,
        topics=topics,
        cursor=cursor,
        page_size=page_size,
        gql_headers=gql_headers,
        rest_fallback=_rest_fallback,
    )


def normalize_log_entry(raw: dict[str, Any]) -> LogEventDTO:
    """Normalize a raw log entry dict into a LogEventDTO Pydantic model."""
    return LogEventDTO.model_validate(raw)


def normalize_logs(items: list[dict[str, Any]]) -> list[LogEventDTO]:
    """Normalize a list of raw log dicts into LogEventDTO Pydantic models."""
    return [LogEventDTO.model_validate(item) for item in items if isinstance(item, dict)]


async def get_all_logs_optimized(
    *,
    ctx: ProviderContext,
    address: Address,
    start_block: int | None,
    end_block: int | None,
    max_concurrent: int,
    max_offset: int,
    min_range_width: int = 1_000,
    max_attempts_per_range: int = 3,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
    stats: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Fetch all logs using page-based strategy (provider-aware)."""
    # Determine latest end_block
    if end_block is None:
        endpoint = ctx.endpoint_builder.open(
            api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
        )
        url: str = endpoint.api_url
        try:
            params_proxy: dict[str, Any] = {'module': 'proxy', 'action': 'eth_blockNumber'}
            signed_params, headers = endpoint.filter_and_sign(params_proxy, headers=None)
            response: Any = await (
                ctx.retry.run(lambda: ctx.http.get(url, params=signed_params, headers=headers))
                if ctx.retry is not None
                else ctx.http.get(url, params=signed_params, headers=headers)
            )
            latest_hex = response.get('result') if isinstance(response, dict) else None
            if isinstance(latest_hex, str):
                if latest_hex.startswith('0x'):
                    end_block = int(latest_hex, 16)
                elif latest_hex.isdigit():
                    end_block = int(latest_hex)
                else:
                    end_block = MAX_BLOCK_NUMBER
            else:
                end_block = MAX_BLOCK_NUMBER
        except Exception:
            end_block = MAX_BLOCK_NUMBER

    if start_block is None:
        start_block = 0
    if end_block <= start_block:
        return []

    all_items: list[dict[str, Any]] = []
    pages_processed = 0

    if ctx.api_kind == 'eth':
        current_start = start_block
        while True:
            items = await get_logs(
                ctx=ctx,
                start_block=current_start,
                end_block=end_block,
                address=address,
                topics=topics,
                topic_operators=topic_operators,
                page=1,
                offset=max_offset,
            )
            pages_processed += 1
            if not items:
                break
            all_items.extend(items)
            if len(items) < max_offset:
                break
            try:
                last_block_str = items[-1].get('blockNumber')
                first_block_str = items[0].get('blockNumber')
                last_block = (
                    int(last_block_str, 16)
                    if isinstance(last_block_str, str) and last_block_str.startswith('0x')
                    else int(str(last_block_str))
                )
                first_block = (
                    int(first_block_str, 16)
                    if isinstance(first_block_str, str) and first_block_str.startswith('0x')
                    else int(str(first_block_str))
                )
            except Exception:
                break
            # Whale block detection: if all items are from the same block
            # and the batch is full, logs beyond the API limit are silently
            # dropped. Warn loudly so callers know data may be incomplete.
            if first_block == last_block and len(items) >= max_offset:
                import warnings

                warnings.warn(
                    f'Block {last_block} returned {len(items)} logs '
                    f'(API limit={max_offset}). '
                    f'Logs beyond the limit are DROPPED. '
                    f'Use a smaller block range or the streaming API '
                    f'to avoid data loss.',
                    stacklevel=2,
                )
            current_start = max(current_start, last_block + 1)
    else:
        page = 1
        while True:
            items = await get_logs(
                ctx=ctx,
                start_block=start_block,
                end_block=end_block,
                address=address,
                topics=topics,
                topic_operators=topic_operators,
                page=page,
                offset=max_offset,
            )
            pages_processed += 1
            if not items:
                break
            all_items.extend(items)
            if len(items) < max_offset:
                break
            page += 1

    # Dedup by (txHash, logIndex) and sort
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for it in all_items:
        if not isinstance(it, dict):
            continue
        txh = it.get('transactionHash') or it.get('hash')
        idx = it.get('logIndex')
        key = f'{txh}:{idx}' if isinstance(txh, str) and isinstance(idx, str | int) else None
        if key is None or key in seen:
            continue
        seen.add(key)
        unique.append(it)

    def to_int(v: Any) -> int:
        try:
            if isinstance(v, str) and v.startswith('0x'):
                return int(v, 16)
            return int(v)
        except Exception:
            return 0

    unique.sort(key=lambda it: (to_int(it.get('blockNumber')), to_int(it.get('logIndex'))))
    if stats is not None:
        stats.update(
            {'pages_processed': pages_processed, 'items_total': len(all_items), 'paging_used': 1}
        )
    return unique
