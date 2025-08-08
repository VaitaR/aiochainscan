from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any

from aiochainscan.domain.dto import (
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


async def get_address_balance(
    *,
    address: Address,
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

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:balance')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'account.get_balance.duration',
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
                'get_address_balance.error',
                exc,
                {
                    'api_kind': api_kind,
                    'network': network,
                },
            )
        raise

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
            'get_address_balance.ok',
            {
                'api_kind': api_kind,
                'network': network,
            },
        )

    if _cache is not None and value >= 0:
        await _cache.set(cache_key, value, ttl_seconds=10)

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

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:balancemulti')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'account.get_balances.duration',
                    {'api_kind': api_kind, 'network': network, 'duration_ms': duration_ms},
                )

    response: Any = await (_retry.run(_do_request) if _retry is not None else _do_request())
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
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
) -> list[NormalTxDTO]:
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
    response: Any = await (
        _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
        if _retry is not None
        else http.get(url, params=signed_params, headers=headers)
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]  # type: ignore[list-item]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]  # type: ignore[list-item]
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
) -> list[InternalTxDTO]:
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
    response: Any = await (
        _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
        if _retry is not None
        else http.get(url, params=signed_params, headers=headers)
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]  # type: ignore[list-item]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]  # type: ignore[list-item]
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
) -> list[TokenTransferDTO]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    actions = {'erc20': 'tokentx', 'erc721': 'tokennfttx', 'erc1155': 'token1155tx'}
    params: dict[str, Any] = {
        'module': 'account',
        'action': actions.get(token_standard, 'tokentx'),
        'address': address,
        'contractaddress': contract_address,
        'startblock': start_block,
        'endblock': end_block,
        'sort': sort,
        'page': page,
        'offset': offset,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await (
        _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
        if _retry is not None
        else http.get(url, params=signed_params, headers=headers)
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]  # type: ignore[list-item]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]  # type: ignore[list-item]
    return []


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
) -> list[MinedBlockDTO]:
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
    response: Any = await (
        _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
        if _retry is not None
        else http.get(url, params=signed_params, headers=headers)
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]  # type: ignore[list-item]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]  # type: ignore[list-item]
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
) -> list[BeaconWithdrawalDTO]:
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
    response: Any = await (
        _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
        if _retry is not None
        else http.get(url, params=signed_params, headers=headers)
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]  # type: ignore[list-item]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]  # type: ignore[list-item]
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
    response: Any = await (
        _retry.run(lambda: http.get(url, params=signed_params, headers=headers))
        if _retry is not None
        else http.get(url, params=signed_params, headers=headers)
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str | int):
            return str(result)
    return str(response)
