from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any

from aiochainscan.domain.dto import ProxyTxDTO
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry


def _to_tag(value: int | str) -> str:
    if isinstance(value, int):
        return hex(value)
    s = str(value).strip().lower()
    return s


async def get_block_number(
    *,
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
) -> str:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_blockNumber',
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.blockNumber')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'proxy.get_block_number.duration',
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
                'proxy.get_block_number.error',
                exc,
                {'api_kind': api_kind, 'network': network},
            )
        raise

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            if _telemetry is not None:
                await _telemetry.record_event(
                    'proxy.get_block_number.ok',
                    {'api_kind': api_kind, 'network': network},
                )
            return result
    if _telemetry is not None:
        await _telemetry.record_event(
            'proxy.get_block_number.unexpected',
            {'api_kind': api_kind, 'network': network},
        )
    return str(response)


async def get_tx_by_hash(
    *,
    txhash: str,
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
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
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
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.txByHash')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'proxy.get_tx_by_hash.duration',
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
                'proxy.get_tx_by_hash.error',
                exc,
                {'api_kind': api_kind, 'network': network},
            )
        raise

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            if _telemetry is not None:
                await _telemetry.record_event(
                    'proxy.get_tx_by_hash.ok',
                    {'api_kind': api_kind, 'network': network},
                )
            return result
    return {}


def normalize_proxy_tx(raw: dict[str, Any]) -> ProxyTxDTO:
    """Normalize proxy.eth_getTransactionByHash result into ProxyTxDTO."""

    def hex_to_int(v: Any) -> int | None:
        try:
            if isinstance(v, str) and v.startswith('0x'):
                return int(v, 16)
            return int(v)
        except Exception:
            return None

    return {
        'tx_hash': raw.get('hash'),
        'block_number': hex_to_int(raw.get('blockNumber')),
        'from_address': raw.get('from'),
        'to_address': raw.get('to'),
        'value_wei': hex_to_int(raw.get('value')),
        'gas': hex_to_int(raw.get('gas')),
        'gas_price_wei': hex_to_int(raw.get('gasPrice')),
        'nonce': hex_to_int(raw.get('nonce')),
        'input': raw.get('input'),
    }


async def get_gas_price(
    *,
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
        'module': 'proxy',
        'action': 'eth_gasPrice',
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.gasPrice')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'proxy.get_gas_price.duration',
                    {'api_kind': api_kind, 'network': network, 'duration_ms': duration_ms},
                )

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_tx_count(
    *,
    address: str,
    tag: int | str,
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
        'module': 'proxy',
        'action': 'eth_getTransactionCount',
        'address': address,
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.txCount')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'proxy.get_tx_count.duration',
                    {'api_kind': api_kind, 'network': network, 'duration_ms': duration_ms},
                )

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_code(
    *,
    address: str,
    tag: int | str,
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
        'module': 'proxy',
        'action': 'eth_getCode',
        'address': address,
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.getCode')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'proxy.get_code.duration',
                    {'api_kind': api_kind, 'network': network, 'duration_ms': duration_ms},
                )

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def eth_call(
    *,
    to: str,
    data: str,
    tag: int | str,
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
        'module': 'proxy',
        'action': 'eth_call',
        'to': to,
        'data': data,
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.ethCall')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'proxy.eth_call.duration',
                    {'api_kind': api_kind, 'network': network, 'duration_ms': duration_ms},
                )

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_storage_at(
    *,
    address: str,
    position: str,
    tag: int | str,
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
        'module': 'proxy',
        'action': 'eth_getStorageAt',
        'address': address,
        'position': position,
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.getStorageAt')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'proxy.get_storage_at.duration',
                    {'api_kind': api_kind, 'network': network, 'duration_ms': duration_ms},
                )

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_block_tx_count_by_number(
    *,
    tag: int | str,
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
        'module': 'proxy',
        'action': 'eth_getBlockTransactionCountByNumber',
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.blockTxCount')
        return await http.get(url, params=signed_params, headers=headers)

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def get_tx_by_block_number_and_index(
    *,
    tag: int | str,
    index: int | str,
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
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
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

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.txByBlockIndex')
        return await http.get(url, params=signed_params, headers=headers)

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            return result
    return {}


async def get_uncle_by_block_number_and_index(
    *,
    tag: int | str,
    index: int | str,
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
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
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

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.uncleByBlockIndex')
        return await http.get(url, params=signed_params, headers=headers)

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            return result
    return {}


async def estimate_gas(
    *,
    to: str,
    value: str,
    gas_price: str,
    gas: str,
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

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.estimateGas')
        return await http.get(url, params=signed_params, headers=headers)

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str):
            return result
    return str(response)


async def send_raw_tx(
    *,
    raw_hex: str,
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
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    data: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_sendRawTransaction',
        'hex': raw_hex,
    }
    if extra_params:
        data.update({k: v for k, v in extra_params.items() if v is not None})

    signed_data, headers = endpoint.filter_and_sign(data, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.sendRawTx')
        return await http.post(url, data=signed_data, headers=headers)

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        return response
    return {'result': response}


async def get_tx_receipt(
    *,
    txhash: str,
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
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getTransactionReceipt',
        'txhash': txhash,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:proxy.txReceipt')
        return await http.get(url, params=signed_params, headers=headers)

    response: Any
    if _retry is not None:
        response = await _retry.run(_do_request)
    else:
        response = await _do_request()

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            return result
    return {}
