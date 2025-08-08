import os
import warnings
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient


class BaseModule(ABC):
    def __init__(self, client: Any) -> None:
        self._client: Any = client
        # Optional deprecation warning (off by default)
        if os.getenv('AIOCHAINSCAN_DEPRECATE_MODULES', '').strip().lower() in {'1', 'true', 'yes'}:
            warnings.warn(
                f'{self.__class__.__name__} is deprecated and will be removed in a future major version. '
                'Prefer using facade functions from aiochainscan directly.',
                DeprecationWarning,
                stacklevel=2,
            )

    @property
    @abstractmethod
    def _module(self) -> str:
        """Returns API module name."""

    async def _get(self, headers: dict[str, Any] | None = None, **params: Any) -> Any:
        headers = headers or {}
        return await self._client._http.get(
            params={**{'module': self._module}, **params}, headers=headers
        )

    async def _post(self, headers: dict[str, Any] | None = None, **params: Any) -> Any:
        headers = headers or {}
        return await self._client._http.post(
            data={**{'module': self._module}, **params}, headers=headers
        )


def _should_force_facades() -> bool:
    """Whether module methods should force facade usage without fallback."""
    return os.getenv('AIOCHAINSCAN_FORCE_FACADES', '').strip().lower() in {'1', 'true', 'yes'}


class _FacadeHttpFromNetwork:
    """Light HttpClient adapter that delegates to legacy Network for tests/mocks.

    It ignores the URL since legacy Network builds it internally. This allows
    existing tests that patch `aiochainscan.network.Network.get/post` to keep working
    even when modules route through facades.
    """

    def __init__(self, network: Any) -> None:
        self._network = network

    async def get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        return await self._network.get(params=dict(params or {}), headers=dict(headers or {}))

    async def post(
        self,
        url: str,
        *,
        data: Any | None = None,
        json: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        # Prefer form-encoded data path to match tests
        payload: Any = data if data is not None else json
        return await self._network.post(data=payload, headers=dict(headers or {}))

    async def aclose(self) -> None:  # Facade expects this method
        return None


class _PassthroughEndpoint:
    """EndpointBuilder stub that returns params/headers unchanged.

    This prevents double-signing (e.g., apikey duplication) and keeps tests
    asserting exact params stable.
    """

    def open(self, *, api_key: str, api_kind: str, network: str) -> '_PassthroughEndpoint':
        return self

    @property
    def api_url(self) -> str:  # not used by the delegating http adapter
        return ''

    @property
    def base_url(self) -> str:  # not used by the delegating http adapter
        return ''

    def filter_and_sign(
        self, params: Mapping[str, Any] | None, headers: Mapping[str, Any] | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # Preserve None values to match tests that assert presence of keys with None
        return dict(params or {}), dict(headers or {})


def _facade_injection(client: Any) -> tuple[HttpClient, EndpointBuilder]:
    """Return http/endpoint_builder suitable for passing into facades.

    - http: delegates to legacy Network, preserving test mocks
    - endpoint_builder: passthrough signing to keep params untouched
    """
    return _FacadeHttpFromNetwork(client._http), _PassthroughEndpoint()


def _resolve_api_context(client: Any) -> tuple[str, str, str]:
    """Resolve (api_kind, network, api_key) from legacy client compatibly.

    Falls back to private attributes of UrlBuilder to preserve behavior in tests.
    """

    def _as_str(value: Any) -> str:
        return '' if value is None else str(value)

    api_kind_any: Any = getattr(client, 'api_kind', None) or getattr(
        getattr(client, '_url_builder', object()), '_api_kind', None
    )
    network_any: Any = getattr(client, 'network', None) or getattr(
        getattr(client, '_url_builder', object()), '_network', None
    )
    api_key_any: Any = getattr(client, 'api_key', None) or getattr(
        getattr(client, '_url_builder', object()), '_API_KEY', None
    )
    api_kind: str = _as_str(api_kind_any)
    network: str = _as_str(network_any)
    api_key: str = _as_str(api_key_any)
    return api_kind, network, api_key
