from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.domain.models import Address
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient


async def get_token_balance(
    *,
    holder: Address,
    token_contract: Address,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
) -> int:
    """Fetch ERC-20 token balance for a holder address.

    Uses the common Etherscan-compatible endpoint: module=account&action=tokenbalance.
    """

    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url

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
    response: Any = await http.get(url, params=signed_params, headers=headers)

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, str) and result.isdigit():
            return int(result)
        if isinstance(result, int | float):
            return int(result)
    elif isinstance(response, str) and response.isdigit():
        return int(response)

    try:
        return int(response)  # best-effort coercion
    except Exception:
        return 0
