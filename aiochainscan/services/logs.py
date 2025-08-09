from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any

from aiochainscan.domain.dto import LogEntryDTO
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry


async def get_logs(
    *,
    start_block: int | str,
    end_block: int | str,
    address: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
    page: int | str | None = None,
    offset: int | str | None = None,
    extra_params: Mapping[str, Any] | None = None,
    _cache: Cache | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'logs',
        'action': 'getLogs',
        'fromBlock': start_block,
        'toBlock': end_block,
        'address': address,
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

    cache_key = f'logs:{api_kind}:{network}:{address}:{start_block}:{end_block}:{topics}:{topic_operators}:{page}:{offset}'
    if _cache is not None:
        cached = await _cache.get(cache_key)
        if isinstance(cached, list):
            return cached

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:logs')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'logs.get_logs.duration',
                    {'api_kind': api_kind, 'network': network, 'duration_ms': duration_ms},
                )

    try:
        if _retry is not None:
            response: Any = await _retry.run(_do_request)
        else:
            response = await _do_request()
    except Exception as exc:  # noqa: BLE001
        if _telemetry is not None:
            await _telemetry.record_error(
                'logs.get_logs.error',
                exc,
                {'api_kind': api_kind, 'network': network},
            )
        raise

    out: list[dict[str, Any]] = []
    if isinstance(response, dict):
        result = response.get('result')
        if isinstance(result, list):
            out = [entry for entry in result if isinstance(entry, dict)]

    if _telemetry is not None:
        await _telemetry.record_event(
            'logs.get_logs.ok',
            {'api_kind': api_kind, 'network': network, 'items': len(out)},
        )

    if _cache is not None and out:
        await _cache.set(cache_key, out, ttl_seconds=15)

    return out


def normalize_log_entry(raw: dict[str, Any]) -> LogEntryDTO:
    def hex_to_int(h: str | None) -> int | None:
        if not h:
            return None
        try:
            return int(h, 16) if isinstance(h, str) and h.startswith('0x') else int(h)
        except Exception:
            return None

    topics_value = raw.get('topics')
    topics: list[Any] = topics_value if isinstance(topics_value, list) else []
    return {
        'address': raw.get('address', ''),
        'block_number': hex_to_int(raw.get('blockNumber')),
        'tx_hash': raw.get('transactionHash'),
        'data': raw.get('data'),
        'topics': [str(t) for t in topics],
    }


def normalize_logs(items: list[dict[str, Any]]) -> list[LogEntryDTO]:
    """Normalize a list of raw log entries using `normalize_log_entry`."""
    out: list[LogEntryDTO] = []
    for item in items:
        if isinstance(item, dict):
            out.append(normalize_log_entry(item))
    return out


async def get_all_logs_optimized(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    max_concurrent: int,
    max_offset: int,
    min_range_width: int = 1_000,
    max_attempts_per_range: int = 3,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
    stats: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Fetch all logs using page-based strategy (provider-aware)."""
    # Determine latest end_block
    if end_block is None:
        endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
        url: str = endpoint.api_url
        try:
            params_proxy: dict[str, Any] = {'module': 'proxy', 'action': 'eth_blockNumber'}
            signed_params, headers = endpoint.filter_and_sign(params_proxy, headers=None)
            response: Any = await (
                _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
                if _retry is not None
                else http.get(url, params=signed_params, headers=headers)
            )
            latest_hex = response.get('result') if isinstance(response, dict) else None
            end_block = int(latest_hex, 16) if isinstance(latest_hex, str) and latest_hex.startswith('0x') else int(latest_hex)
        except Exception:
            end_block = 99_999_999

    if start_block is None:
        start_block = 0
    if end_block <= start_block:
        return []

    all_items: list[dict[str, Any]] = []
    pages_processed = 0

    if api_kind == 'eth':
        current_start = start_block
        while True:
            items = await get_logs(
                start_block=current_start,
                end_block=end_block,
                address=address,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=_endpoint_builder,
                topics=topics,
                topic_operators=topic_operators,
                page=1,
                offset=max_offset,
                _rate_limiter=_rate_limiter,
                _retry=_retry,
                _telemetry=_telemetry,
            )
            pages_processed += 1
            if not items:
                break
            all_items.extend(items)
            if len(items) < max_offset:
                break
            try:
                last_block_str = items[-1].get('blockNumber')
                last_block = int(last_block_str, 16) if isinstance(last_block_str, str) and last_block_str.startswith('0x') else int(str(last_block_str))
            except Exception:
                break
            current_start = max(current_start, last_block + 1)
    else:
        page = 1
        while True:
            items = await get_logs(
                start_block=start_block,
                end_block=end_block,
                address=address,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=_endpoint_builder,
                topics=topics,
                topic_operators=topic_operators,
                page=page,
                offset=max_offset,
                _rate_limiter=_rate_limiter,
                _retry=_retry,
                _telemetry=_telemetry,
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
        key = f'{txh}:{idx}' if isinstance(txh, str) and isinstance(idx, (str, int)) else None
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
        stats.update({'pages_processed': pages_processed, 'items_total': len(all_items), 'paging_used': 1})
    return unique
