from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.ports.endpoint_builder import EndpointBuilder, EndpointSession
from aiochainscan.url_builder import UrlBuilder


class _UrlSession(EndpointSession):
    def __init__(self, *, api_key: str, api_kind: str, network: str) -> None:
        self._builder = UrlBuilder(api_key=api_key, api_kind=api_kind, network=network)

    @property
    def api_url(self) -> str:
        return self._builder.API_URL

    @property
    def base_url(self) -> str:
        return self._builder.BASE_URL

    def filter_and_sign(
        self, params: Mapping[str, Any] | None, headers: Mapping[str, Any] | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._builder.filter_and_sign(dict(params or {}), dict(headers or {}))


class UrlBuilderEndpoint(EndpointBuilder):
    def open(self, *, api_key: str, api_kind: str, network: str) -> EndpointSession:
        return _UrlSession(api_key=api_key, api_kind=api_kind, network=network)
