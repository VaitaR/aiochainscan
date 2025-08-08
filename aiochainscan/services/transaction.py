from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any

from aiochainscan.domain.dto import TransactionDTO
from aiochainscan.domain.models import TxHash
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry


async def get_transaction_by_hash(
    *,
    txhash: TxHash,
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
    """Fetch transaction details by transaction hash via proxy endpoint."""

    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    cache_key = f'tx:{api_kind}:{network}:{txhash}'

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getTransactionByHash',
        'txhash': str(txhash),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)

    if _cache is not None:
        cached = await _cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:tx')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'transaction.get_by_hash.duration',
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
                'get_transaction_by_hash.error',
                exc,
                {
                    'api_kind': api_kind,
                    'network': network,
                },
            )
        raise

    out: dict[str, Any] = {}
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            out = result

    if _telemetry is not None:
        await _telemetry.record_event(
            'get_transaction_by_hash.ok',
            {
                'api_kind': api_kind,
                'network': network,
            },
        )

    if _cache is not None and out:
        await _cache.set(cache_key, out, ttl_seconds=10)

    return out


def normalize_transaction(raw: dict[str, Any]) -> TransactionDTO:
    """Normalize provider-shaped transaction into TransactionDTO."""

    def hex_to_int(h: str | None) -> int | None:
        if not h:
            return None
        try:
            return int(h, 16) if isinstance(h, str) and h.startswith('0x') else int(h)  # type: ignore[arg-type]
        except Exception:
            return None

    return {
        'tx_hash': raw.get('hash') or raw.get('tx_hash') or raw.get('txhash'),
        'block_number': hex_to_int(raw.get('blockNumber') or raw.get('block_number')),
        'from_address': raw.get('from'),
        'to_address': raw.get('to'),
        'value_wei': hex_to_int(raw.get('value')),
        'gas': hex_to_int(raw.get('gas')),
        'gas_price_wei': hex_to_int(raw.get('gasPrice')),
        'nonce': hex_to_int(raw.get('nonce')),
        'input': raw.get('input'),
    }
