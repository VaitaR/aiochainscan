from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient


def _to_tag(value: int | str) -> str:
    if isinstance(value, int):
        return hex(value)
    s = value.strip().lower()
    if s == 'latest' or s.startswith('0x'):
        return s
    if s.isdigit():
        return hex(int(s))
    # Fallback: pass-through (provider may error)
    return s


async def get_block_by_number(
    *,
    tag: int | str,
    full: bool,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient,
    _endpoint_builder: EndpointBuilder,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch block by number via proxy.eth_getBlockByNumber."""

    endpoint = _endpoint_builder.open(api_key=api_key, api_kind=api_kind, network=network)
    url: str = endpoint.api_url

    params: dict[str, Any] = {
        'module': 'proxy',
        'action': 'eth_getBlockByNumber',
        'boolean': str(full).lower(),
        'tag': _to_tag(tag),
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})

    signed_params, headers = endpoint.filter_and_sign(params, headers=None)
    response: Any = await http.get(url, params=signed_params, headers=headers)

    if isinstance(response, dict):
        result = response.get('result', response)
        if isinstance(result, dict):
            return result
    # Fallback to dict coercion if possible
    return dict(response) if isinstance(response, Mapping) else {'result': response}
