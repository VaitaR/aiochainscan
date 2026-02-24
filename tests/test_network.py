"""Tests for Network transport layer using httpx/tenacity/aiolimiter."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import orjson
import pytest
import pytest_asyncio

from aiochainscan.adapters.aiolimiter_adapter import AioLimiterAdapter
from aiochainscan.adapters.tenacity_retry import TenacityRetryAdapter
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientProxyError,
    ChainscanRateLimitError,
)
from aiochainscan.network import Network
from aiochainscan.url_builder import UrlBuilder


@pytest_asyncio.fixture
async def ub():
    ub = UrlBuilder('test_api_key', 'eth', 'main')
    yield ub


@pytest_asyncio.fixture
async def nw(ub):
    nw = Network(ub, timeout=10.0)
    yield nw
    await nw.close()


def test_init(ub):
    """Test Network initialization with various parameters."""
    proxy = 'http://proxy:8080'
    timeout = httpx.Timeout(5.0)
    rate_limiter = AioLimiterAdapter(max_rate=10.0, time_period=1.0)
    retry_policy = TenacityRetryAdapter(max_attempts=3)

    n = Network(
        ub,
        timeout=timeout,
        proxy=proxy,
        rate_limiter=rate_limiter,
        retry_policy=retry_policy,
        http2=False,
        max_connections=50,
    )

    assert n._url_builder is ub
    assert n._timeout is timeout
    assert n._proxy is proxy
    assert n._rate_limiter is rate_limiter
    assert n._retry_policy is retry_policy
    assert n._http2 is False
    assert n._max_connections == 50
    assert n._client is None
    assert isinstance(n._logger, logging.Logger)


def test_default_timeout(ub):
    """Test default timeout initialization."""
    # Float timeout
    n1 = Network(ub, timeout=5.0)
    assert n1._timeout.connect == 5.0

    # None timeout (uses default)
    n2 = Network(ub, timeout=None)
    assert n2._timeout.connect == 10.0

    # httpx.Timeout passthrough
    custom_timeout = httpx.Timeout(15.0, connect=5.0)
    n3 = Network(ub, timeout=custom_timeout)
    assert n3._timeout is custom_timeout


def test_default_adapters(ub):
    """Test that default adapters are created."""
    n = Network(ub)

    assert isinstance(n._rate_limiter, AioLimiterAdapter)
    assert isinstance(n._retry_policy, TenacityRetryAdapter)


@pytest.mark.asyncio
async def test_get(nw):
    """Test GET request routing."""
    with patch.object(nw, '_request', new=AsyncMock()) as mock:
        await nw.get()
        mock.assert_called_once_with(
            'GET',
            params={'chainid': '1'},
            headers={'X-API-Key': nw._url_builder._API_KEY},
        )


@pytest.mark.asyncio
async def test_post(nw):
    """Test POST request routing."""
    with patch.object(nw, '_request', new=AsyncMock()) as mock:
        await nw.post()
        mock.assert_called_once_with(
            'POST',
            data={'chainid': '1'},
            headers={'X-API-Key': nw._url_builder._API_KEY},
        )

    with patch.object(nw, '_request', new=AsyncMock()) as mock:
        await nw.post({'some': 'data'})
        mock.assert_called_once_with(
            'POST',
            data={'chainid': '1', 'some': 'data'},
            headers={'X-API-Key': nw._url_builder._API_KEY},
        )

    with patch.object(nw, '_request', new=AsyncMock()) as mock:
        await nw.post({'some': 'data', 'null': None})
        mock.assert_called_once_with(
            'POST',
            data={'chainid': '1', 'some': 'data'},
            headers={'X-API-Key': nw._url_builder._API_KEY},
        )


@pytest.mark.asyncio
async def test_request_with_mocked_httpx():
    """Test Network._request method with httpx mocking."""
    url_builder = UrlBuilder('test_api_key', 'eth', 'main')
    network = Network(url_builder)

    try:
        mock_response_data = {'status': '1', 'result': 'test_result'}

        # Test GET request
        with patch.object(httpx.AsyncClient, 'get') as mock_get:
            mock_response = MagicMock(spec=httpx.Response)
            mock_response.status_code = 200
            mock_response.headers = {'content-type': 'application/json'}
            mock_response.content = orjson.dumps(mock_response_data)
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await network.get(params={'test': 'param'})

            assert result == 'test_result'
            assert mock_get.called

        # Test POST request
        with patch.object(httpx.AsyncClient, 'post') as mock_post:
            mock_response = MagicMock(spec=httpx.Response)
            mock_response.status_code = 200
            mock_response.headers = {'content-type': 'application/json'}
            mock_response.content = orjson.dumps(mock_response_data)
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = await network.post(data={'test': 'data'})

            assert result == 'test_result'
            assert mock_post.called

    finally:
        await network.close()


@pytest.mark.asyncio
async def test_handle_response(nw):
    """Test response handling with various scenarios."""

    def make_mock_response(
        data: str,
        status_code: int = 200,
        content_type: str = 'application/json',
        raise_for_status_error: Exception | None = None,
    ) -> MagicMock:
        mock = MagicMock(spec=httpx.Response)
        mock.status_code = status_code
        mock.headers = {'content-type': content_type}
        mock.text = data
        # Set content as bytes for orjson parsing
        mock.content = data.encode('utf-8')

        if raise_for_status_error:
            mock.raise_for_status.side_effect = raise_for_status_error
        else:
            mock.raise_for_status = MagicMock()

        return mock

    # Test ContentTypeError (non-JSON response)
    with pytest.raises(ChainscanClientContentTypeError) as e:
        nw._handle_response(make_mock_response('not json', content_type='text/html'))
    assert e.value.status == 200
    assert e.value.content == 'not json'

    # Test API error response
    with pytest.raises(ChainscanClientApiError) as e:
        nw._handle_response(
            make_mock_response('{"status": "0", "message": "NOTOK", "result": "res"}')
        )
    assert e.value.message == 'NOTOK'
    assert e.value.result == 'res'

    # Test proxy error response
    with pytest.raises(ChainscanClientProxyError) as e:
        nw._handle_response(make_mock_response('{"error": {"code": "100", "message": "msg"}}'))
    assert e.value.code == '100'
    assert e.value.message == 'msg'

    # Test rate limit error in body
    with pytest.raises(ChainscanRateLimitError):
        nw._handle_response(
            make_mock_response(
                '{"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}'
            )
        )

    # Test successful response with result field
    assert nw._handle_response(make_mock_response('{"result": "some_result"}')) == 'some_result'

    # Test successful response with nested result
    payload = nw._handle_response(
        make_mock_response('{"status": "1", "result": {"items": [{"foo": "bar"}]}}')
    )
    assert payload == {'items': [{'foo': 'bar'}]}

    # Test HTTP 429 error
    with pytest.raises(ChainscanRateLimitError):
        mock_429 = make_mock_response(
            '{}',
            status_code=429,
            raise_for_status_error=httpx.HTTPStatusError(
                'Too Many Requests',
                request=MagicMock(),
                response=MagicMock(status_code=429),
            ),
        )
        nw._handle_response(mock_429)


@pytest.mark.asyncio
async def test_close_session(nw):
    """Test client cleanup on close."""
    # First close without client initialized
    await nw.close()
    assert nw._client is None

    # Initialize client and then close
    await nw._ensure_client()
    assert nw._client is not None

    await nw.close()
    assert nw._client is None
