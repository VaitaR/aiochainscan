from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.core.context import ProviderContext
from aiochainscan.domain.dto_v2 import GasOracleDTO
from aiochainscan.services._executor import run_with_policies
from aiochainscan.services.constants import CACHE_TTL_GAS_SECONDS as CACHE_TTL_SECONDS


async def get_gas_oracle(
    *,
    ctx: ProviderContext,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch gas oracle info (Etherscan-compatible).

    Returns a provider-specific mapping. No normalization is performed at this layer.
    """

    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'gastracker',
        'action': 'gasoracle',
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    cache_key = f'gas_oracle:{ctx.api_kind}:{ctx.network}'
    if ctx.cache is not None:
        cached = await ctx.cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='gas.get_gas_oracle',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:gas_oracle',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            if ctx.cache is not None:
                await ctx.cache.set(cache_key, result, ttl_seconds=CACHE_TTL_SECONDS)
            if ctx.telemetry is not None:
                await ctx.telemetry.record_event(
                    'gas.get_gas_oracle.ok',
                    {'api_kind': ctx.api_kind, 'network': ctx.network},
                )
            return result
    return {}


async def get_gas_estimate(
    *,
    ctx: ProviderContext,
    gasprice_wei: int,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Get gas estimate via gastracker.gasestimate (provider-shaped)."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'gastracker',
        'action': 'gasestimate',
        'gasprice': gasprice_wei,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='gas.get_gas_estimate',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:gasestimate',
        retry_policy=ctx.retry,
    )
    return response if isinstance(response, dict) else {'result': response}


def normalize_gas_oracle(raw: dict[str, Any]) -> GasOracleDTO:
    """Normalize provider-shaped gas oracle payload to GasOracleDTO.

    Pydantic handles SafeGasPrice/ProposeGasPrice/FastGasPrice → Gwei-to-wei conversion.
    """
    return GasOracleDTO.model_validate(raw)
