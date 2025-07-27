from abc import ABC, abstractmethod


class BaseModule(ABC):
    def __init__(self, client):
        self._client = client

    @property
    @abstractmethod
    def _module(self) -> str:
        """Returns API module name."""

    async def _get(self, headers=None, **params):
        headers = headers or {}
        return await self._client._http.get(
            params={**{'module': self._module}, **params}, headers=headers
        )

    async def _post(self, headers=None, **params):
        headers = headers or {}
        return await self._client._http.post(
            data={**{'module': self._module}, **params}, headers=headers
        )
