from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp

from aiochainscan.exceptions import ChainscanClientError
from aiochainscan.ports.graphql_client import GraphQLClient


class AiohttpGraphQLClient(GraphQLClient):
    """GraphQL client backed by aiohttp."""

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

    async def execute(
        self,
        url: str,
        query: str,
        variables: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        session = await self._ensure_session()
        payload = {'query': query, 'variables': dict(variables or {})}
        async with session.post(url, json=payload, headers=dict(headers or {})) as resp:
            resp.raise_for_status()
            data = await resp.json()
        if not isinstance(data, dict):
            raise ChainscanClientError('Invalid GraphQL response: not a JSON object')
        if 'errors' in data and data['errors']:
            # Raise a succinct error preserving provider context
            first = data['errors'][0]
            message = first.get('message') if isinstance(first, dict) else str(first)
            raise ChainscanClientError(f'GraphQL error: {message}')
        return data.get('data')
