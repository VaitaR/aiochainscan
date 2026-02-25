from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.adapters.smart_data_provider import SmartDataProvider
from aiochainscan.core.context import ProviderContext
from aiochainscan.domain.dto_v2 import TransactionDTO
from aiochainscan.domain.models import TxHash
from aiochainscan.services._executor import run_with_policies

CACHE_TTL_SECONDS: int = 10


async def get_transaction_by_hash(
    *,
    ctx: ProviderContext,
    txhash: TxHash,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch transaction details by transaction hash.

    Tries GraphQL first when available; falls back to REST proxy otherwise.
    """
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    cache_key = f'tx:{ctx.api_kind}:{ctx.network}:{txhash}'

    provider = SmartDataProvider(ctx)

    async def _rest_fallback() -> dict[str, Any]:
        params: dict[str, Any] = {
            'module': 'proxy',
            'action': 'eth_getTransactionByHash',
            'txhash': str(txhash),
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
            telemetry_name='transaction.get_transaction_by_hash',
            api_kind=ctx.api_kind,
            network=ctx.network,
            rate_limiter=ctx.rate_limiter,
            rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:tx',
            retry_policy=ctx.retry,
        )

        out: dict[str, Any] = {}
        if isinstance(response, dict):
            result = response.get('result', response)
            if isinstance(result, dict):
                out = result

        if ctx.telemetry is not None:
            await ctx.telemetry.record_event(
                'transaction.get_transaction_by_hash.ok',
                {
                    'api_kind': ctx.api_kind,
                    'network': ctx.network,
                },
            )

        if ctx.cache is not None and out:
            await ctx.cache.set(cache_key, out, ttl_seconds=CACHE_TTL_SECONDS)

        return out

    return await provider.fetch_transaction_by_hash(
        txhash=txhash,
        cache_key=cache_key,
        cache_ttl_seconds=CACHE_TTL_SECONDS,
        rest_fallback=_rest_fallback,
    )


def normalize_transaction(raw: dict[str, Any]) -> TransactionDTO:
    """Normalize provider-shaped transaction into TransactionDTO.

    Pydantic handles all field aliases and hex→int conversion automatically.
    """
    return TransactionDTO.model_validate(raw)


async def get_tx_receipt_status(
    *,
    ctx: ProviderContext,
    txhash: TxHash,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """[BETA] Check Transaction Receipt Status (post-Byzantium)."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'transaction',
        'action': 'gettxreceiptstatus',
        'txhash': str(txhash),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='transaction.get_tx_receipt_status',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:gettxreceiptstatus',
        retry_policy=ctx.retry,
    )
    return response if isinstance(response, dict) else {'result': response}


async def get_contract_execution_status(
    *,
    ctx: ProviderContext,
    txhash: TxHash,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """[BETA] Check Contract Execution Status (provider-shaped)."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'transaction',
        'action': 'getstatus',
        'txhash': str(txhash),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='transaction.get_contract_execution_status',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:getstatus',
        retry_policy=ctx.retry,
    )
    return response if isinstance(response, dict) else {'result': response}
