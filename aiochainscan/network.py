import asyncio
import logging
from asyncio import AbstractEventLoop
from contextlib import AbstractAsyncContextManager
from typing import Any

import aiohttp
from aiohttp import ClientTimeout
from aiohttp.client import ClientSession
from aiohttp.hdrs import METH_GET, METH_POST
from aiohttp_retry import RetryClient, RetryOptionsBase
from asyncio_throttle import Throttler
from curl_cffi.requests import AsyncSession as cffiClientSession

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
        throttler: AbstractAsyncContextManager | None = None,
        retry_options: RetryOptionsBase | None = None,
        use_cffi: bool = True,
    ) -> None:
        self._url_builder = url_builder
        self._loop = loop or asyncio.get_running_loop()
        self._timeout = self._prepare_timeout(timeout)
        self._proxy = proxy
        self._throttler = throttler or Throttler(rate_limit=5, period=1.0)
        self._retry_client = None
        self._retry_options = retry_options
        self._logger = logging.getLogger(__name__)
        self._use_cffi = use_cffi

    def _prepare_timeout(self, timeout: float | ClientTimeout | None) -> ClientTimeout:
        if isinstance(timeout, ClientTimeout):
            return timeout
        elif isinstance(timeout, int | float):
            return ClientTimeout(total=timeout)
        else:
            return ClientTimeout(total=10)  # Default timeout

    async def close(self):
        if self._retry_client is not None:
            await self._retry_client.close()

    async def get(self, params: dict = None, headers: dict = None) -> dict | list | str:
        params, headers = self._url_builder.filter_and_sign(params, headers)
        return await self._request(METH_GET, params=params, headers=headers)

    async def post(self, data: dict = None, headers: dict = None) -> dict | list | str:
        data, headers = self._url_builder.filter_and_sign(data, headers)
        return await self._request(METH_POST, data=data, headers=headers)

    def _get_retry_client(self) -> RetryClient | cffiClientSession:
        if self._use_cffi:
            return cffiClientSession(timeout=self._timeout.total)
        else:
            session = ClientSession(loop=self._loop, timeout=self._timeout)
            return RetryClient(client_session=session, retry_options=self._retry_options)

    async def _request(
        self, method: str, data: dict = None, params: dict = None, headers: dict = None
    ) -> dict | list | str:
        if self._retry_client is None:
            self._retry_client = self._get_retry_client()

        async with self._throttler:
            if self._use_cffi:
                response = await self._cffi_request(method, data, params, headers)
            else:
                response = await self._aiohttp_request(method, data, params, headers)

            return await self._handle_response(response)

    async def _cffi_request(
        self, method: str, data: dict = None, params: dict = None, headers: dict = None
    ) -> Any:
        kwargs = {
            'url': self._url_builder.API_URL,
            'params': params,
            'headers': headers,
            'proxies': {'http': self._proxy, 'https': self._proxy} if self._proxy else None,
        }
        if method.lower() == 'post':
            kwargs['data'] = data

        response = await getattr(self._retry_client, method.lower())(**kwargs)
        self._logger.debug(
            '[%s] %r %r %s', method, str(response.url), data, headers, response.status_code
        )
        return response

    async def _aiohttp_request(
        self, method: str, data: dict = None, params: dict = None, headers: dict = None
    ) -> aiohttp.ClientResponse:
        session_method = getattr(self._retry_client, method.lower())
        async with session_method(
            self._url_builder.API_URL, params=params, data=data, headers=headers, proxy=self._proxy
        ) as response:
            self._logger.debug(
                '[%s] %r %r %s', method, str(response.url), data, headers, response.status
            )
            return response

    async def _handle_response(self, response: aiohttp.ClientResponse | Any) -> dict | list | str:
        try:
            if isinstance(response, aiohttp.ClientResponse):
                status = response.status
                response_json = await response.json()
            else:  # cffiClientSession response
                status = response.status_code
                response_json = response.json()
        except aiohttp.ContentTypeError:
            status = (
                response.status
                if isinstance(response, aiohttp.ClientResponse)
                else response.status_code
            )
            raise ChainscanClientContentTypeError(
                status,
                await response.text()
                if isinstance(response, aiohttp.ClientResponse)
                else response.text,
            ) from None
        except Exception as e:
            raise ChainscanClientError(e) from e
        else:
            self._logger.debug('Response: %r', str(response_json)[0:200])
            self._raise_if_error(response_json)
            return response_json['result']

    @staticmethod
    def _raise_if_error(response_json: dict):
        if 'status' in response_json and response_json['status'] != '1':
            message, result = response_json.get('message'), response_json.get('result')
            raise ChainscanClientApiError(message, result)

        if 'error' in response_json:
            err = response_json['error']
            code, message = err.get('code'), err.get('message')
            raise ChainscanClientProxyError(code, message)
