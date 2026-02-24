from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any

from aiochainscan.constants import MAX_BLOCK_NUMBER
from aiochainscan.domain.dto import (
    AddressBalanceDTO,
    BeaconWithdrawalDTO,
    InternalTxDTO,
    MinedBlockDTO,
    NormalTxDTO,
    TokenTransferDTO,
)
from aiochainscan.domain.dto_v2 import parse_hex_or_int_zero
from aiochainscan.domain.models import Address
from aiochainscan.exceptions import ChainscanClientError
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services._executor import run_with_policies

CACHE_TTL_SECONDS_BALANCE: int = 10


# ============================================================================
# DRY Helper Functions - Extracted common patterns for account module
# ============================================================================


async def _fetch_account_list_data(
    *,
    action: str,
    params: dict[str, Any],
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
    telemetry_name: str | None = None,
    preserve_none: bool = False,
) -> list[dict[str, Any]]:
    """
    Generic helper for fetching account-related list data from blockchain explorers.

    This consolidates the common pattern used across:
    - get_normal_transactions
    - get_internal_transactions
    - get_token_transfers
    - get_mined_blocks
    - get_beacon_chain_withdrawals

    Args:
        action: The API action (e.g., 'txlist', 'txlistinternal', 'tokentx')
        params: Base parameters dict (will be merged with module='account' and action)
        api_kind: Scanner identifier (e.g., 'eth', 'bsc')
        network: Network name (e.g., 'main', 'test')
        api_key: API key for the scanner
        http: HTTP client port
        _endpoint_builder: Endpoint builder for URL construction
        extra_params: Additional params to merge
        _rate_limiter: Optional rate limiter
        _retry: Optional retry policy
        _telemetry: Optional telemetry recorder
        telemetry_name: Name for telemetry events (defaults to f'account.{action}')
        preserve_none: Whether to keep None values in params

    Returns:
        List of dict results from the API
    """
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url

    # Build final params with module and action
    final_params: dict[str, Any] = {'module': 'account', 'action': action, **params}

    # Filter None values unless preserve_none is True
    if not preserve_none:
        final_params = {k: v for k, v in final_params.items() if v is not None}

    # Merge extra params
    if extra_params:
        final_params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(final_params, headers=None)

    # Determine telemetry name
    telem_name = telemetry_name or f'account.{action}'
    rate_limiter_key = f'{api_kind}:{network}:{action}'

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name=telem_name,
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=rate_limiter_key,
        retry_policy=_retry,
    )

    # Parse response - common pattern for all list endpoints
    out = _parse_list_response(response=response)

    # Record telemetry for successful list responses
    if _telemetry is not None and out:
        await _telemetry.record_event(
            f'{telem_name}.ok',
            {'api_kind': api_kind, 'network': network, 'items': len(out)},
        )

    return out


def _parse_list_response(*, response: Any) -> list[dict[str, Any]]:
    """
    Parse API response for list endpoints with common logic.

    Handles both:
    - Etherscan-style: {"status": "1", "result": [...]}
    - Direct list responses: [...]

    Note: This is a synchronous helper. Telemetry recording is deferred
    to the caller to maintain DRY principle while keeping this function simple.
    """
    out: list[dict[str, Any]] = []

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
    elif isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]

    return out


# ============================================================================
# Public API Functions
# ============================================================================


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
        except (ValueError, TypeError):
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
    return await _fetch_account_list_data(
        action='balancemulti',
        params={
            'address': ','.join(addresses),
            'tag': tag,
        },
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        extra_params=extra_params,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
        telemetry_name='account.get_address_balances',
    )


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
    return await _fetch_account_list_data(
        action='txlist',
        params={
            'address': address,
            'startblock': start_block,
            'endblock': end_block,
            'sort': sort,
            'page': page,
            'offset': offset,
        },
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        extra_params=extra_params,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
        telemetry_name='account.get_normal_transactions',
    )


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
    return await _fetch_account_list_data(
        action='txlistinternal',
        params={
            'address': address,
            'startblock': start_block,
            'endblock': end_block,
            'sort': sort,
            'page': page,
            'offset': offset,
            'txhash': txhash,
        },
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        extra_params=extra_params,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
        telemetry_name='account.get_internal_transactions',
    )


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
    actions = {'erc20': 'tokentx', 'erc721': 'tokennfttx', 'erc1155': 'token1155tx'}
    action = actions.get(token_standard, 'tokentx')

    return await _fetch_account_list_data(
        action=action,
        params={
            'address': address,
            'contractaddress': contract_address,
            'startblock': start_block,
            'endblock': end_block,
            'sort': sort,
            'page': page,
            'offset': offset,
        },
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        extra_params=extra_params,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
        telemetry_name='account.get_token_transfers',
        preserve_none=preserve_none,
    )


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
    # Use unified facade; fallback to legacy fetch_all wrappers if unified module is unavailable.
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
    except (ImportError, AttributeError):
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
        except (ValueError, TypeError, KeyError, ChainscanClientError):
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
                end_block = int(res2) if isinstance(res2, str | int) else MAX_BLOCK_NUMBER

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
            except (ValueError, TypeError):
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

    unique.sort(
        key=lambda it: (
            parse_hex_or_int_zero(it.get('blockNumber')),
            parse_hex_or_int_zero(it.get('transactionIndex')),
        )
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
    return await _fetch_account_list_data(
        action='getminedblocks',
        params={
            'address': address,
            'blocktype': blocktype,
            'page': page,
            'offset': offset,
        },
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        extra_params=extra_params,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
        telemetry_name='account.get_mined_blocks',
    )


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
    return await _fetch_account_list_data(
        action='txsBeaconWithdrawal',
        params={
            'address': address,
            'startblock': start_block,
            'endblock': end_block,
            'sort': sort,
            'page': page,
            'offset': offset,
        },
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        extra_params=extra_params,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
        telemetry_name='account.get_beacon_chain_withdrawals',
    )


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
    except (ValueError, TypeError):
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
        except (ValueError, TypeError):
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
