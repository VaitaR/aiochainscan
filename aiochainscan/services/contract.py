from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry


async def get_contract_abi(
    *,
    address: str,
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
        'module': 'contract',
        'action': 'getabi',
        'address': address,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:contract.getabi')
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                await _telemetry.record_event(
                    'contract.get_abi.duration',
                    {'api_kind': api_kind, 'network': network},
                )

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_contract_source_code(
    *,
    address: str,
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
        'module': 'contract',
        'action': 'getsourcecode',
        'address': address,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any
    if _retry is not None:
        response = await _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
    else:
        response = await http.get(url, params=signed_params, headers=headers)

    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    return []


async def verify_contract_source_code(
    *,
    contract_address: str,
    source_code: str,
    contract_name: str,
    compiler_version: str,
    optimization_used: bool,
    runs: int,
    constructor_arguements: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    libraries: Mapping[str, str] | None = None,
    extra_params: Mapping[str, Any] | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
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
    response: Any
    if _retry is not None:
        response = await _retry.run(lambda: http.post(url, data=signed_data, headers=headers))
    else:
        response = await http.post(url, data=signed_data, headers=headers)
    return response if isinstance(response, dict) else {'result': response}


async def check_verification_status(
    *,
    guid: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params = {'module': 'contract', 'action': 'checkverifystatus', 'guid': guid}
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any
    if _retry is not None:
        response = await _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
    else:
        response = await http.get(url, params=signed_params, headers=headers)
    return response if isinstance(response, dict) else {'result': response}


async def verify_proxy_contract(
    *,
    address: str,
    expected_implementation: str | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    data: dict[str, Any] = {
        'module': 'contract',
        'action': 'verifyproxycontract',
        'address': address,
        'expectedimplementation': expected_implementation,
    }
    signed_data, headers = endpoint.filter_and_sign(data, headers=None)
    response: Any
    if _retry is not None:
        response = await _retry.run(lambda: http.post(url, data=signed_data, headers=headers))
    else:
        response = await http.post(url, data=signed_data, headers=headers)
    return response if isinstance(response, dict) else {'result': response}


async def check_proxy_contract_verification(
    *,
    guid: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params = {'module': 'contract', 'action': 'checkproxyverification', 'guid': guid}
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any
    if _retry is not None:
        response = await _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
    else:
        response = await http.get(url, params=signed_params, headers=headers)
    return response if isinstance(response, dict) else {'result': response}


async def get_contract_creation(
    *,
    contract_addresses: list[str],
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'contract',
        'action': 'getcontractcreation',
        'contractaddresses': ','.join(contract_addresses),
    }
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any
    if _retry is not None:
        response = await _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
    else:
        response = await http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []
