from abc import ABC, abstractmethod
from typing import Any


class BaseModule(ABC):
    def __init__(self, client: Any) -> None:
        self._client: Any = client

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
