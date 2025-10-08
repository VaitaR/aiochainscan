import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip('aiohttp', reason='Network transport tests require aiohttp runtime')

import aiohttp  # noqa: E402
import pytest_asyncio  # noqa: E402
from aiohttp import ClientTimeout  # noqa: E402
from aiohttp.hdrs import METH_GET, METH_POST  # noqa: E402
from aiohttp_retry import ExponentialRetry  # noqa: E402
from asyncio_throttle import Throttler  # noqa: E402

from aiochainscan.exceptions import (  # noqa: E402
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientError,
    ChainscanClientProxyError,
)
from aiochainscan.network import Network  # noqa: E402
from aiochainscan.url_builder import UrlBuilder  # noqa: E402


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
async def test_request():
    """Test Network._request method with proper mocking.

    This test verifies that Network correctly:
    - Constructs URLs using UrlBuilder
    - Makes HTTP requests (GET/POST)
    - Handles responses through aiohttp-retry
    """
    from aiochainscan.network import Network
    from aiochainscan.url_builder import UrlBuilder

    # Create a fresh Network instance with proper initialization
    url_builder = UrlBuilder('test_api_key', 'eth', 'main')
    network = Network(url_builder)

    try:
        # Mock the actual HTTP response at the aiohttp level
        mock_response_data = {'status': '1', 'result': 'test_result'}

        # Test GET request - mock at the aiohttp_retry level
        with patch('aiohttp_retry.RetryClient.get') as mock_get:
            # Setup mock response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.text = AsyncMock(return_value='')
            # RetryClient.get is a context manager
            mock_get.return_value.__aenter__.return_value = mock_response
            mock_get.return_value.__aexit__.return_value = AsyncMock()

            result = await network.get(params={'test': 'param'})

            # Verify the result
            assert result == 'test_result'
            assert mock_get.called

        # Test POST request
        with patch('aiohttp_retry.RetryClient.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.text = AsyncMock(return_value='')
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = AsyncMock()

            result = await network.post(data={'test': 'data'})

            assert result == 'test_result'
            assert mock_post.called

    finally:
        await network.close()


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

    payload = await nw._handle_response(
        MockResponse('{"status": "1", "result": {"items": [{"foo": "bar"}]}}')
    )
    assert payload == {'items': [{'foo': 'bar'}]}


@pytest.mark.asyncio
async def test_close_session(nw):
    with patch('aiohttp.ClientSession.close', new_callable=AsyncMock) as m:
        await nw.close()
        m: AsyncMock
        m.assert_not_called()

        nw._retry_client = MagicMock()
        retry_client = nw._retry_client
        retry_client.close = AsyncMock()
        await nw.close()
        retry_client.close.assert_awaited_once()
        assert nw._retry_client is None
