from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp

from aiochainscan.ports.http_client import HttpClient


class AiohttpClient(HttpClient):
    """HttpClient implementation backed by aiohttp."""

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
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
        ctype = resp.headers.get('Content-Type', '')
        if 'application/json' in ctype:
            return await resp.json()
        return await resp.text()
