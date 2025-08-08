import os
import warnings
from abc import ABC, abstractmethod
from typing import Any


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
