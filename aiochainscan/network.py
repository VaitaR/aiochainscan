from __future__ import annotations

import asyncio
import logging
from asyncio import AbstractEventLoop
from contextlib import AbstractAsyncContextManager
from typing import Any, cast

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
        if loop is not None:
            self._loop = loop
        else:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                # Allow constructing the client in a thread without an active loop; the
                # actual loop will be picked up when the first request is awaited.
                self._loop = asyncio.get_event_loop()
        self._timeout = self._prepare_timeout(timeout)
        self._proxy = proxy
        self._throttler: AbstractAsyncContextManager[Any] = throttler or Throttler(
            rate_limit=5, period=1.0
        )
        self._retry_client: Any | None = None
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

    def _get_retry_client(self) -> Any:
        session = ClientSession(loop=self._loop, timeout=self._timeout)
        return RetryClient(client_session=session, retry_options=self._retry_options)

    async def _request(
        self,
        method: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any] | str:
        if self._retry_client is None:
            self._retry_client = self._get_retry_client()

        async with self._throttler:
            response = await self._aiohttp_request(method, data, params, headers)
            return await self._handle_response(response)

    async def _aiohttp_request(
        self,
        method: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> aiohttp.ClientResponse:
        session_method = getattr(self._retry_client, method.lower())
        async with session_method(
            self._url_builder.API_URL, params=params, data=data, headers=headers, proxy=self._proxy
        ) as response:
            self._logger.debug(
                '[%s] %r %r %s', method, str(response.url), data, headers, response.status
            )
            return cast(aiohttp.ClientResponse, response)

    async def _handle_response(
        self, response: aiohttp.ClientResponse
    ) -> dict[str, Any] | list[Any] | str:
        try:
            status = response.status
            response_json: Any = await response.json()
        except aiohttp.ContentTypeError:
            raise ChainscanClientContentTypeError(status, await response.text()) from None
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
