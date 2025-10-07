import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
pytest.importorskip('aiohttp', reason='Network transport tests require aiohttp runtime')

import aiohttp
import pytest_asyncio
from aiohttp import ClientTimeout
from aiohttp.hdrs import METH_GET, METH_POST
from aiohttp_retry import ExponentialRetry
from asyncio_throttle import Throttler

from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientError,
    ChainscanClientProxyError,
)
from aiochainscan.network import Network
from aiochainscan.url_builder import UrlBuilder


class SessionMock(AsyncMock):
    # noinspection PyUnusedLocal
    @pytest.mark.asyncio
    async def get(self, url, params, data):
        return AsyncCtxMgrMock()


class AsyncCtxMgrMock(MagicMock):
    @pytest.mark.asyncio
    async def __aenter__(self):
        return self.aenter

    @pytest.mark.asyncio
    async def __aexit__(self, *args):
        pass


def get_loop():
    return asyncio.get_event_loop()


@pytest_asyncio.fixture
async def ub():
    ub = UrlBuilder('test_api_key', 'eth', 'main')
    yield ub


@pytest_asyncio.fixture
async def nw(ub):
    nw = Network(ub, get_loop(), None, None, None, None)
    yield nw
    await nw.close()


def test_init(ub):
    myloop = get_loop()
    proxy = 'qwe'
    timeout = ClientTimeout(5)
    throttler = Throttler(1)
    retry_options = ExponentialRetry()
    n = Network(ub, myloop, timeout, proxy, throttler, retry_options)

    assert n._url_builder is ub
    assert n._loop == myloop
    assert n._timeout is timeout
    assert n._proxy is proxy
    assert n._throttler is throttler

    assert n._retry_options is retry_options
    assert n._retry_client is None

    assert isinstance(n._logger, logging.Logger)


def test_no_loop(ub):
    network = Network(ub, None, None, None, None, None)
    assert network._loop is None


@pytest.mark.asyncio
async def test_get(nw):
    with patch('aiochainscan.network.Network._request', new=AsyncMock()) as mock:
        await nw.get()
        mock.assert_called_once_with(
            METH_GET, params={'apikey': nw._url_builder._API_KEY}, headers={}
        )


@pytest.mark.asyncio
async def test_post(nw):
    with patch('aiochainscan.network.Network._request', new=AsyncMock()) as mock:
        await nw.post()
        mock.assert_called_once_with(
            METH_POST, data={'apikey': nw._url_builder._API_KEY}, headers={}
        )

    with patch('aiochainscan.network.Network._request', new=AsyncMock()) as mock:
        await nw.post({'some': 'data'})
        mock.assert_called_once_with(
            METH_POST, data={'apikey': nw._url_builder._API_KEY, 'some': 'data'}, headers={}
        )

    with patch('aiochainscan.network.Network._request', new=AsyncMock()) as mock:
        await nw.post({'some': 'data', 'null': None})
        mock.assert_called_once_with(
            METH_POST, data={'apikey': nw._url_builder._API_KEY, 'some': 'data'}, headers={}
        )


@pytest.mark.asyncio
async def test_request(nw):
    throttler_enter = AsyncMock()
    throttler_exit = AsyncMock()
    nw._throttler = AsyncMock()
    nw._throttler.__aenter__ = throttler_enter
    nw._throttler.__aexit__ = throttler_exit

    retry_client = object()
    with patch.object(nw, '_get_retry_client', new=AsyncMock(return_value=retry_client)):
        with patch.object(nw, '_aiohttp_request', new=AsyncMock()) as request_mock:
            with patch.object(nw, '_handle_response', new=AsyncMock()) as handle_mock:
                await nw._request(METH_GET)
                throttler_enter.assert_awaited_once()
                request_mock.assert_awaited_once_with(
                    retry_client,
                    METH_GET,
                    None,
                    None,
                    None,
                )
                handle_mock.assert_awaited_once()

    with patch.object(nw, '_get_retry_client', new=AsyncMock(return_value=retry_client)):
        with patch.object(nw, '_aiohttp_request', new=AsyncMock()) as request_mock:
            with patch.object(nw, '_handle_response', new=AsyncMock()) as handle_mock:
                await nw._request(METH_POST)
                throttler_enter.assert_awaited()
                request_mock.assert_awaited_with(
                    retry_client,
                    METH_POST,
                    None,
                    None,
                    None,
                )
                handle_mock.assert_awaited()

    assert throttler_enter.await_count == 2
    assert throttler_exit.await_count == 2


# noinspection PyTypeChecker
@pytest.mark.asyncio
async def test_handle_response(nw):
    class MockResponse:
        def __init__(self, data, raise_exc=None):
            self.data = data
            self.raise_exc = raise_exc

        @property
        def status(self):
            return 200

        @property
        def status_code(self):
            return 200

        @property
        def text(self):
            async def _text():
                return 'some text'

            return _text

        def json(self):
            if self.raise_exc:
                raise self.raise_exc
            async def _json():
                return json.loads(self.data)

            return _json()

    with pytest.raises(ChainscanClientContentTypeError) as e:
        await nw._handle_response(MockResponse('some', aiohttp.ContentTypeError('info', 'hist')))
    assert e.value.status == 200
    assert e.value.content == 'some text'

    with pytest.raises(ChainscanClientError, match='some exception'):
        await nw._handle_response(MockResponse('some', Exception('some exception')))

    with pytest.raises(ChainscanClientApiError) as e:
        await nw._handle_response(
            MockResponse('{"status": "0", "message": "NOTOK", "result": "res"}')
        )
    assert e.value.message == 'NOTOK'
    assert e.value.result == 'res'

    with pytest.raises(ChainscanClientProxyError) as e:
        await nw._handle_response(MockResponse('{"error": {"code": "100", "message": "msg"}}'))
    assert e.value.code == '100'
    assert e.value.message == 'msg'

    assert await nw._handle_response(MockResponse('{"result": "some_result"}')) == 'some_result'


@pytest.mark.asyncio
async def test_close_session(nw):
    with patch('aiohttp.ClientSession.close', new_callable=AsyncMock) as m:
        await nw.close()
        m: AsyncMock
        m.assert_not_called()

        nw._retry_client = MagicMock()
        nw._retry_client.close = AsyncMock()
        await nw.close()
        nw._retry_client.close.assert_called_once()
