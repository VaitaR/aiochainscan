from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient


async def get_gas_oracle(
    *,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
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
    response: Any = await http.get(url, params=signed_params, headers=headers)

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            return result
    return {}
