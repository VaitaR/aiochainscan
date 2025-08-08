from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from time import monotonic
from typing import Any

from aiochainscan.domain.dto import DailySeriesDTO, EthPriceDTO
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry


async def get_eth_price(
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
) -> dict[str, Any]:
    """Fetch ETH price (raw provider shape).

    Returns a provider-shaped mapping with keys like 'ethusd', 'ethbtc', etc.
    """
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'stats',
        'action': 'ethprice',
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    cache_key = f'ethprice:{api_kind}:{network}'
    if _cache is not None:
        cached = await _cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:ethprice')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'stats.get_eth_price.duration',
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
                'get_eth_price.error',
                exc,
                {'api_kind': api_kind, 'network': network},
            )
        raise

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            if _cache is not None:
                await _cache.set(cache_key, result, ttl_seconds=30)
            if _telemetry is not None:
                await _telemetry.record_event(
                    'get_eth_price.ok',
                    {'api_kind': api_kind, 'network': network},
                )
            return result
    return {}


def normalize_eth_price(raw: dict[str, Any]) -> EthPriceDTO:
    """Normalize provider ETH price payload to EthPriceDTO."""

    def to_float(value: Any) -> float | None:
        try:
            return float(value)
        except Exception:
            return None

    def to_int(value: Any) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    return {
        'eth_usd': to_float(raw.get('ethusd')),
        'eth_btc': to_float(raw.get('ethbtc')),
        'eth_usd_timestamp': to_int(raw.get('ethusd_timestamp')),
        'eth_btc_timestamp': to_int(raw.get('ethbtc_timestamp')),
    }


async def _get_daily_series(
    *,
    action: str,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    """Fetch a daily time-series from stats endpoints (raw provider shape)."""
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
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
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:{action}')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    f'stats.{action}.duration',
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
                f'stats.{action}.error',
                exc,
                {'api_kind': api_kind, 'network': network},
            )
        raise

    # Providers may return either {"result": [...]} or just [...]
    if isinstance(response, dict):
        result = response.get('result', [])
        if isinstance(result, list):
            return result
        return []
    if isinstance(response, list):
        return response
    return []


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def normalize_daily_series(raw: list[dict[str, Any]], *, value_key: str) -> list[DailySeriesDTO]:
    """Normalize a provider daily-series payload to a simple DTO list.

    This helper accepts a specific value_key for the metric of interest since
    different stats actions expose different field names.
    """
    normalized: list[DailySeriesDTO] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                'utc_date': str(item.get('UTCDate')) if item.get('UTCDate') is not None else None,
                'unix_timestamp': _to_int(item.get('unixTimeStamp')),
                'value': _to_float(item.get(value_key)),
            }
        )
    return normalized


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
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailytx',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_new_address_count(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailynewaddress',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_network_tx_fee(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailytxnfee',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_network_utilization(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailynetutilization',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


# Additional daily series exposed via services
async def get_daily_average_block_size(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailyavgblocksize',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_block_rewards(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailyblockrewards',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_average_block_time(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailyavgblocktime',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_uncle_block_count(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailyuncleblkcount',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_average_gas_limit(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailyavggaslimit',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_total_gas_used(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailygasused',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_average_gas_price(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailyavggasprice',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
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
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailyblkcount',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_average_network_hash_rate(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailyavghashrate',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_daily_average_network_difficulty(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='dailyavgnetdifficulty',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_ether_historical_daily_market_cap(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='ethdailymarketcap',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )


async def get_ether_historical_price(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    sort: str | None = None,
    _rate_limiter: RateLimiter | None = None,
    _retry: RetryPolicy | None = None,
    _telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    return await _get_daily_series(
        action='ethdailyprice',
        start_date=start_date,
        end_date=end_date,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        _endpoint_builder=_endpoint_builder,
        sort=sort,
        _rate_limiter=_rate_limiter,
        _retry=_retry,
        _telemetry=_telemetry,
    )
