from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any

from aiochainscan.core.context import ProviderContext
from aiochainscan.domain.dto_v2 import TransactionDTO
from aiochainscan.services._executor import run_with_policies


def _to_tag(value: int | str) -> str:
    if isinstance(value, int):
        return hex(value)
    s = str(value).strip().lower()
    return s


async def get_balance(
    *,
    ctx: ProviderContext,
    address: str,
    tag: int | str,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getBalance',
        'address': address,
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.get_balance',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.getBalance',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_block_number(
    *,
    ctx: ProviderContext,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_blockNumber',
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.get_block_number',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.blockNumber',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            if ctx.telemetry is not None:
                await ctx.telemetry.record_event(
                    'proxy.get_block_number.ok',
                    {'api_kind': ctx.api_kind, 'network': ctx.network},
                )
            return result
    if ctx.telemetry is not None:
        await ctx.telemetry.record_event(
            'proxy.get_block_number.unexpected',
            {'api_kind': ctx.api_kind, 'network': ctx.network},
        )
    return str(response)


async def get_tx_by_hash(
    *,
    ctx: ProviderContext,
    txhash: str,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getTransactionByHash',
        'txhash': txhash,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if ctx.rate_limiter is not None:
            await ctx.rate_limiter.acquire(key=f'{ctx.api_kind}:{ctx.network}:proxy.txByHash')
        start = monotonic()
        try:
            return await ctx.http.get(url, params=signed_params, headers=headers)
        finally:
            if ctx.telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await ctx.telemetry.record_event(
                    'proxy.get_tx_by_hash.duration',
                    {'api_kind': ctx.api_kind, 'network': ctx.network, 'duration_ms': duration_ms},
                )

    try:
        if ctx.retry is not None:
            response: Any = await ctx.retry.run(_do_request)
        else:
            response = await _do_request()
    except Exception as exc:  # noqa: BLE001
        if ctx.telemetry is not None:
            await ctx.telemetry.record_error(
                'proxy.get_tx_by_hash.error',
                exc,
                {'api_kind': ctx.api_kind, 'network': ctx.network},
            )
        raise

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            if ctx.telemetry is not None:
                await ctx.telemetry.record_event(
                    'proxy.get_tx_by_hash.ok',
                    {'api_kind': ctx.api_kind, 'network': ctx.network},
                )
            return result
    return {}


def normalize_proxy_tx(raw: dict[str, Any]) -> TransactionDTO:
    """Normalize proxy.eth_getTransactionByHash result into TransactionDTO."""
    return TransactionDTO.model_validate(raw)


async def get_gas_price(
    *,
    ctx: ProviderContext,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_gasPrice',
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.get_gas_price',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.gasPrice',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_tx_count(
    *,
    ctx: ProviderContext,
    address: str,
    tag: int | str,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getTransactionCount',
        'address': address,
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.get_tx_count',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.txCount',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_code(
    *,
    ctx: ProviderContext,
    address: str,
    tag: int | str,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getCode',
        'address': address,
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.get_code',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.getCode',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def eth_call(
    *,
    ctx: ProviderContext,
    to: str,
    data: str,
    tag: int | str,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_call',
        'to': to,
        'data': data,
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.eth_call',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.ethCall',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_storage_at(
    *,
    ctx: ProviderContext,
    address: str,
    position: str,
    tag: int | str,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getStorageAt',
        'address': address,
        'position': position,
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.get_storage_at',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.getStorageAt',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_block_tx_count_by_number(
    *,
    ctx: ProviderContext,
    tag: int | str,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getBlockTransactionCountByNumber',
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.get_block_tx_count_by_number',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.blockTxCount',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_tx_by_block_number_and_index(
    *,
    ctx: ProviderContext,
    tag: int | str,
    index: int | str,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getTransactionByBlockNumberAndIndex',
        'tag': _to_tag(tag),
        'index': _to_tag(index),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.get_tx_by_block_number_and_index',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.txByBlockIndex',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            return result
    return {}


async def get_uncle_by_block_number_and_index(
    *,
    ctx: ProviderContext,
    tag: int | str,
    index: int | str,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getUncleByBlockNumberAndIndex',
        'tag': _to_tag(tag),
        'index': _to_tag(index),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.get_uncle_by_block_number_and_index',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.uncleByBlockIndex',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            return result
    return {}


async def estimate_gas(
    *,
    ctx: ProviderContext,
    to: str,
    value: str,
    gas_price: str,
    gas: str,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_estimateGas',
        'to': to,
        'value': value,
        'gasPrice': gas_price,
        'gas': gas,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.estimate_gas',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.estimateGas',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def send_raw_tx(
    *,
    ctx: ProviderContext,
    raw_hex: str,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    data: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_sendRawTransaction',
        'hex': raw_hex,
    }
    if extra_params:
        data.update({k: v for k, v in extra_params.items() if v is not None})

    signed_data, headers = endpoint.filter_and_sign(data, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.post(url, data=signed_data, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.send_raw_tx',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.sendRawTx',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        return response
    return {'result': response}


async def get_tx_receipt(
    *,
    ctx: ProviderContext,
    txhash: str,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getTransactionReceipt',
        'txhash': txhash,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='proxy.get_tx_receipt',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:proxy.txReceipt',
        retry_policy=ctx.retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            return result
    return {}
