from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any

from aiochainscan.core.context import ProviderContext


async def get_contract_abi(
    *,
    ctx: ProviderContext,
    address: str,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'contract',
        'action': 'getabi',
        'address': address,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if ctx.rate_limiter is not None:
            await ctx.rate_limiter.acquire(key=f'{ctx.api_kind}:{ctx.network}:contract.getabi')
        start = monotonic()
        try:
            return await ctx.http.get(url, params=signed_params, headers=headers)
        finally:
            if ctx.telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await ctx.telemetry.record_event(
                    'contract.get_abi.duration',
                    {'api_kind': ctx.api_kind, 'network': ctx.network, 'duration_ms': duration_ms},
                )

    response: Any
    if ctx.retry is not None:
        response = await ctx.retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, str):
        if ctx.telemetry is not None:
            await ctx.telemetry.record_event(
                'contract.get_abi.ok', {'api_kind': ctx.api_kind, 'network': ctx.network}
            )
        return response
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            if ctx.telemetry is not None:
                await ctx.telemetry.record_event(
                    'contract.get_abi.ok', {'api_kind': ctx.api_kind, 'network': ctx.network}
                )
            return result
    if ctx.telemetry is not None:
        await ctx.telemetry.record_event(
            'contract.get_abi.unexpected', {'api_kind': ctx.api_kind, 'network': ctx.network}
        )
    return str(response)


async def get_contract_source_code(
    *,
    ctx: ProviderContext,
    address: str,
    extra_params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'contract',
        'action': 'getsourcecode',
        'address': address,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    start = monotonic()

    async def _do_request() -> Any:
        if ctx.rate_limiter is not None:
            await ctx.rate_limiter.acquire(
                key=f'{ctx.api_kind}:{ctx.network}:contract.getsourcecode'
            )
        try:
            return await ctx.http.get(url, params=signed_params, headers=headers)
        finally:
            if ctx.telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await ctx.telemetry.record_event(
                    'contract.get_source_code.duration',
                    {'api_kind': ctx.api_kind, 'network': ctx.network, 'duration_ms': duration_ms},
                )

    response: Any
    if ctx.retry is not None:
        response = await ctx.retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if ctx.telemetry is not None:
                await ctx.telemetry.record_event(
                    'contract.get_source_code.ok',
                    {'api_kind': ctx.api_kind, 'network': ctx.network, 'items': len(out)},
                )
            return out
    if ctx.telemetry is not None:
        await ctx.telemetry.record_event(
            'contract.get_source_code.unexpected',
            {'api_kind': ctx.api_kind, 'network': ctx.network},
        )
    return []


async def verify_contract_source_code(
    *,
    ctx: ProviderContext,
    contract_address: str,
    source_code: str,
    contract_name: str,
    compiler_version: str,
    optimization_used: bool,
    runs: int,
    constructor_arguements: str,
    libraries: Mapping[str, str] | None = None,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    data: dict[str, Any] = {
        'module': 'contract',
        'action': 'verifysourcecode',
        'contractaddress': contract_address,
        'sourceCode': source_code,
        'contractname': contract_name,
        'compilerversion': compiler_version,
        'optimizationUsed': 1 if optimization_used else 0,
        'runs': runs,
        'constructorArguements': constructor_arguements,
    }
    if libraries:
        idx: int = 1
        for name, addr in libraries.items():
            data[f'libraryname{idx}'] = name
            data[f'libraryaddress{idx}'] = addr
            idx += 1
    if extra_params:
        data.update({k: v for k, v in extra_params.items() if v is not None})

    signed_data, headers = endpoint.filter_and_sign(data, headers=None)
    start = monotonic()

    async def _do_request() -> Any:
        if ctx.rate_limiter is not None:
            await ctx.rate_limiter.acquire(
                key=f'{ctx.api_kind}:{ctx.network}:contract.verifysourcecode'
            )
        try:
            return await ctx.http.post(url, data=signed_data, headers=headers)
        finally:
            if ctx.telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await ctx.telemetry.record_event(
                    'contract.verify_source_code.duration',
                    {'api_kind': ctx.api_kind, 'network': ctx.network, 'duration_ms': duration_ms},
                )

    response: Any
    if ctx.retry is not None:
        response = await ctx.retry.run(_do_request)
    else:
        response = await _do_request()
    if isinstance(response, dict):
        if ctx.telemetry is not None:
            await ctx.telemetry.record_event(
                'contract.verify_source_code.ok',
                {'api_kind': ctx.api_kind, 'network': ctx.network},
            )
        return response
    return {'result': response}


async def check_verification_status(
    *,
    ctx: ProviderContext,
    guid: str,
) -> dict[str, Any]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params = {'module': 'contract', 'action': 'checkverifystatus', 'guid': guid}
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    start = monotonic()

    async def _do_request() -> Any:
        if ctx.rate_limiter is not None:
            await ctx.rate_limiter.acquire(
                key=f'{ctx.api_kind}:{ctx.network}:contract.checkverifystatus'
            )
        try:
            return await ctx.http.get(url, params=signed_params, headers=headers)
        finally:
            if ctx.telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await ctx.telemetry.record_event(
                    'contract.check_verification_status.duration',
                    {'api_kind': ctx.api_kind, 'network': ctx.network, 'duration_ms': duration_ms},
                )

    response: Any
    if ctx.retry is not None:
        response = await ctx.retry.run(_do_request)
    else:
        response = await _do_request()
    if isinstance(response, dict):
        if ctx.telemetry is not None:
            await ctx.telemetry.record_event(
                'contract.check_verification_status.ok',
                {'api_kind': ctx.api_kind, 'network': ctx.network},
            )
        return response
    return {'result': response}


async def verify_proxy_contract(
    *,
    ctx: ProviderContext,
    address: str,
    expected_implementation: str | None,
) -> dict[str, Any]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    data: dict[str, Any] = {
        'module': 'contract',
        'action': 'verifyproxycontract',
        'address': address,
        'expectedimplementation': expected_implementation,
    }
    signed_data, headers = endpoint.filter_and_sign(data, headers=None)
    start = monotonic()

    async def _do_request() -> Any:
        if ctx.rate_limiter is not None:
            await ctx.rate_limiter.acquire(
                key=f'{ctx.api_kind}:{ctx.network}:contract.verifyproxycontract'
            )
        try:
            return await ctx.http.post(url, data=signed_data, headers=headers)
        finally:
            if ctx.telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await ctx.telemetry.record_event(
                    'contract.verify_proxy_contract.duration',
                    {'api_kind': ctx.api_kind, 'network': ctx.network, 'duration_ms': duration_ms},
                )

    response: Any
    if ctx.retry is not None:
        response = await ctx.retry.run(_do_request)
    else:
        response = await _do_request()
    if isinstance(response, dict):
        if ctx.telemetry is not None:
            await ctx.telemetry.record_event(
                'contract.verify_proxy_contract.ok',
                {'api_kind': ctx.api_kind, 'network': ctx.network},
            )
        return response
    return {'result': response}


async def check_proxy_contract_verification(
    *,
    ctx: ProviderContext,
    guid: str,
) -> dict[str, Any]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params = {'module': 'contract', 'action': 'checkproxyverification', 'guid': guid}
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any
    if ctx.retry is not None:
        response = await ctx.retry.run(
            lambda: ctx.http.get(url, params=signed_params, headers=headers)
        )
    else:
        response = await ctx.http.get(url, params=signed_params, headers=headers)
    return response if isinstance(response, dict) else {'result': response}


async def get_contract_creation(
    *,
    ctx: ProviderContext,
    contract_addresses: list[str],
) -> list[dict[str, Any]]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'contract',
        'action': 'getcontractcreation',
        'contractaddresses': ','.join(contract_addresses),
    }
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    start = monotonic()

    async def _do_request() -> Any:
        if ctx.rate_limiter is not None:
            await ctx.rate_limiter.acquire(
                key=f'{ctx.api_kind}:{ctx.network}:contract.getcontractcreation'
            )
        try:
            return await ctx.http.get(url, params=signed_params, headers=headers)
        finally:
            if ctx.telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await ctx.telemetry.record_event(
                    'contract.get_contract_creation.duration',
                    {'api_kind': ctx.api_kind, 'network': ctx.network, 'duration_ms': duration_ms},
                )

    response: Any
    if ctx.retry is not None:
        response = await ctx.retry.run(_do_request)
    else:
        response = await _do_request()
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if ctx.telemetry is not None:
                await ctx.telemetry.record_event(
                    'contract.get_contract_creation.ok',
                    {'api_kind': ctx.api_kind, 'network': ctx.network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if ctx.telemetry is not None:
            await ctx.telemetry.record_event(
                'contract.get_contract_creation.ok',
                {'api_kind': ctx.api_kind, 'network': ctx.network, 'items': len(out)},
            )
        return out
    if ctx.telemetry is not None:
        await ctx.telemetry.record_event(
            'contract.get_contract_creation.unexpected',
            {'api_kind': ctx.api_kind, 'network': ctx.network},
        )
    return []
