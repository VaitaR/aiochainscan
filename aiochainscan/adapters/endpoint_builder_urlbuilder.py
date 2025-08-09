from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.ports.endpoint_builder import EndpointBuilder, EndpointSession
from aiochainscan.url_builder import UrlBuilder


class _UrlSession(EndpointSession):
    def __init__(self, *, api_key: str, api_kind: str, network: str) -> None:
        self._builder = UrlBuilder(api_key=api_key, api_kind=api_kind, network=network)
        self._api_key: str = api_key
        self._api_kind: str = api_kind

    @property
    def api_url(self) -> str:
        return self._builder.API_URL

    @property
    def base_url(self) -> str:
        return self._builder.BASE_URL

    def filter_and_sign(
        self, params: Mapping[str, Any] | None, headers: Mapping[str, Any] | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # Header-based auth for specific providers (e.g., Moralis)
        if self._api_kind == 'moralis':
            # Do not append apikey to query params; add X-API-Key header instead
            filtered_params: dict[str, Any] = self._builder._filter_params(dict(params or {}))
            out_headers: dict[str, str] = {
                str(k): str(v) for k, v in dict(headers or {}).items() if v is not None
            }
            if self._api_key:
                out_headers['X-API-Key'] = self._api_key
            return filtered_params, out_headers

        # Default Etherscan-style: query param apikey
        signed_params, signed_headers = self._builder.filter_and_sign(
            dict(params or {}), dict(headers or {})
        )
        # Ensure header value types are strings
        typed_headers: dict[str, str] = {
            str(k): str(v) for k, v in signed_headers.items() if v is not None
        }
        return signed_params, typed_headers


class UrlBuilderEndpoint(EndpointBuilder):
    def open(self, *, api_key: str, api_kind: str, network: str) -> EndpointSession:
        return _UrlSession(api_key=api_key, api_kind=api_kind, network=network)
