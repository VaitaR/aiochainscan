from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any, TypedDict

from aiochainscan.domain.models import Address
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services.constants import (
    CACHE_TTL_TOKEN_BALANCE_SECONDS as CACHE_TTL_SECONDS_TOKEN_BALANCE,
)


async def get_token_balance(
    *,
    holder: Address | str,
    token_contract: Address | str,
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
    """Fetch ERC-20 token balance for a holder address.

    Uses the common Etherscan-compatible endpoint: module=account&action=tokenbalance.
    """

    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    cache_key = f'token_balance:{api_kind}:{network}:{holder}:{token_contract}'

    params: dict[str, Any] = {
        'module': 'account',
        'action': 'tokenbalance',
        'contractaddress': str(token_contract),
        'address': str(holder),
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
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:token_balance')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'token.get_balance.duration',
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
                'get_token_balance.error',
                exc,
                {
                    'api_kind': api_kind,
                    'network': network,
                },
            )
        raise

    value: int = 0
    if isinstance(response, dict):
        result = response.get('result', response)
        if (isinstance(result, str) and result.isdigit()) or isinstance(result, int | float):
            value = int(result)
    elif isinstance(response, str) and response.isdigit():
        value = int(response)
    else:
        try:
            value = int(response)  # best-effort coercion
        except Exception:
            value = 0

    if _telemetry is not None:
        await _telemetry.record_event(
            'token.get_token_balance.ok',
            {
                'api_kind': api_kind,
                'network': network,
            },
        )

    if _cache is not None and value >= 0:
        await _cache.set(cache_key, value, ttl_seconds=CACHE_TTL_SECONDS_TOKEN_BALANCE)

    return value


class TokenBalanceDTO(TypedDict):
    holder: str
    token_contract: str
    balance_wei: int


def normalize_token_balance(
    *, holder: Address, token_contract: Address, value: int
) -> TokenBalanceDTO:
    return {
        'holder': str(holder),
        'token_contract': str(token_contract),
        'balance_wei': int(value),
    }


# TTL constants (conservative defaults)
# centralized in constants module


async def get_token_total_supply(
    *,
    contract: Address | str,
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
    """Get ERC20-Token TotalSupply by ContractAddress."""
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'stats',
        'action': 'tokensupply',
        'contractaddress': str(contract),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        return str(result)
    return str(response)


async def get_token_total_supply_by_block(
    *,
    contract: Address | str,
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
) -> str:
    """Get Historical ERC20-Token TotalSupply by ContractAddress & BlockNo."""
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'stats',
        'action': 'tokensupplyhistory',
        'contractaddress': str(contract),
        'blockno': block_no,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        return str(result)
    return str(response)


async def get_token_balance_history(
    *,
    contract: Address | str,
    address: Address | str,
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
) -> str:
    """Get Historical ERC20-Token Account Balance by BlockNo."""
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'tokenbalancehistory',
        'contractaddress': str(contract),
        'address': str(address),
        'blockno': block_no,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        return str(result)
    return str(response)


async def get_token_holder_list(
    *,
    contract_address: Address | str,
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
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'token',
        'action': 'tokenholderlist',
        'contractaddress': str(contract_address),
        'page': page,
        'offset': offset,
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []


async def get_token_info(
    *,
    contract_address: Address | str | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'token',
        'action': 'tokeninfo',
        'contractaddress': None if contract_address is None else str(contract_address),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []


async def get_address_token_balance(
    *,
    address: Address | str,
    page: int | None,
    offset: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'addresstokenbalance',
        'address': str(address),
        'page': page,
        'offset': offset,
    }
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []


async def get_address_token_nft_balance(
    *,
    address: Address | str,
    page: int | None,
    offset: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'addresstokennftbalance',
        'address': str(address),
        'page': page,
        'offset': offset,
    }
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []


async def get_address_token_nft_inventory(
    *,
    address: Address | str,
    contract_address: Address | str,
    page: int | None,
    offset: int | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
) -> list[dict[str, Any]]:
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'addresstokennftinventory',
        'address': str(address),
        'contractaddress': str(contract_address),
        'page': page,
        'offset': offset,
    }
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []
