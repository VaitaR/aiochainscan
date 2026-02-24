from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import orjson

if TYPE_CHECKING:
    import aiohttp

from aiochainscan.ports.http_client import HttpClient

try:
    import aiohttp
except ImportError:
    raise ImportError(
        'aiohttp is required for AiohttpClient. Install with: pip install aiohttp'
    ) from None


class AiohttpClient(HttpClient):
    """HttpClient implementation backed by aiohttp."""

    def __init__(self, *, timeout: float | None = None) -> None:
        """Create aiohttp-based client.

        timeout: when None, do not enforce a client-level total timeout.
        """
        self._timeout: aiohttp.ClientTimeout | None
        if timeout is None:
            self._timeout = None
        else:
            self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            if self._timeout is None:
                self._session = aiohttp.ClientSession()
            else:
                self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def aclose(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        session = await self._ensure_session()
        async with session.get(
            url, params=dict(params or {}), headers=dict(headers or {})
        ) as resp:
            resp.raise_for_status()
            return await self._maybe_json(resp)

    async def post(
        self,
        url: str,
        *,
        data: Any | None = None,
        json: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        session = await self._ensure_session()
        async with session.post(url, data=data, json=json, headers=dict(headers or {})) as resp:
            resp.raise_for_status()
            return await self._maybe_json(resp)

    @staticmethod
    async def _maybe_json(resp: aiohttp.ClientResponse) -> Any:
        """Parse response as JSON if content type indicates JSON, else return text.

        Uses orjson for 3-5x faster parsing compared to stdlib json.
        This is critical for large API responses (megabytes of transactions)
        to avoid blocking the event loop.
        """
        ctype = resp.headers.get('Content-Type', '')
        if 'application/json' in ctype:
            # Use orjson for ultra-fast JSON parsing
            # Read raw bytes and parse with orjson instead of aiohttp's json()
            raw_bytes = await resp.read()
            return orjson.loads(raw_bytes)
        return await resp.text()
