from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any, TypedDict

from aiochainscan.core.context import ProviderContext
from aiochainscan.domain.models import Address
from aiochainscan.services.constants import (
    CACHE_TTL_TOKEN_BALANCE_SECONDS as CACHE_TTL_SECONDS_TOKEN_BALANCE,
)


async def get_token_balance(
    *,
    ctx: ProviderContext,
    holder: Address,
    token_contract: Address,
    extra_params: Mapping[str, Any] | None = None,
) -> int:
    """Fetch ERC-20 token balance for a holder address.

    Uses the common Etherscan-compatible endpoint: module=account&action=tokenbalance.
    """

    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    cache_key = f'token_balance:{ctx.api_kind}:{ctx.network}:{holder}:{token_contract}'

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
    if ctx.cache is not None:
        cached = await ctx.cache.get(cache_key)
        if isinstance(cached, int):
            return cached

    async def _do_request() -> Any:
        if ctx.rate_limiter is not None:
            await ctx.rate_limiter.acquire(key=f'{ctx.api_kind}:{ctx.network}:token_balance')
        start = monotonic()
        try:
            return await ctx.http.get(url, params=signed_params, headers=headers)
        finally:
            if ctx.telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await ctx.telemetry.record_event(
                    'token.get_balance.duration',
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
                'get_token_balance.error',
                exc,
                {
                    'api_kind': ctx.api_kind,
                    'network': ctx.network,
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
        except (ValueError, TypeError):
            value = 0

    if ctx.telemetry is not None:
        await ctx.telemetry.record_event(
            'token.get_token_balance.ok',
            {
                'api_kind': ctx.api_kind,
                'network': ctx.network,
            },
        )

    if ctx.cache is not None and value >= 0:
        await ctx.cache.set(cache_key, value, ttl_seconds=CACHE_TTL_SECONDS_TOKEN_BALANCE)

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
    ctx: ProviderContext,
    contract: Address,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    """Get ERC20-Token TotalSupply by ContractAddress."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'stats',
        'action': 'tokensupply',
        'contractaddress': str(contract),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await ctx.http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        return str(result)
    return str(response)


async def get_token_total_supply_by_block(
    *,
    ctx: ProviderContext,
    contract: Address,
    block_no: int,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    """Get Historical ERC20-Token TotalSupply by ContractAddress & BlockNo."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
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
    response: Any = await ctx.http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        return str(result)
    return str(response)


async def get_token_balance_history(
    *,
    ctx: ProviderContext,
    contract: Address,
    address: Address,
    block_no: int,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    """Get Historical ERC20-Token Account Balance by BlockNo."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
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
    response: Any = await ctx.http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        return str(result)
    return str(response)


async def get_token_holder_list(
    *,
    ctx: ProviderContext,
    contract_address: Address,
    page: int | None,
    offset: int | None,
    extra_params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
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
    response: Any = await ctx.http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []


async def get_token_info(
    *,
    ctx: ProviderContext,
    contract_address: Address | None,
    extra_params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'token',
        'action': 'tokeninfo',
        'contractaddress': None if contract_address is None else str(contract_address),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await ctx.http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []


async def get_address_token_balance(
    *,
    ctx: ProviderContext,
    address: Address,
    page: int | None,
    offset: int | None,
) -> list[dict[str, Any]]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'addresstokenbalance',
        'address': str(address),
        'page': page,
        'offset': offset,
    }
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await ctx.http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []


async def get_address_token_nft_balance(
    *,
    ctx: ProviderContext,
    address: Address,
    page: int | None,
    offset: int | None,
) -> list[dict[str, Any]]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'account',
        'action': 'addresstokennftbalance',
        'address': str(address),
        'page': page,
        'offset': offset,
    }
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await ctx.http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []


async def get_address_token_nft_inventory(
    *,
    ctx: ProviderContext,
    address: Address,
    contract_address: Address,
    page: int | None,
    offset: int | None,
) -> list[dict[str, Any]]:
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
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
    response: Any = await ctx.http.get(url, params=signed_params, headers=headers)
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []
