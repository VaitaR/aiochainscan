from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from time import monotonic
from typing import Any

from aiochainscan.core.context import ProviderContext
from aiochainscan.domain.dto_v2 import DailySeriesDTO, EthPriceDTO, parse_hex_or_int
from aiochainscan.services._executor import run_with_policies
from aiochainscan.services.constants import CACHE_TTL_ETH_PRICE_SECONDS


async def get_eth_price(
    *,
    ctx: ProviderContext,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch ETH price (raw provider shape).

    Returns a provider-shaped mapping with keys like 'ethusd', 'ethbtc', etc.
    """
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'stats',
        'action': 'ethprice',
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    # Preserve explicit None for sort in tests: keep the key present
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    cache_key = f'ethprice:{ctx.api_kind}:{ctx.network}'
    if ctx.cache is not None:
        cached = await ctx.cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='stats.get_eth_price',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:ethprice',
        retry_policy=ctx.retry,
    )

    result: Any = response
    if isinstance(response, dict):
        result = response.get('result', response)
    if isinstance(result, dict):
        if ctx.cache is not None:
            await ctx.cache.set(cache_key, result, ttl_seconds=CACHE_TTL_ETH_PRICE_SECONDS)
        if ctx.telemetry is not None:
            await ctx.telemetry.record_event(
                'stats.get_eth_price.ok',
                {'api_kind': ctx.api_kind, 'network': ctx.network},
            )
        return result
    return {}


async def get_eth_supply(
    *,
    ctx: ProviderContext,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    """Get Total Supply of Ether (ethsupply)."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {'module': 'stats', 'action': 'ethsupply'}
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='stats.ethsupply',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:ethsupply',
        retry_policy=ctx.retry,
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        return str(result)
    return str(response)


async def get_eth2_supply(
    *,
    ctx: ProviderContext,
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    """Get Total Supply of Ether (ethsupply2)."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {'module': 'stats', 'action': 'ethsupply2'}
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='stats.ethsupply2',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:ethsupply2',
        retry_policy=ctx.retry,
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        return str(result)
    return str(response)


async def get_total_nodes_count(
    *,
    ctx: ProviderContext,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Get Total Nodes Count (nodecount)."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {'module': 'stats', 'action': 'nodecount'}
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='stats.nodecount',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:nodecount',
        retry_policy=ctx.retry,
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        return result if isinstance(result, dict) else response
    return {'result': response}


async def get_chain_size(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    client_type: str,
    sync_mode: str,
    sort: str | None = None,
) -> dict[str, Any] | None:
    """Get chain size (provider-shaped). Returns None when provider returns empty list."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'stats',
        'action': 'chainsize',
        'startdate': start_date.isoformat(),
        'enddate': end_date.isoformat(),
        'clienttype': client_type,
        'syncmode': sync_mode,
        'sort': sort,
    }
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    response: Any = await run_with_policies(
        do_call=lambda: ctx.http.get(url, params=signed_params, headers=headers),
        telemetry=ctx.telemetry,
        telemetry_name='stats.chainsize',
        api_kind=ctx.api_kind,
        network=ctx.network,
        rate_limiter=ctx.rate_limiter,
        rate_limiter_key=f'{ctx.api_kind}:{ctx.network}:chainsize',
        retry_policy=ctx.retry,
    )

    if isinstance(response, list) and len(response) == 0:
        return None
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list) and len(result) == 0:
            return None
        return result if isinstance(result, dict) else response
    return {'result': response}


def normalize_eth_price(raw: dict[str, Any]) -> EthPriceDTO:
    """Normalize provider ETH price payload to EthPriceDTO."""
    return EthPriceDTO.model_validate(raw)


async def _get_daily_series(
    *,
    ctx: ProviderContext,
    action: str,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch a daily time-series from stats endpoints (raw provider shape)."""
    endpoint = ctx.endpoint_builder.open(
        api_key=ctx.api_key, api_kind=ctx.api_kind, network=ctx.network
    )
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'stats',
        'action': action,
        'startdate': start_date.isoformat(),
        'enddate': end_date.isoformat(),
        'sort': sort,
    }
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    async def _do_request() -> Any:
        if ctx.rate_limiter is not None:
            await ctx.rate_limiter.acquire(key=f'{ctx.api_kind}:{ctx.network}:{action}')
        start = monotonic()
        try:
            return await ctx.http.get(url, params=signed_params, headers=headers)
        finally:
            if ctx.telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await ctx.telemetry.record_event(
                    f'stats.{action}.duration',
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
                f'stats.{action}.error',
                exc,
                {'api_kind': ctx.api_kind, 'network': ctx.network},
            )
        raise

    # Providers may return either {"result": [...]} or just [...]
    items: list[dict[str, Any]] = []
    if isinstance(response, dict):
        result = response.get('result', [])
        if isinstance(result, list):
            items = result
    elif isinstance(response, list):
        items = response

    if ctx.telemetry is not None:
        await ctx.telemetry.record_event(
            f'stats.{action}.ok',
            {'api_kind': ctx.api_kind, 'network': ctx.network, 'items': len(items)},
        )

    return items if isinstance(items, list) else []


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def normalize_daily_series(raw: list[dict[str, Any]], *, value_key: str) -> list[DailySeriesDTO]:
    """Normalize a provider daily-series payload to DailySeriesDTO list.

    The value_key parameter selects which provider-specific field contains the metric
    (e.g. 'transactionCount', 'newAddressCount'). This can't be a static Pydantic
    alias since it varies per endpoint, so we pre-process manually.
    """
    result: list[DailySeriesDTO] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        utc = item.get('UTCDate')
        ts_raw = item.get('unixTimeStamp')
        val_raw = item.get(value_key)
        result.append(
            DailySeriesDTO(
                utc_date=str(utc) if utc is not None else None,
                unix_timestamp=parse_hex_or_int(ts_raw),
                value=_to_float(val_raw),
            )
        )
    return result


# Convenience specific normalizers (value_key bound)
def normalize_daily_transaction_count(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    return normalize_daily_series(raw, value_key='transactionCount')


def normalize_daily_new_address_count(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    return normalize_daily_series(raw, value_key='newAddressCount')


def normalize_daily_network_tx_fee(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    # Common providers expose ETH-denominated fee; fallback to generic key if differs
    for candidate in ('transactionFeeEth', 'txnFee', 'txFee'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='transactionFeeEth')


def normalize_daily_network_utilization(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('utilization', 'networkUtilization'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='utilization')


# Public service functions for high-traffic series
async def get_daily_transaction_count(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailytx',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_new_address_count(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailynewaddress',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_network_tx_fee(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailytxnfee',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_network_utilization(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailynetutilization',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


# Additional daily series exposed via services
async def get_daily_average_block_size(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailyavgblocksize',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_block_rewards(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailyblockrewards',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_average_block_time(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailyavgblocktime',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_uncle_block_count(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailyuncleblkcount',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_average_gas_limit(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailyavggaslimit',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_total_gas_used(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailygasused',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_average_gas_price(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailyavggasprice',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


# Normalizers for additional daily series
def normalize_daily_average_block_size(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('avgBlockSize', 'averageBlockSize', 'blockSizeBytes'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='avgBlockSize')


def normalize_daily_block_rewards(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('blockRewards_Eth', 'blockRewards', 'rewards'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='blockRewards_Eth')


def normalize_daily_average_block_time(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('avgBlockTime', 'blockTimeSeconds'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='avgBlockTime')


def normalize_daily_uncle_block_count(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('uncleBlockCount', 'uncleBlocks'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='uncleBlockCount')


def normalize_daily_average_gas_limit(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('avgGasLimit', 'averageGasLimit'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='avgGasLimit')


def normalize_daily_total_gas_used(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('gasUsed', 'totalGasUsed'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='gasUsed')


def normalize_daily_average_gas_price(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('avgGasPrice', 'averageGasPrice', 'avgGasPrice_Wei'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='avgGasPrice')


def normalize_daily_block_count(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('blockCount', 'blocks', 'dailyBlockCount'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='blockCount')


def normalize_daily_average_network_hash_rate(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in (
        'dailyAvgHashRate',
        'avgHashRate',
        'hashRate',
        'networkHashRate',
    ):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='dailyAvgHashRate')


def normalize_daily_average_network_difficulty(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in (
        'dailyAvgNetDifficulty',
        'avgDifficulty',
        'difficulty',
        'networkDifficulty',
    ):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='dailyAvgNetDifficulty')


def normalize_ether_historical_daily_market_cap(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('marketCap', 'marketcapUSD', 'marketCapUsd'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='marketCap')


def normalize_ether_historical_price(raw: list[dict[str, Any]]) -> list[DailySeriesDTO]:
    for candidate in ('value', 'price', 'priceUSD', 'priceUsd'):
        if raw and isinstance(raw[0], dict) and candidate in raw[0]:
            return normalize_daily_series(raw, value_key=candidate)
    return normalize_daily_series(raw, value_key='value')


async def get_daily_block_count(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailyblkcount',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_average_network_hash_rate(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailyavghashrate',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_daily_average_network_difficulty(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='dailyavgnetdifficulty',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_ether_historical_daily_market_cap(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='ethdailymarketcap',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )


async def get_ether_historical_price(
    *,
    ctx: ProviderContext,
    start_date: date,
    end_date: date,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        ctx=ctx,
        action='ethdailyprice',
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )
