from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any

from aiochainscan.domain.dto import (
    AddressBalanceDTO,
    BeaconWithdrawalDTO,
    InternalTxDTO,
    MinedBlockDTO,
    NormalTxDTO,
    TokenTransferDTO,
)
from aiochainscan.domain.models import Address
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services._executor import run_with_policies

CACHE_TTL_SECONDS_BALANCE: int = 10


async def get_address_balance(
    *,
    address: Address | str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _cache: Cache | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> int:
    """Fetch address balance (wei) using the canonical HTTP port and legacy UrlBuilder.

    This is a thin use-case wrapper. It composes URL and delegates HTTP to the provided port.
    """

    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    cache_key = f'balance:{api_kind}:{network}:{address}'

    params: dict[str, Any] = {
        'module': 'account',
        'action': 'balance',
        'address': str(address),
        'tag': 'latest',
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    # Try cache first
    if _cache is not None:
        cached = await _cache.get(cache_key)
        if isinstance(cached, int):
            return cached

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_address_balance',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:balance',
        retry_policy=_retry,
    )

    # Etherscan-like response: {"status": "1", "message": "OK", "result": "123..."}
    value: int = 0
    if isinstance(response, dict):
        result = response.get('result', response)
        if (isinstance(result, str) and result.isdigit()) or isinstance(result, int | float):
            value = int(result)
    elif isinstance(response, str) and response.isdigit():
        value = int(response)
    else:
        # Fallback: best-effort int conversion
        try:
            value = int(response)
        except Exception:
            value = 0

    if _telemetry is not None:
        await _telemetry.record_event(
            'account.get_address_balance.ok',
            {
                'api_kind': api_kind,
                'network': network,
            },
        )

    if _cache is not None and value >= 0:
        await _cache.set(cache_key, value, ttl_seconds=CACHE_TTL_SECONDS_BALANCE)

    return value


async def get_address_balances(
    *,
    addresses: list[str],
    tag: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'balancemulti',
        'address': ','.join(addresses),
        'tag': tag,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_address_balances',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:balancemulti',
        retry_policy=_retry,
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_address_balances.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_address_balances.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
    return []


async def get_normal_transactions(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    sort: str | None,
    page: int | None,
    offset: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'txlist',
        'address': address,
        'startblock': start_block,
        'endblock': end_block,
        'sort': sort,
        'page': page,
        'offset': offset,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_normal_transactions',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:txlist',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_normal_transactions.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_normal_transactions.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
    return []


async def get_internal_transactions(
    *,
    address: str | None,
    start_block: int | None,
    end_block: int | None,
    sort: str | None,
    page: int | None,
    offset: int | None,
    txhash: str | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'txlistinternal',
        'address': address,
        'startblock': start_block,
        'endblock': end_block,
        'sort': sort,
        'page': page,
        'offset': offset,
        'txhash': txhash,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_internal_transactions',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:txlistinternal',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_internal_transactions.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_internal_transactions.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
    return []


async def get_token_transfers(
    *,
    address: str | None,
    contract_address: str | None,
    start_block: int | None,
    end_block: int | None,
    sort: str | None,
    page: int | None,
    offset: int | None,
    token_standard: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
    preserve_none: bool = False,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    actions = {'erc20': 'tokentx', 'erc721': 'tokennfttx', 'erc1155': 'token1155tx'}
    params: dict[str, Any] = {
        'module': 'account',
        'action': actions.get(token_standard, 'tokentx'),
        'address': address,
        # Preserve legacy tests shape: omit keys with None to match expected params
        # (contractaddress and sort are optional and should not appear when None)
        'contractaddress': contract_address,
        'startblock': start_block,
        'endblock': end_block,
        'sort': sort,
        'page': page,
        'offset': offset,
    }
    # Preserve or drop None-valued optional keys depending on caller needs
    if not preserve_none:
        params = {k: v for k, v in params.items() if v is not None}
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_token_transfers',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:{params["action"]}',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_token_transfers.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_token_transfers.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
    return []


async def get_all_transactions_optimized(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    max_concurrent: int,
    max_offset: int,
    min_range_width: int = 1_000,
    max_attempts_per_range: int = 3,
    prefer_paging: bool | None = None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
    stats: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Fetch all normal transactions using dynamic range splitting and priority queue.

    This aggregator operates purely on the services layer (ports + endpoint builder),
    compatible with Blockscout/Etherscan-style providers without requiring an API key
    for Blockscout. It respects provider rate limits via the supplied RateLimiter and
    limits concurrency via ``max_concurrent``.
    """
    # New architecture: prefer unified facade; fallback to legacy wrappers, then to local implementation.
    try:
        try:
            from aiochainscan.services.unified_fetch import fetch_all as _fetch_all_unified

            result = await _fetch_all_unified(
                data_type='transactions',
                address=address,
                start_block=start_block,
                end_block=end_block,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                endpoint_builder=_endpoint_builder,
                rate_limiter=_rate_limiter,
                retry=_retry,
                telemetry=_telemetry,
                strategy='fast',
                max_offset=max_offset,
                max_concurrent=max_concurrent,
            )
        except Exception:
            from aiochainscan.services.fetch_all import (
                fetch_all_transactions_eth_sliding_fast,
                fetch_all_transactions_fast,
            )

            if api_kind == 'eth':
                result = await fetch_all_transactions_eth_sliding_fast(
                    address=address,
                    start_block=start_block,
                    end_block=end_block,
                    network=network,
                    api_key=api_key,
                    http=http,
                    endpoint_builder=_endpoint_builder,
                    rate_limiter=_rate_limiter,
                    retry=_retry,
                    telemetry=_telemetry,
                    max_offset=max_offset,
                )
            else:
                result = await fetch_all_transactions_fast(
                    address=address,
                    start_block=start_block,
                    end_block=end_block,
                    api_kind=api_kind,
                    network=network,
                    api_key=api_key,
                    http=http,
                    endpoint_builder=_endpoint_builder,
                    rate_limiter=_rate_limiter,
                    retry=_retry,
                    telemetry=_telemetry,
                    max_offset=max_offset,
                    max_concurrent=max_concurrent,
                )

        if stats is not None:
            stats.update({'items_total': len(result)})
        return result
    except Exception:
        # Fall back to the legacy implementation below if the new engine path fails.
        pass

    import asyncio

    # Resolve end_block if not provided (use proxy.eth_blockNumber contract via ports)
    if end_block is None:
        endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
        url: str = endpoint.api_url
        # Attempt 1: proxy.eth_blockNumber
        try:
            params_proxy: dict[str, Any] = {'module': 'proxy', 'action': 'eth_blockNumber'}
            signed_params, headers = endpoint.filter_and_sign(params_proxy, headers=None)

            async def _get_latest_block() -> Any:
                if _rate_limiter is not None:
                    await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.blockNumber')
                return await http.get(url, params=signed_params, headers=headers)

            response: Any = await (
                _retry.run(_get_latest_block) if _retry is not None else _get_latest_block()
            )
            latest_hex: str | None = None
            if isinstance(response, dict):
                result = response.get('result', response)
                if isinstance(result, str):
                    latest_hex = result
            if latest_hex:
                end_block = int(latest_hex, 16) if latest_hex.startswith('0x') else int(latest_hex)
            else:
                raise ValueError('no result')
        except Exception:
            # Attempt 2: block.getblocknobytime (closest=before)
            try:
                import time as _t

                params_block: dict[str, Any] = {
                    'module': 'block',
                    'action': 'getblocknobytime',
                    'timestamp': int(_t.time()),
                    'closest': 'before',
                }
                signed_params2, headers2 = endpoint.filter_and_sign(params_block, headers=None)

                async def _get_block_by_time() -> Any:
                    if _rate_limiter is not None:
                        await _rate_limiter.acquire(
                            key=f'{api_kind}:{network}:block.getblocknobytime'
                        )
                    return await http.get(url, params=signed_params2, headers=headers2)

                resp2: Any = await (
                    _retry.run(_get_block_by_time) if _retry is not None else _get_block_by_time()
                )
                if isinstance(resp2, dict):
                    res2 = resp2.get('result', resp2)
                    end_block = int(res2) if isinstance(res2, str | int) else None
            except Exception:
                end_block = None
            if end_block is None:
                # Attempt 3: sentinel latest
                end_block = 99_999_999

    # Auto-select strategy by provider when prefer_paging is None
    if prefer_paging is None:
        prefer_paging = bool(
            api_kind == 'eth' or (isinstance(api_kind, str) and api_kind.startswith('blockscout_'))
        )

    # Tighten scan window by probing earliest/latest only when not using paging.
    # Пагинация уже идет от раннего к позднему; отдельный earliest-зонд не нужен.
    if not prefer_paging:
        try:
            probe_http = http
            probe_endpoint = _endpoint_builder
            # earliest (asc, page=1, offset=1)
            earliest_items = await get_normal_transactions(
                address=address,
                start_block=None,
                end_block=None,
                sort='asc',
                page=1,
                offset=1,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=probe_http,
                _endpoint_builder=probe_endpoint,
                _rate_limiter=_rate_limiter,
                _retry=None,
                _telemetry=_telemetry,
            )
            earliest_block: int | None = None
            if earliest_items:
                try:
                    b = earliest_items[0].get('blockNumber')
                    earliest_block = (
                        int(str(b), 16)
                        if isinstance(b, str) and str(b).startswith('0x')
                        else int(str(b))
                    )
                except Exception:
                    earliest_block = None
            # latest (desc, page=1, offset=1)
            latest_items = await get_normal_transactions(
                address=address,
                start_block=None,
                end_block=None,
                sort='desc',
                page=1,
                offset=1,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=probe_http,
                _endpoint_builder=probe_endpoint,
                _rate_limiter=_rate_limiter,
                _retry=None,
                _telemetry=_telemetry,
            )
            latest_block: int | None = None
            if latest_items:
                try:
                    b = latest_items[0].get('blockNumber')
                    latest_block = (
                        int(str(b), 16)
                        if isinstance(b, str) and str(b).startswith('0x')
                        else int(str(b))
                    )
                except Exception:
                    latest_block = None
            # apply bounds if discovered
            if earliest_block is not None and (
                start_block is None or earliest_block > start_block
            ):
                start_block = earliest_block
            if latest_block is not None and (end_block is None or latest_block < end_block):
                end_block = latest_block
        except Exception:
            # Non-fatal: keep default 0..latest window
            pass

    if start_block is None:
        start_block = 0

    if end_block is not None and start_block is not None and end_block <= start_block:
        return []

    # Fast path: provider supports stable pagination by page/offset; use minimal requests
    if prefer_paging:
        all_items: list[dict[str, Any]] = []
        pages_processed: int = 0
        from contextlib import suppress as _suppress

        start_ts = __import__('time').monotonic() if _telemetry is not None else 0.0

        # Etherscan window rule: page * offset <= 10000.
        # To fetch >10k efficiently, slide by start_block and always request page=1.
        if api_kind == 'eth':
            current_start = start_block
            while True:
                items = await get_normal_transactions(
                    address=address,
                    start_block=current_start,
                    end_block=end_block,
                    sort='asc',
                    page=1,
                    offset=max_offset,
                    api_kind=api_kind,
                    network=network,
                    api_key=api_key,
                    http=http,
                    _endpoint_builder=_endpoint_builder,
                    _rate_limiter=_rate_limiter,
                    _retry=_retry,
                    _telemetry=_telemetry,
                )
                pages_processed += 1
                if _telemetry is not None:
                    await _telemetry.record_event(
                        'account.get_all_transactions_optimized.page_ok',
                        {'page': 1, 'items': len(items) if isinstance(items, list) else 0},
                    )
                if not items:
                    break
                all_items.extend(items)
                if len(items) < max_offset:
                    break
                # advance window to next block after the last item
                try:
                    last_block_str = items[-1].get('blockNumber')
                    last_block = (
                        int(last_block_str, 16)
                        if isinstance(last_block_str, str) and last_block_str.startswith('0x')
                        else int(str(last_block_str))
                    )
                except Exception:
                    break
                current_start = max(current_start, last_block + 1)
        else:
            # small parallel window to accelerate paging while respecting rate limit
            parallelism: int = max(1, min(max_concurrent, 2))
            next_page: int = 1
            stop: bool = False
            while not stop:
                batch_pages = [next_page + i for i in range(parallelism)]

                async def _fetch_page(p: int) -> tuple[int, list[dict[str, Any]]]:
                    items = await get_normal_transactions(
                        address=address,
                        start_block=start_block,
                        end_block=end_block,
                        sort='asc',
                        page=p,
                        offset=max_offset,
                        api_kind=api_kind,
                        network=network,
                        api_key=api_key,
                        http=http,
                        _endpoint_builder=_endpoint_builder,
                        _rate_limiter=_rate_limiter,
                        _retry=_retry,
                        _telemetry=_telemetry,
                    )
                    return p, items

                results = await asyncio.gather(*[_fetch_page(p) for p in batch_pages])
                # sort by page index to maintain deterministic handling
                results.sort(key=lambda t: t[0])
                for p, items in results:
                    pages_processed += 1
                    if _telemetry is not None:
                        await _telemetry.record_event(
                            'account.get_all_transactions_optimized.page_ok',
                            {'page': p, 'items': len(items) if isinstance(items, list) else 0},
                        )
                    if not items:
                        stop = True
                        break
                    all_items.extend(items)
                    if len(items) < max_offset:
                        stop = True
                        break
                next_page += parallelism
        # Dedup + sort
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for it in all_items:
            if not isinstance(it, dict):
                continue
            h = it.get('hash')
            if not isinstance(h, str):
                continue
            if h in seen:
                continue
            seen.add(h)
            unique.append(it)

        # stable sort
        def _to_int(v: Any) -> int:
            with _suppress(Exception):
                if isinstance(v, str):
                    s = v.strip()
                    if s.startswith('0x'):
                        return int(s, 16)
                    return int(s)
                return int(v)
            return 0

        with _suppress(Exception):
            unique.sort(
                key=lambda it: (
                    _to_int(it.get('blockNumber')),
                    _to_int(it.get('transactionIndex')),
                )
            )

        if _telemetry is not None:
            end_ts = __import__('time').monotonic()
            await _telemetry.record_event(
                'account.get_all_transactions_optimized.duration',
                {'duration_ms': int((end_ts - start_ts) * 1000)},
            )
            await _telemetry.record_event(
                'account.get_all_transactions_optimized.ok',
                {'items': len(unique)},
            )
        if stats is not None:
            stats.update(
                {
                    'pages_processed': int(pages_processed),
                    'items_total': len(all_items),
                    'paging_used': 1,
                }
            )
        return unique

    # Fallback: generic page loop (provider-agnostic)
    all_items: list[dict[str, Any]] = []
    pages_processed = 0
    start_ts = __import__('time').monotonic() if _telemetry is not None else 0.0
    page = 1
    while True:
        items = await get_normal_transactions(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort='asc',
            page=page,
            offset=max_offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=_endpoint_builder,
            _rate_limiter=_rate_limiter,
            _retry=_retry,
            _telemetry=_telemetry,
        )
        pages_processed += 1
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_all_transactions_optimized.page_ok',
                {'page': page, 'items': len(items) if isinstance(items, list) else 0},
            )
        if not items:
            break
        all_items.extend(items)
        if len(items) < max_offset:
            break
        page += 1

    # Dedup + sort
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for it in all_items:
        if not isinstance(it, dict):
            continue
        h = it.get('hash')
        if not isinstance(h, str) or h in seen:
            continue
        seen.add(h)
        unique.append(it)

    def _to_int(v: Any) -> int:
        try:
            if isinstance(v, str):
                s = v.strip()
                if s.startswith('0x'):
                    return int(s, 16)
                return int(s)
            return int(v)
        except Exception:
            return 0

    unique.sort(
        key=lambda it: (_to_int(it.get('blockNumber')), _to_int(it.get('transactionIndex')))
    )

    if _telemetry is not None:
        end_ts = __import__('time').monotonic()
        await _telemetry.record_event(
            'account.get_all_transactions_optimized.duration',
            {'duration_ms': int((end_ts - start_ts) * 1000)},
        )
        await _telemetry.record_event(
            'account.get_all_transactions_optimized.ok',
            {'items': len(unique)},
        )
    if stats is not None:
        stats.update(
            {'pages_processed': pages_processed, 'items_total': len(all_items), 'paging_used': 1}
        )
    return unique

    # Fallback path removed (legacy range-splitting). Use the generic page loop result above.
    return unique


async def get_all_internal_transactions_optimized(
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
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
    stats: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Fetch all internal transactions using page-based strategy.

    For Etherscan: slide start_block with page=1, offset=max_offset to avoid 10k window.
    For Blockscout: iterate pages 1..N with offset=max_offset.
    """
    # Resolve latest block when needed (same as above)

    if end_block is None:
        endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
        url: str = endpoint.api_url
        try:
            params_proxy: dict[str, Any] = {'module': 'proxy', 'action': 'eth_blockNumber'}
            signed_params, headers = endpoint.filter_and_sign(params_proxy, headers=None)

            async def _get_latest_block() -> Any:
                if _rate_limiter is not None:
                    await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.blockNumber')
                return await http.get(url, params=signed_params, headers=headers)

            response: Any = await (
                _retry.run(_get_latest_block) if _retry is not None else _get_latest_block()
            )
            latest_hex: str | None = None
            if isinstance(response, dict):
                result = response.get('result', response)
                if isinstance(result, str):
                    latest_hex = result
            if latest_hex:
                end_block = int(latest_hex, 16) if latest_hex.startswith('0x') else int(latest_hex)
            else:
                raise ValueError('no result')
        except Exception:
            import time as _t

            params_block: dict[str, Any] = {
                'module': 'block',
                'action': 'getblocknobytime',
                'timestamp': int(_t.time()),
                'closest': 'before',
            }
            signed_params2, headers2 = endpoint.filter_and_sign(params_block, headers=None)

            async def _get_block_by_time() -> Any:
                if _rate_limiter is not None:
                    await _rate_limiter.acquire(key=f'{api_kind}:{network}:block.getblocknobytime')
                return await http.get(url, params=signed_params2, headers=headers2)

            resp2: Any = await (
                _retry.run(_get_block_by_time) if _retry is not None else _get_block_by_time()
            )
            if isinstance(resp2, dict):
                res2 = resp2.get('result', resp2)
                end_block = int(res2) if isinstance(res2, str | int) else 99_999_999

    if start_block is None:
        start_block = 0
    if end_block is not None and start_block is not None and end_block <= start_block:
        return []

    all_items: list[dict[str, Any]] = []
    pages_processed = 0

    if api_kind == 'eth':
        current_start = start_block
        while True:
            items = await get_internal_transactions(
                address=address,
                start_block=current_start,
                end_block=end_block,
                sort='asc',
                page=1,
                offset=max_offset,
                txhash=None,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=_endpoint_builder,
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
                last_block = (
                    int(last_block_str, 16)
                    if isinstance(last_block_str, str) and last_block_str.startswith('0x')
                    else int(str(last_block_str))
                )
            except Exception:
                break
            current_start = max(current_start, last_block + 1)
    else:
        page = 1
        while True:
            items = await get_internal_transactions(
                address=address,
                start_block=start_block,
                end_block=end_block,
                sort='asc',
                page=page,
                offset=max_offset,
                txhash=None,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=_endpoint_builder,
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

    # Dedup + sort
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for it in all_items:
        if not isinstance(it, dict):
            continue
        h = it.get('hash')
        if not isinstance(h, str) or h in seen:
            continue
        seen.add(h)
        unique.append(it)

    def _to_int2(v: Any) -> int:
        try:
            if isinstance(v, str):
                s = v.strip()
                if s.startswith('0x'):
                    return int(s, 16)
                return int(s)
            return int(v)
        except Exception:
            return 0

    unique.sort(
        key=lambda it: (_to_int2(it.get('blockNumber')), _to_int2(it.get('transactionIndex')))
    )
    if stats is not None:
        stats.update(
            {'pages_processed': pages_processed, 'items_total': len(all_items), 'paging_used': 1}
        )
    return unique


async def get_mined_blocks(
    *,
    address: str,
    blocktype: str,
    page: int | None,
    offset: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'getminedblocks',
        'address': address,
        'blocktype': blocktype,
        'page': page,
        'offset': offset,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_mined_blocks',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:getminedblocks',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_mined_blocks.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_mined_blocks.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
    return []


async def get_beacon_chain_withdrawals(
    *,
    address: str,
    start_block: int | None,
    end_block: int | None,
    sort: str | None,
    page: int | None,
    offset: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'txsBeaconWithdrawal',
        'address': address,
        'startblock': start_block,
        'endblock': end_block,
        'sort': sort,
        'page': page,
        'offset': offset,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_beacon_chain_withdrawals',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:txsBeaconWithdrawal',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_beacon_chain_withdrawals.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_beacon_chain_withdrawals.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
    return []


async def get_account_balance_by_blockno(
    *,
    address: str,
    blockno: int,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> str:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'balancehistory',
        'address': address,
        'blockno': blockno,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:balancehistory')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'account.get_account_balance_by_blockno.duration',
                    {'api_kind': api_kind, 'network': network, 'duration_ms': duration_ms},
                )

    response: Any = await (_retry.run(_do_request) if _retry is not None else _do_request())
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str | int):
            return str(result)
    return str(response)


# --- Normalizers for account list endpoints (pure helpers) ---


def _to_str(value: Any) -> str | None:
    try:
        if value is None:
            return None
        return str(value)
    except Exception:
        return None


def normalize_normal_txs(items: list[dict[str, Any]]) -> list[NormalTxDTO]:
    normalized: list[NormalTxDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'blockNumber': _to_str(it.get('blockNumber')),
                'timeStamp': _to_str(it.get('timeStamp')),
                'hash': _to_str(it.get('hash')),
                'nonce': _to_str(it.get('nonce')),
                'blockHash': _to_str(it.get('blockHash')),
                'transactionIndex': _to_str(it.get('transactionIndex')),
                'from_': _to_str(it.get('from') or it.get('from_')),
                'to': _to_str(it.get('to')),
                'value': _to_str(it.get('value')),
                'gas': _to_str(it.get('gas')),
                'gasPrice': _to_str(it.get('gasPrice')),
                'isError': _to_str(it.get('isError')),
                'txreceipt_status': _to_str(it.get('txreceipt_status')),
                'input': _to_str(it.get('input')),
                'contractAddress': _to_str(it.get('contractAddress')),
                'cumulativeGasUsed': _to_str(it.get('cumulativeGasUsed')),
                'gasUsed': _to_str(it.get('gasUsed')),
                'confirmations': _to_str(it.get('confirmations')),
            }
        )
    return normalized


def normalize_internal_txs(items: list[dict[str, Any]]) -> list[InternalTxDTO]:
    normalized: list[InternalTxDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'blockNumber': _to_str(it.get('blockNumber')),
                'timeStamp': _to_str(it.get('timeStamp')),
                'hash': _to_str(it.get('hash')),
                'from_': _to_str(it.get('from') or it.get('from_')),
                'to': _to_str(it.get('to')),
                'value': _to_str(it.get('value')),
                'contractAddress': _to_str(it.get('contractAddress')),
                'input': _to_str(it.get('input')),
                'type': _to_str(it.get('type')),
                'gas': _to_str(it.get('gas')),
                'gasUsed': _to_str(it.get('gasUsed')),
                'traceId': _to_str(it.get('traceId')),
                'isError': _to_str(it.get('isError')),
                'errCode': _to_str(it.get('errCode')),
            }
        )
    return normalized


def normalize_token_transfers(items: list[dict[str, Any]]) -> list[TokenTransferDTO]:
    normalized: list[TokenTransferDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'blockNumber': _to_str(it.get('blockNumber')),
                'timeStamp': _to_str(it.get('timeStamp')),
                'hash': _to_str(it.get('hash')),
                'nonce': _to_str(it.get('nonce')),
                'blockHash': _to_str(it.get('blockHash')),
                'from_': _to_str(it.get('from') or it.get('from_')),
                'contractAddress': _to_str(it.get('contractAddress')),
                'to': _to_str(it.get('to')),
                'value': _to_str(it.get('value')),
                'tokenName': _to_str(it.get('tokenName')),
                'tokenSymbol': _to_str(it.get('tokenSymbol')),
                'tokenDecimal': _to_str(it.get('tokenDecimal')),
                'transactionIndex': _to_str(it.get('transactionIndex')),
                'gas': _to_str(it.get('gas')),
                'gasPrice': _to_str(it.get('gasPrice')),
                'gasUsed': _to_str(it.get('gasUsed')),
                'cumulativeGasUsed': _to_str(it.get('cumulativeGasUsed')),
                'input': _to_str(it.get('input')),
                'confirmations': _to_str(it.get('confirmations')),
            }
        )
    return normalized


def normalize_mined_blocks(items: list[dict[str, Any]]) -> list[MinedBlockDTO]:
    normalized: list[MinedBlockDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'blockNumber': _to_str(it.get('blockNumber')),
                'timeStamp': _to_str(it.get('timeStamp')),
                'blockReward': _to_str(it.get('blockReward')),
            }
        )
    return normalized


def normalize_beacon_withdrawals(items: list[dict[str, Any]]) -> list[BeaconWithdrawalDTO]:
    normalized: list[BeaconWithdrawalDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'blockNumber': _to_str(it.get('blockNumber')),
                'timeStamp': _to_str(it.get('timeStamp')),
                'address': _to_str(it.get('address')),
                'amount': _to_str(it.get('amount')),
            }
        )
    return normalized


def normalize_address_balances(items: list[dict[str, Any]]) -> list[AddressBalanceDTO]:
    """Normalize multi-balance response items into `AddressBalanceDTO` list.

    Providers usually return entries like {'account': '0x..', 'balance': '123'}.
    This helper coerces balance to int when possible and renames fields.
    """

    def to_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except Exception:
            return None

    normalized: list[AddressBalanceDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'address': _to_str(it.get('account') or it.get('address')),
                'balance_wei': to_int(it.get('balance')),
            }
        )
    return normalized
