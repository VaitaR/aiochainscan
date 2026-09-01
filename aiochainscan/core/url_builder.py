from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from aiochainscan.chain_registry import (
    URL_BUILDER_CURRENCIES,
    get_url_builder_profile,
)


class UrlBuilder:
    # Kept for compatibility with tests and external introspection.
    _API_KINDS = {kind: ('', currency) for kind, currency in URL_BUILDER_CURRENCIES.items()}

    BASE_URL: str
    API_URL: str

    def __init__(
        self, api_key: str, api_kind: str, network: str, *, api_url: str | None = None
    ) -> None:
        """Initialize the URL builder.

        Args:
            api_key: API key used for request signing.
            api_kind: Registry api kind selecting the URL profile.
            network: Network name for the profile lookup.
            api_url: Custom API endpoint override (e.g. an Etherscan v2 proxy
                or self-hosted instance). When given, it replaces the
                profile's ``api_url`` and ``base_url``; the profile still
                supplies auth mode and currency. Expected to be pre-validated
                by :func:`aiochainscan.base_url.validate_base_url` — trailing
                slash is stripped defensively.
        """
        self._API_KEY = api_key

        self._api_kind = api_kind.lower().strip()
        self._network = network.lower().strip()

        profile = get_url_builder_profile(self._api_kind, self._network)
        self.BASE_URL = str(profile['base_url'])
        self.API_URL = str(profile['api_url'])
        if api_url is not None:
            normalized = api_url.rstrip('/')
            self.API_URL = normalized
            # Derive the frontend root from the override (scheme + host).
            parts = urlsplit(normalized)
            self.BASE_URL = urlunsplit((parts.scheme, parts.netloc, '', '', ''))
        self._auth_mode = str(profile['auth_mode'])
        self._currency = str(profile['currency'])
        chainid = profile.get('chainid')
        self._chainid = str(chainid) if isinstance(chainid, str) else None

    def _set_api_kind(self, api_kind: str) -> None:
        api_kind = api_kind.lower().strip()
        if api_kind not in self._API_KINDS:
            raise ValueError(
                f'Incorrect api_kind {api_kind!r}, supported only: {", ".join(self._API_KINDS)}'
            )
        else:
            self._api_kind = api_kind

    @property
    def currency(self) -> str:
        return self._currency

    def get_link(self, path: str) -> str:
        return urljoin(self.BASE_URL, path)

    def filter_and_sign(
        self, params: dict[str, Any] | None, headers: dict[str, Any] | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        filtered_params = self._filter_params(dict(params or {}))
        filtered_headers = self._filter_headers(dict(headers or {}))

        params_with_chain = self._apply_chain_id(filtered_params)
        signed_params, signed_headers = self._apply_auth(params_with_chain, filtered_headers)
        return signed_params, signed_headers

    @staticmethod
    def _filter_params(params: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in params.items() if v is not None}

    @staticmethod
    def _filter_headers(headers: dict[str, Any]) -> dict[str, str]:
        return {str(k): str(v) for k, v in headers.items() if v is not None}

    def _apply_chain_id(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._chainid is not None:
            params.setdefault('chainid', self._chainid)
        return params

    def _apply_auth(
        self, params: dict[str, Any], headers: dict[str, str]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        if not self._API_KEY:
            return params, headers

        if self._auth_mode == 'header':
            headers.setdefault('X-API-Key', self._API_KEY)
        else:
            params.setdefault('apikey', self._API_KEY)

        return params, headers
