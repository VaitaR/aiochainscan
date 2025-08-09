from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.domain.dto import TransactionDTO
from aiochainscan.domain.models import TxHash
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services._executor import run_with_policies

CACHE_TTL_SECONDS: int = 10


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

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='transaction.get_transaction_by_hash',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:tx',
        retry_policy=_retry,
    )

    out: dict[str, Any] = {}
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            out = result

    if _telemetry is not None:
        await _telemetry.record_event(
            'transaction.get_transaction_by_hash.ok',
            {
                'api_kind': api_kind,
                'network': network,
            },
        )

    if _cache is not None and out:
        await _cache.set(cache_key, out, ttl_seconds=CACHE_TTL_SECONDS)

    return out


def normalize_transaction(raw: dict[str, Any]) -> TransactionDTO:
    """Normalize provider-shaped transaction into TransactionDTO."""

    def hex_to_int(h: str | None) -> int | None:
        if not h:
            return None
        try:
            return int(h, 16) if isinstance(h, str) and h.startswith('0x') else int(h)
        except Exception:
            return None

    tx_hash_value = raw.get('hash') or raw.get('tx_hash') or raw.get('txhash')
    return {
        'tx_hash': str(tx_hash_value) if tx_hash_value is not None else '',
        'block_number': hex_to_int(raw.get('blockNumber') or raw.get('block_number')),
        'from_address': raw.get('from'),
        'to_address': raw.get('to'),
        'value_wei': hex_to_int(raw.get('value')),
        'gas': hex_to_int(raw.get('gas')),
        'gas_price_wei': hex_to_int(raw.get('gasPrice')),
        'nonce': hex_to_int(raw.get('nonce')),
        'input': raw.get('input'),
    }


async def get_tx_receipt_status(
    *,
    txhash: TxHash,
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
    """[BETA] Check Transaction Receipt Status (post-Byzantium)."""
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'transaction',
        'action': 'gettxreceiptstatus',
        'txhash': str(txhash),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='transaction.get_tx_receipt_status',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:gettxreceiptstatus',
        retry_policy=_retry,
    )
    return response if isinstance(response, dict) else {'result': response}


async def get_contract_execution_status(
    *,
    txhash: TxHash,
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
    """[BETA] Check Contract Execution Status (provider-shaped)."""
    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url
    params: dict[str, Any] = {
        'module': 'transaction',
        'action': 'getstatus',
        'txhash': str(txhash),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='transaction.get_contract_execution_status',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:getstatus',
        retry_policy=_retry,
    )
    return response if isinstance(response, dict) else {'result': response}
