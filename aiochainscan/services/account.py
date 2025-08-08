from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.domain.models import Address
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient


async def get_address_balance(
    *,
    address: Address,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
) -> int:
    """Fetch address balance (wei) using the canonical HTTP port and legacy UrlBuilder.

    This is a thin use-case wrapper. It composes URL and delegates HTTP to the provided port.
    """

    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'account',
        'action': 'balance',
        'address': str(address),
        'tag': 'latest',
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)

    # Etherscan-like response: {"status": "1", "message": "OK", "result": "123..."}
    if isinstance(response, dict):
        result = response.get('result', response)
        # Some providers return numbers as strings
        if isinstance(result, str) and result.isdigit():
            return int(result)
        # Moralis or other providers might return nested structures; attempt to coerce
        if isinstance(result, int | float):
            return int(result)
    elif isinstance(response, str) and response.isdigit():
        return int(response)

    # Fallback: best-effort int conversion
    try:
        return int(response)  # best-effort coercion
    except Exception:
        return 0
