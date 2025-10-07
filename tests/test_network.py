import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
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
    assert network._loop is not None


@pytest.mark.asyncio
async def test_get(nw):
    with patch('aiochainscan.network.Network._request', new=AsyncMock()) as mock:
        await nw.get()
        mock.assert_called_once_with(
            METH_GET,
            params={'chainid': '1'},
            headers={'X-API-Key': nw._url_builder._API_KEY},
        )


@pytest.mark.asyncio
async def test_post(nw):
    with patch('aiochainscan.network.Network._request', new=AsyncMock()) as mock:
        await nw.post()
        mock.assert_called_once_with(
            METH_POST,
            data={'chainid': '1'},
            headers={'X-API-Key': nw._url_builder._API_KEY},
        )

    with patch('aiochainscan.network.Network._request', new=AsyncMock()) as mock:
        await nw.post({'some': 'data'})
        mock.assert_called_once_with(
            METH_POST,
            data={'chainid': '1', 'some': 'data'},
            headers={'X-API-Key': nw._url_builder._API_KEY},
        )

    with patch('aiochainscan.network.Network._request', new=AsyncMock()) as mock:
        await nw.post({'some': 'data', 'null': None})
        mock.assert_called_once_with(
            METH_POST,
            data={'chainid': '1', 'some': 'data'},
            headers={'X-API-Key': nw._url_builder._API_KEY},
        )


@pytest.mark.asyncio
async def test_request(nw):
    class MagicMockContext(MagicMock):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            type(self).__aenter__ = AsyncMock(return_value=MagicMock())
            type(self).__aexit__ = AsyncMock(return_value=MagicMock())

    nw._retry_client = AsyncMock()

    throttler_mock = AsyncMock()
    nw._throttler = AsyncMock()
    nw._throttler.__aenter__ = throttler_mock

    get_mock = AsyncMock()
    nw._retry_client.get = get_mock
    with patch('aiochainscan.network.Network._handle_response', new=AsyncMock()) as h:
        await nw._request(METH_GET)
        throttler_mock.assert_awaited_once()
        get_mock.assert_called_once_with(
            url='https://api.etherscan.io/v2/api', params=None, headers=None, proxies=None
        )
        h.assert_called_once()

    post_mock = AsyncMock()
    nw._retry_client.post = post_mock
    with patch('aiochainscan.network.Network._handle_response', new=AsyncMock()) as h:
        await nw._request(METH_POST)
        throttler_mock.assert_awaited()
        post_mock.assert_called_once_with(
            url='https://api.etherscan.io/v2/api', params=None, headers=None, proxies=None, data=None
        )
        h.assert_called_once()

    assert throttler_mock.call_count == 2


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
            return 'some text'

        def json(self):
            if self.raise_exc:
                raise self.raise_exc
            return json.loads(self.data)

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
