from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.domain.dto import BlockDTO
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services._executor import run_with_policies

CACHE_TTL_SECONDS: int = 5


def _to_tag(value: int | str) -> str:
    if isinstance(value, int):
        return hex(value)
    s = value.strip().lower()
    if s == 'latest' or s.startswith('0x'):
        return s
    if s.isdigit():
        return hex(int(s))
    # Fallback: pass-through (provider may error)
    return s


async def get_block_by_number(
    *,
    tag: int | str,
    full: bool,
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
) -> dict[str, Any]:
    """Fetch block by number via proxy.eth_getBlockByNumber."""

    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    cache_key = f'block:{api_kind}:{network}:{_to_tag(tag)}:{full}'

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getBlockByNumber',
        'boolean': str(full).lower(),
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    if _cache is not None:
        cached = await _cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='block.get_block_by_number',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:block',
        retry_policy=_retry,
    )

    out: dict[str, Any]
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            out = result
        else:
            out = dict(response) if isinstance(response, Mapping) else {'result': response}
    else:
        out = dict(response) if isinstance(response, Mapping) else {'result': response}

    if _telemetry is not None:
        await _telemetry.record_event(
            'block.get_block_by_number.ok',
            {
                'api_kind': api_kind,
                'network': network,
            },
        )

    if _cache is not None:
        await _cache.set(cache_key, out, ttl_seconds=CACHE_TTL_SECONDS)

    return out


async def get_block_countdown(
    *,
    block_no: int,
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
) -> dict[str, Any] | None:
    """Get Estimated Block Countdown Time by BlockNo via provider endpoint.

    Returns provider-shaped dict or None when provider reports no data
    (e.g., "No transactions found").
    """

    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'block',
        'action': 'getblockcountdown',
        'blockno': block_no,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='block.get_block_countdown',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:getblockcountdown',
        retry_policy=_retry,
    )

    # Handle API responses
    if isinstance(response, dict) and response.get('status') == '0':
        message_raw = str(response.get('message', ''))
        message = message_raw.lower()
        if message.startswith('no transactions found'):
            return None
        # Raise ValueError for provider error messages to match tests semantics
        raise ValueError(message_raw)

    # Normalize to dict-like
    out: dict[str, Any]
    if isinstance(response, dict):
        result = response.get('result', response)
        out = result if isinstance(result, dict) else dict(response)
    else:
        out = {'result': response}

    if _telemetry is not None:
        await _telemetry.record_event(
            'block.get_block_countdown.ok', {'api_kind': api_kind, 'network': network}
        )

    return out


async def get_block_reward(
    *,
    block_no: int,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> dict[str, Any] | None:
    """Get Block And Uncle Rewards by BlockNo.

    Returns provider-shaped dict or None when provider reports no reward/status=0.
    """

    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'block',
        'action': 'getblockreward',
        'blockno': block_no,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='block.get_block_reward',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:getblockreward',
        retry_policy=_retry,
    )

    if isinstance(response, dict) and response.get('status') == '0':
        return None
    if isinstance(response, dict):
        result = response.get('result', response)
        return result if isinstance(result, dict) else dict(response)
    return {'result': response}


async def get_block_number_by_timestamp(
    *,
    ts: int,
    closest: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    """Get Block Number by Timestamp (Etherscan-compatible)."""
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'block',
        'action': 'getblocknobytime',
        'timestamp': ts,
        'closest': closest,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='block.get_block_number_by_timestamp',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:getblocknobytime',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        return result if isinstance(result, dict) else dict(response)
    return {'result': response}


def normalize_block(raw: dict[str, Any]) -> BlockDTO:
    """Normalize provider-shaped block into BlockDTO."""

    def hex_to_int(h: str | None) -> int | None:
        if not h:
            return None
        try:
            return int(h, 16) if isinstance(h, str) and h.startswith('0x') else int(h)
        except Exception:
            return None

    txs = raw.get('transactions')
    tx_count: int | None = len(txs) if isinstance(txs, list) else None

    return {
        'block_number': hex_to_int(raw.get('number') or raw.get('blockNumber')),
        'hash': raw.get('hash'),
        'parent_hash': raw.get('parentHash'),
        'miner': raw.get('miner') or raw.get('author'),
        'timestamp': hex_to_int(raw.get('timestamp')),
        'gas_limit': hex_to_int(raw.get('gasLimit')),
        'gas_used': hex_to_int(raw.get('gasUsed')),
        'tx_count': tx_count,
    }
