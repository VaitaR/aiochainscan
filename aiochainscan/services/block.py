from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.core.context import ProviderContext
from aiochainscan.domain.dto_v2 import BlockDTO
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
    ctx: ProviderContext,
    tag: int | str,
    full: bool,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch block by number via proxy.eth_getBlockByNumber."""

    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    cache_key = f'block:{ctx.api_kind}:{ctx.network}:{_to_tag(tag)}:{full}'

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getBlockByNumber',
        'boolean': str(full).lower(),
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    if ctx.cache is not None:
        cached = await ctx.cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='block.get_block_by_number',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:block',
        retry_policy=ctx.retry,
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

    if ctx.telemetry is not None:
        await ctx.telemetry.record_event(
            'block.get_block_by_number.ok',
            {
                'api_kind': ctx.api_kind,
                'network': ctx.network,
            },
        )

    if ctx.cache is not None:
        await ctx.cache.set(cache_key, out, ttl_seconds=CACHE_TTL_SECONDS)

    return out


async def get_block_countdown(
    *,
    ctx: ProviderContext,
    block_no: int,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Get Estimated Block Countdown Time by BlockNo via provider endpoint.

    Returns provider-shaped dict or None when provider reports no data
    (e.g., "No transactions found").
    """

    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
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
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='block.get_block_countdown',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:getblockcountdown',
        retry_policy=ctx.retry,
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

    if ctx.telemetry is not None:
        await ctx.telemetry.record_event(
            'block.get_block_countdown.ok', {'api_kind': ctx.api_kind, 'network': ctx.network}
        )

    return out


async def get_block_reward(
    *,
    ctx: ProviderContext,
    block_no: int,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Get Block And Uncle Rewards by BlockNo.

    Returns provider-shaped dict or None when provider reports no reward/status=0.
    """

    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
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
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='block.get_block_reward',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:getblockreward',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict) and response.get('status') == '0':
        return None
    if isinstance(response, dict):
        result = response.get('result', response)
        return result if isinstance(result, dict) else dict(response)
    return {'result': response}


async def get_block_number_by_timestamp(
    *,
    ctx: ProviderContext,
    ts: int,
    closest: str,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Get Block Number by Timestamp (Etherscan-compatible)."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
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
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='block.get_block_number_by_timestamp',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:getblocknobytime',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        return result if isinstance(result, dict) else dict(response)
    return {'result': response}


def normalize_block(raw: dict[str, Any]) -> BlockDTO:
    """Normalize provider-shaped block into BlockDTO.

    Pre-processes JSON-RPC field name variants before Pydantic validation:
    - 'number' (JSON-RPC) → 'blockNumber' (Etherscan alias in BlockDTO)
    - 'author' (some clients) → 'miner'
    - Derives 'txCount' from 'transactions' list when present
    """
    data = dict(raw)
    # JSON-RPC eth_getBlockByNumber uses 'number', Etherscan uses 'blockNumber'
    if 'number' in data and 'blockNumber' not in data:
        data['blockNumber'] = data['number']
    # Some chain clients use 'author' instead of 'miner'
    if not data.get('miner') and data.get('author'):
        data['miner'] = data['author']
    # Derive txCount from the transactions list when the field is absent
    txs = data.get('transactions')
    if isinstance(txs, list) and 'txCount' not in data:
        data['txCount'] = len(txs)
    return BlockDTO.model_validate(data)
