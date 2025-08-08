from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any

from aiochainscan.domain.dto import GasOracleDTO
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry


async def get_gas_oracle(
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
    """Fetch gas oracle info (Etherscan-compatible).

    Returns a provider-specific mapping. No normalization is performed at this layer.
    """

    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'gastracker',
        'action': 'gasoracle',
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    cache_key = f'gas_oracle:{api_kind}:{network}'
    if _cache is not None:
        cached = await _cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:gas_oracle')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'gas.get_gas_oracle.duration',
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
                'gas.get_gas_oracle.error',
                exc,
                {'api_kind': api_kind, 'network': network},
            )
        raise

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            if _cache is not None:
                await _cache.set(cache_key, result, ttl_seconds=5)
            if _telemetry is not None:
                await _telemetry.record_event(
                    'gas.get_gas_oracle.ok',
                    {'api_kind': api_kind, 'network': network},
                )
            return result
    return {}


def normalize_gas_oracle(raw: dict[str, Any]) -> GasOracleDTO:
    """Normalize provider-shaped gas oracle payload to `GasOracleDTO`.

    Supports Etherscan-compatible fields: SafeGasPrice, ProposeGasPrice, FastGasPrice,
    suggestBaseFee, gasUsedRatio. Missing fields are omitted.
    """

    def gwei_to_wei(value: str | int | float | None) -> int | None:
        if value is None:
            return None
        try:
            v = float(value) if isinstance(value, str) else float(value)
            return int(v * 1_000_000_000)
        except Exception:
            return None

    dto: GasOracleDTO = {}
    # Etherscan-style keys
    safe = raw.get('SafeGasPrice')
    prop = raw.get('ProposeGasPrice')
    fast = raw.get('FastGasPrice')
    base = raw.get('suggestBaseFee')
    ratio = raw.get('gasUsedRatio')

    safe_wei = gwei_to_wei(safe)
    if safe_wei is not None:
        dto['safe_gas_price_wei'] = safe_wei

    prop_wei = gwei_to_wei(prop)
    if prop_wei is not None:
        dto['propose_gas_price_wei'] = prop_wei

    fast_wei = gwei_to_wei(fast)
    if fast_wei is not None:
        dto['fast_gas_price_wei'] = fast_wei

    base_wei = gwei_to_wei(base)
    if base_wei is not None:
        dto['suggest_base_fee_wei'] = base_wei

    if isinstance(ratio, str):
        # Etherscan often returns a comma-separated list of ratios; take the first numeric value
        try:
            first = ratio.split(',')[0]
            dto['gas_used_ratio'] = float(first)
        except Exception:
            pass
    elif isinstance(ratio, int | float):
        dto['gas_used_ratio'] = float(ratio)

    return dto
