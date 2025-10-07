from __future__ import annotations

import asyncio
import logging
from asyncio import AbstractEventLoop
from contextlib import AbstractAsyncContextManager
from typing import Any, Awaitable, Callable, cast

import aiohttp
from aiohttp import ClientTimeout
from aiohttp.client import ClientSession
from aiohttp.hdrs import METH_GET, METH_POST
from aiohttp_retry import RetryClient, RetryOptionsBase
from asyncio_throttle import Throttler  # type: ignore[attr-defined]

from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientError,
    ChainscanClientProxyError,
)
from aiochainscan.url_builder import UrlBuilder


async def _maybe_await(candidate: Any | Callable[[], Any]) -> Any:
    """Return awaited result when the candidate is awaitable/callable."""

    value = candidate() if callable(candidate) else candidate
    if asyncio.iscoroutine(value) or asyncio.isfuture(value):
        return await cast(Awaitable[Any], value)
    return value


class Network:
    def __init__(
        self,
        url_builder: UrlBuilder,
        loop: AbstractEventLoop | None = None,
        timeout: float | ClientTimeout | None = 10,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager[Any] | None = None,
        retry_options: RetryOptionsBase | None = None,
    ) -> None:
        self._url_builder = url_builder
        # Store the loop hint supplied by the caller. When ``None`` we will bind lazily on the
        # first awaited request in order to avoid capturing an inactive placeholder loop created
        # by ``asyncio.get_event_loop`` when no loop is running yet.
        self._loop: AbstractEventLoop | None = loop
        # Track which loop the retry client is currently bound to so we can rebuild it if calls
        # arrive from a different running loop (e.g. when using ``asyncio.run`` from multiple
        # threads during tests).
        self._bound_loop: AbstractEventLoop | None = None
        self._timeout = self._prepare_timeout(timeout)
        self._proxy = proxy
        self._throttler: AbstractAsyncContextManager[Any] = throttler or Throttler(
            rate_limit=5, period=1.0
        )
        self._retry_client: RetryClient | None = None
        self._retry_options = retry_options
        self._logger = logging.getLogger(__name__)

    def _prepare_timeout(self, timeout: float | ClientTimeout | None) -> ClientTimeout:
        if isinstance(timeout, ClientTimeout):
            return timeout
        elif isinstance(timeout, (int, float)):
            return ClientTimeout(total=float(timeout))
        else:
            return ClientTimeout(total=10)  # Default timeout

    async def close(self) -> None:
        if self._retry_client is not None:
            await self._retry_client.close()
            self._retry_client = None
        self._bound_loop = None

    async def get(
        self, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any] | list[Any] | str:
        params, headers = self._url_builder.filter_and_sign(params, headers)
        return await self._request(METH_GET, params=params, headers=headers)

    async def post(
        self, data: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any] | list[Any] | str:
        data, headers = self._url_builder.filter_and_sign(data, headers)
        return await self._request(METH_POST, data=data, headers=headers)

    def _ensure_loop(self) -> AbstractEventLoop:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            if self._loop is None:
                raise RuntimeError(
                    'Network requests must be awaited from within a running event loop. '
                    'Instantiate the client inside the loop or pass an explicit loop instance.'
                ) from exc

            loop = self._loop
            if not loop.is_running():
                raise RuntimeError(
                    'The stored event loop is not running; create the Network inside an active loop.'
                ) from exc
        else:
            self._loop = loop

        return loop

    async def _get_retry_client(self) -> RetryClient:
        loop = self._ensure_loop()

        if self._retry_client is not None and self._bound_loop is not loop:
            # Re-bind the transport if the active loop changed between requests.
            await self._retry_client.close()
            self._retry_client = None

        if self._retry_client is None:
            session = ClientSession(timeout=self._timeout)
            self._retry_client = RetryClient(
                client_session=session, retry_options=self._retry_options
            )
            self._bound_loop = loop

        return self._retry_client

    async def _request(
        self,
        method: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any] | str:
        retry_client = await self._get_retry_client()

        async with self._throttler:
            response = await self._aiohttp_request(
                retry_client, method, data, params, headers
            )
            return await self._handle_response(response)

    async def _aiohttp_request(
        self,
        client: RetryClient,
        method: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> aiohttp.ClientResponse:
        session_method = getattr(client, method.lower())
        request_kwargs: dict[str, Any] = {
            'url': self._url_builder.API_URL,
            'params': params,
            'headers': headers,
        }
        if data is not None:
            request_kwargs['data'] = data
        if self._proxy is not None:
            request_kwargs['proxy'] = self._proxy

        async with session_method(**request_kwargs) as response:
            self._logger.debug(
                '[%s] %r %r %s', method, str(response.url), data, headers, response.status
            )
            return cast(aiohttp.ClientResponse, response)

    async def _handle_response(
        self, response: aiohttp.ClientResponse
    ) -> dict[str, Any] | list[Any] | str:
        try:
            status = response.status
            response_json = await _maybe_await(response.json())
        except aiohttp.ContentTypeError:
            raise ChainscanClientContentTypeError(
                status, await _maybe_await(response.text)
            ) from None
        except Exception as e:
            raise ChainscanClientError(e) from e
        else:
            self._logger.debug('Response: %r', str(response_json)[0:200])
            self._raise_if_error(response_json)
            return cast(dict[str, Any] | list[Any] | str, response_json['result'])

    @staticmethod
    def _raise_if_error(response_json: dict[str, Any]) -> None:
        if 'status' in response_json and response_json['status'] != '1':
            message, result = response_json.get('message'), response_json.get('result')
            raise ChainscanClientApiError(message, result)

        if 'error' in response_json:
            err = response_json['error']
            code, message = err.get('code'), err.get('message')
            raise ChainscanClientProxyError(code, message)
