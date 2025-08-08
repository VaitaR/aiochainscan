from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.domain.models import TxHash
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.url_builder import UrlBuilder


async def get_transaction_by_hash(
    *,
    txhash: TxHash,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch transaction details by transaction hash via proxy endpoint."""

    builder = UrlBuilder(api_key=api_key, api_kind=api_kind, network=network)
    url: str = builder.API_URL

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getTransactionByHash',
        'txhash': str(txhash),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = builder.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            return result
    return {}
