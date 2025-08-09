from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from typing import Any

from aiochainscan.domain.dto import (
    AddressBalanceDTO,
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
from aiochainscan.services._executor import run_with_policies

CACHE_TTL_SECONDS_BALANCE: int = 10


async def get_address_balance(
    *,
    address: Address | str,
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

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_address_balance',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:balance',
        retry_policy=_retry,
    )

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
            'account.get_address_balance.ok',
            {
                'api_kind': api_kind,
                'network': network,
            },
        )

    if _cache is not None and value >= 0:
        await _cache.set(cache_key, value, ttl_seconds=CACHE_TTL_SECONDS_BALANCE)

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

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_address_balances',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:balancemulti',
        retry_policy=_retry,
    )
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_address_balances.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_address_balances.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
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
) -> list[dict[str, Any]]:
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

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_normal_transactions',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:txlist',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_normal_transactions.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_normal_transactions.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
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
) -> list[dict[str, Any]]:
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

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_internal_transactions',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:txlistinternal',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_internal_transactions.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_internal_transactions.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
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
) -> list[dict[str, Any]]:
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

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_token_transfers',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:{params["action"]}',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_token_transfers.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_token_transfers.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
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
) -> list[dict[str, Any]]:
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

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_mined_blocks',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:getminedblocks',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_mined_blocks.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_mined_blocks.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
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
) -> list[dict[str, Any]]:
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

    response: Any = await run_with_policies(
        do_call=lambda: http.get(url, params=signed_params, headers=headers),
        telemetry=_telemetry,
        telemetry_name='account.get_beacon_chain_withdrawals',
        api_kind=api_kind,
        network=network,
        rate_limiter=_rate_limiter,
        rate_limiter_key=f'{api_kind}:{network}:txsBeaconWithdrawal',
        retry_policy=_retry,
    )

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, list):
            out = [r for r in result if isinstance(r, dict)]
            if _telemetry is not None:
                await _telemetry.record_event(
                    'account.get_beacon_chain_withdrawals.ok',
                    {'api_kind': api_kind, 'network': network, 'items': len(out)},
                )
            return out
    if isinstance(response, list):
        out = [r for r in response if isinstance(r, dict)]
        if _telemetry is not None:
            await _telemetry.record_event(
                'account.get_beacon_chain_withdrawals.ok',
                {'api_kind': api_kind, 'network': network, 'items': len(out)},
            )
        return out
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

    async def _do_request() -> Any:
        if _rate_limiter is not None:
            await _rate_limiter.acquire(key=f'{api_kind}:{network}:balancehistory')
        start = monotonic()
        try:
            return await http.get(url, params=signed_params, headers=headers)
        finally:
            if _telemetry is not None:
                duration_ms = int((monotonic() - start) * 1000)
                await _telemetry.record_event(
                    'account.get_account_balance_by_blockno.duration',
                    {'api_kind': api_kind, 'network': network, 'duration_ms': duration_ms},
                )

    response: Any = await (_retry.run(_do_request) if _retry is not None else _do_request())
    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str | int):
            return str(result)
    return str(response)


# --- Normalizers for account list endpoints (pure helpers) ---


def _to_str(value: Any) -> str | None:
    try:
        if value is None:
            return None
        return str(value)
    except Exception:
        return None


def normalize_normal_txs(items: list[dict[str, Any]]) -> list[NormalTxDTO]:
    normalized: list[NormalTxDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'blockNumber': _to_str(it.get('blockNumber')),
                'timeStamp': _to_str(it.get('timeStamp')),
                'hash': _to_str(it.get('hash')),
                'nonce': _to_str(it.get('nonce')),
                'blockHash': _to_str(it.get('blockHash')),
                'transactionIndex': _to_str(it.get('transactionIndex')),
                'from_': _to_str(it.get('from') or it.get('from_')),
                'to': _to_str(it.get('to')),
                'value': _to_str(it.get('value')),
                'gas': _to_str(it.get('gas')),
                'gasPrice': _to_str(it.get('gasPrice')),
                'isError': _to_str(it.get('isError')),
                'txreceipt_status': _to_str(it.get('txreceipt_status')),
                'input': _to_str(it.get('input')),
                'contractAddress': _to_str(it.get('contractAddress')),
                'cumulativeGasUsed': _to_str(it.get('cumulativeGasUsed')),
                'gasUsed': _to_str(it.get('gasUsed')),
                'confirmations': _to_str(it.get('confirmations')),
            }
        )
    return normalized


def normalize_internal_txs(items: list[dict[str, Any]]) -> list[InternalTxDTO]:
    normalized: list[InternalTxDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'blockNumber': _to_str(it.get('blockNumber')),
                'timeStamp': _to_str(it.get('timeStamp')),
                'hash': _to_str(it.get('hash')),
                'from_': _to_str(it.get('from') or it.get('from_')),
                'to': _to_str(it.get('to')),
                'value': _to_str(it.get('value')),
                'contractAddress': _to_str(it.get('contractAddress')),
                'input': _to_str(it.get('input')),
                'type': _to_str(it.get('type')),
                'gas': _to_str(it.get('gas')),
                'gasUsed': _to_str(it.get('gasUsed')),
                'traceId': _to_str(it.get('traceId')),
                'isError': _to_str(it.get('isError')),
                'errCode': _to_str(it.get('errCode')),
            }
        )
    return normalized


def normalize_token_transfers(items: list[dict[str, Any]]) -> list[TokenTransferDTO]:
    normalized: list[TokenTransferDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'blockNumber': _to_str(it.get('blockNumber')),
                'timeStamp': _to_str(it.get('timeStamp')),
                'hash': _to_str(it.get('hash')),
                'nonce': _to_str(it.get('nonce')),
                'blockHash': _to_str(it.get('blockHash')),
                'from_': _to_str(it.get('from') or it.get('from_')),
                'contractAddress': _to_str(it.get('contractAddress')),
                'to': _to_str(it.get('to')),
                'value': _to_str(it.get('value')),
                'tokenName': _to_str(it.get('tokenName')),
                'tokenSymbol': _to_str(it.get('tokenSymbol')),
                'tokenDecimal': _to_str(it.get('tokenDecimal')),
                'transactionIndex': _to_str(it.get('transactionIndex')),
                'gas': _to_str(it.get('gas')),
                'gasPrice': _to_str(it.get('gasPrice')),
                'gasUsed': _to_str(it.get('gasUsed')),
                'cumulativeGasUsed': _to_str(it.get('cumulativeGasUsed')),
                'input': _to_str(it.get('input')),
                'confirmations': _to_str(it.get('confirmations')),
            }
        )
    return normalized


def normalize_mined_blocks(items: list[dict[str, Any]]) -> list[MinedBlockDTO]:
    normalized: list[MinedBlockDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'blockNumber': _to_str(it.get('blockNumber')),
                'timeStamp': _to_str(it.get('timeStamp')),
                'blockReward': _to_str(it.get('blockReward')),
            }
        )
    return normalized


def normalize_beacon_withdrawals(items: list[dict[str, Any]]) -> list[BeaconWithdrawalDTO]:
    normalized: list[BeaconWithdrawalDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'blockNumber': _to_str(it.get('blockNumber')),
                'timeStamp': _to_str(it.get('timeStamp')),
                'address': _to_str(it.get('address')),
                'amount': _to_str(it.get('amount')),
            }
        )
    return normalized


def normalize_address_balances(items: list[dict[str, Any]]) -> list[AddressBalanceDTO]:
    """Normalize multi-balance response items into `AddressBalanceDTO` list.

    Providers usually return entries like {'account': '0x..', 'balance': '123'}.
    This helper coerces balance to int when possible and renames fields.
    """

    def to_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except Exception:
            return None

    normalized: list[AddressBalanceDTO] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized.append(
            {
                'address': _to_str(it.get('account') or it.get('address')),
                'balance_wei': to_int(it.get('balance')),
            }
        )
    return normalized
