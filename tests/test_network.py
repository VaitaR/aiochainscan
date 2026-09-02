"""Tests for Network transport layer using httpx/tenacity/aiolimiter."""

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import orjson
import pytest
import pytest_asyncio

from aiochainscan.adapters.aiolimiter_adapter import AioLimiterAdapter
from aiochainscan.adapters.tenacity_retry import TenacityRetryAdapter
from aiochainscan.core.url_builder import UrlBuilder
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanDataError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
    ChainscanResponseTooLargeError,
    FailureKind,
)
from aiochainscan.network import (
    Network,
    _redact_headers,
    _redact_payload,
    _redact_url,
    api_error_failure_kind,
)


def _ok_handler(request: httpx.Request) -> httpx.Response:
    """MockTransport handler answering a healthy Etherscan-style envelope."""
    return httpx.Response(200, json={'status': '1', 'message': 'OK', 'result': 'ok'})


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
            params={'chainid': '1', 'apikey': nw._url_builder._API_KEY},
            headers={},
        )


@pytest.mark.asyncio
async def test_post(nw):
    """Test POST request routing."""
    with patch.object(nw, '_request', new=AsyncMock()) as mock:
        await nw.post()
        mock.assert_called_once_with(
            'POST',
            data={'chainid': '1', 'apikey': nw._url_builder._API_KEY},
            headers={},
        )

    with patch.object(nw, '_request', new=AsyncMock()) as mock:
        await nw.post({'some': 'data'})
        mock.assert_called_once_with(
            'POST',
            data={'chainid': '1', 'some': 'data', 'apikey': nw._url_builder._API_KEY},
            headers={},
        )

    with patch.object(nw, '_request', new=AsyncMock()) as mock:
        await nw.post({'some': 'data', 'null': None})
        mock.assert_called_once_with(
            'POST',
            data={'chainid': '1', 'some': 'data', 'apikey': nw._url_builder._API_KEY},
            headers={},
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
async def test_http_503_is_retryable_network_error(ub):
    """HTTP 5xx responses must enter the configured network retry policy."""
    response = httpx.Response(
        503,
        request=httpx.Request('GET', 'https://example.com/api?apikey=secret123'),
        text='service unavailable',
    )

    network = Network(ub)
    try:
        with pytest.raises(ChainscanNetworkError) as exc_info:
            network._handle_response(response)
    finally:
        await network.close()

    assert exc_info.value.retryable is True
    assert 'secret123' not in str(exc_info.value)


@pytest.mark.asyncio
async def test_http_503_retries_then_succeeds(ub):
    """A transient HTTP 503 is retried through Network's RetryPolicy seam."""
    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock()
    retry_policy = TenacityRetryAdapter(
        max_attempts=2,
        min_wait=0.0,
        max_wait=0.0,
        jitter=0.0,
        retry_exceptions=(ChainscanNetworkError,),
    )
    network = Network(ub, rate_limiter=rate_limiter, retry_policy=retry_policy)
    responses = [
        httpx.Response(
            503,
            request=httpx.Request('GET', 'https://example.com/api'),
            text='service unavailable',
        ),
        httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.com/api'),
            json={'result': 'ok'},
        ),
    ]

    try:
        with patch.object(
            httpx.AsyncClient, 'get', new=AsyncMock(side_effect=responses)
        ) as mock_get:
            assert await network.get() == 'ok'
    finally:
        await network.close()

    assert mock_get.await_count == 2


@pytest.mark.asyncio
async def test_http_400_is_non_retryable_and_redacts_url(ub):
    """Other HTTP 4xx responses remain plain client errors with safe URLs."""
    response = httpx.Response(
        400,
        request=httpx.Request('GET', 'https://example.com/api?apikey=secret123&foo=bar'),
        text='bad request',
    )

    network = Network(ub)
    try:
        with pytest.raises(ChainscanClientError) as exc_info:
            network._handle_response(response)
    finally:
        await network.close()

    assert type(exc_info.value) is ChainscanClientError
    assert 'secret123' not in str(exc_info.value)
    assert 'foo=bar' in str(exc_info.value)


@pytest.mark.asyncio
async def test_close_session(nw):
    """Test client cleanup on close."""
    # First close without client initialized
    await nw.close()
    assert nw._client is None

    # Close is terminal and cannot lazily reopen the transport.
    with pytest.raises(ChainscanClientError, match='Network is closed'):
        await nw._ensure_client()


def test_redact_headers_and_payload() -> None:
    headers = _redact_headers(
        {
            'Authorization': 'Bearer secret',
            'X-Access-Token': 'token-secret',
            'Cookie': 'session-secret',
            'Proxy-Authorization': 'proxy-secret',
            'X-Trace': 'keep-me',
        }
    )
    assert headers == {
        'Authorization': '***REDACTED***',
        'X-Access-Token': '***REDACTED***',
        'Cookie': '***REDACTED***',
        'Proxy-Authorization': '***REDACTED***',
        'X-Trace': 'keep-me',
    }

    payload = _redact_payload({'api_key': 'secret', 'nested': {'token': 'secret', 'ok': 1}})
    assert payload == {
        'api_key': '***REDACTED***',
        'nested': {'token': '***REDACTED***', 'ok': 1},
    }


def test_redact_url_userinfo_and_sensitive_query_names() -> None:
    redacted = _redact_url(
        'https://user:password@example.com/api?access_token=secret&foo=bar&secret=x'
    )
    assert 'user' not in redacted
    assert 'password' not in redacted
    assert '=x' not in redacted
    assert 'access_token=%2A%2A%2AREDACTED%2A%2A%2A' in redacted
    assert 'foo=bar' in redacted


def test_http_status_error_chain_is_sanitized(ub) -> None:
    response = httpx.Response(
        503,
        request=httpx.Request('GET', 'https://user:secret@example.com/api?token=secret'),
        text='service unavailable',
    )
    network = Network(ub)

    with pytest.raises(ChainscanNetworkError) as exc_info:
        network._handle_response(response)

    assert not isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)
    assert not isinstance(exc_info.value.__context__, httpx.HTTPStatusError)
    assert 'secret' not in str(exc_info.value)


@pytest.mark.parametrize('payload', [['error'], 'error'])
@pytest.mark.asyncio
async def test_top_level_list_and_string_payloads_are_valid(nw, payload) -> None:
    response = httpx.Response(
        200,
        headers={'content-type': 'application/json'},
        content=orjson.dumps(payload),
    )
    assert nw._handle_response(response) == payload


@pytest.mark.asyncio
async def test_dict_error_string_and_list_are_inspected(nw) -> None:
    with pytest.raises(ChainscanClientProxyError) as string_error:
        nw._handle_response(
            httpx.Response(
                200,
                headers={'content-type': 'application/json'},
                json={'error': 'proxy failed'},
            )
        )
    assert string_error.value.message == 'proxy failed'

    with pytest.raises(ChainscanClientProxyError) as list_error:
        nw._handle_response(
            httpx.Response(
                200,
                headers={'content-type': 'application/json'},
                json={'error': ['proxy failed']},
            )
        )
    assert list_error.value.message == '<list with 1 items>'


def test_response_size_is_rejected_before_json_parsing(ub) -> None:
    network = Network(ub, max_response_bytes=10)
    response = httpx.Response(
        200,
        headers={'content-type': 'application/json'},
        content=b'{"result":"too large"}',
    )

    with pytest.raises(ChainscanResponseTooLargeError, match='exceeds'):
        network._handle_response(response)


def test_redact_url_query_api_key() -> None:
    """Sensitive query params in URL must be redacted before logging."""
    url = 'https://api.etherscan.io/v2/api?module=account&apikey=secret123&chainid=1'
    redacted = _redact_url(url)

    assert 'secret123' not in redacted
    assert 'apikey=%2A%2A%2AREDACTED%2A%2A%2A' in redacted
    assert 'module=account' in redacted
    assert 'chainid=1' in redacted


# ---------------------------------------------------------------------------
# Raise-site failure kinds: the exception carries its classification from the
# moment it is raised — the pool classifies by lookup, not by re-parsing text.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('message', 'result', 'expected'),
    [
        ('NOTOK', 'Invalid API Key', FailureKind.AUTH),
        ('NOTOK', 'Missing/Invalid API Key', FailureKind.AUTH),
        ('Invalid API key provided', None, FailureKind.AUTH),
        ('NOTOK', 'Free API Access is not supported for this chain', FailureKind.PLAN_RESTRICTED),
        ('NOTOK', 'you are trying to access an API Pro endpoint', FailureKind.PLAN_RESTRICTED),
        ('NOTOK', 'No transactions found', FailureKind.FATAL),
        (None, None, FailureKind.FATAL),
    ],
)
def test_api_error_failure_kind_classifies_etherescan_texts(
    message: str | None, result: Any, expected: FailureKind
) -> None:
    assert api_error_failure_kind(message, result) is expected


@pytest.mark.parametrize(
    ('message', 'result', 'expected'),
    [
        ('NOTOK', 'Invalid API Key', FailureKind.AUTH),
        (
            'NOTOK',
            'Free API Access is not supported for this chain',
            FailureKind.PLAN_RESTRICTED,
        ),
        ('NOTOK', 'No transactions found', FailureKind.FATAL),
    ],
)
@pytest.mark.asyncio
async def test_api_error_raise_site_carries_failure_kind(
    ub, message: str, result: str, expected: FailureKind
) -> None:
    """The API-error flatten in _raise_if_error attaches the kind computed
    from the envelope — no regex left to run at classification time."""
    network = Network(ub)
    response = httpx.Response(
        200,
        headers={'content-type': 'application/json'},
        json={'status': '0', 'message': message, 'result': result},
    )
    try:
        with pytest.raises(ChainscanClientApiError) as exc_info:
            network._handle_response(response)
    finally:
        await network.close()

    assert exc_info.value.failure_kind is expected


@pytest.mark.asyncio
async def test_rate_limit_in_http_200_carries_rate_limit_kind(ub) -> None:
    """The hidden rate-limit detection (HTTP 200 + rate-limit text) raises a
    ChainscanRateLimitError whose class default carries RATE_LIMIT."""
    network = Network(ub)
    response = httpx.Response(
        200,
        headers={'content-type': 'application/json'},
        json={'status': '0', 'message': 'NOTOK', 'result': 'Max rate limit reached'},
    )
    try:
        with pytest.raises(ChainscanRateLimitError) as exc_info:
            network._handle_response(response)
    finally:
        await network.close()

    assert exc_info.value.failure_kind is FailureKind.RATE_LIMIT


@pytest.mark.parametrize(
    ('status_code', 'expected_exc', 'expected_kind'),
    [
        (429, ChainscanRateLimitError, FailureKind.RATE_LIMIT),
        (503, ChainscanNetworkError, FailureKind.TRANSIENT),
        (400, ChainscanClientError, FailureKind.FATAL),
    ],
)
@pytest.mark.asyncio
async def test_http_status_raise_sites_carry_failure_kinds(
    ub, status_code: int, expected_exc: type[Exception], expected_kind: FailureKind
) -> None:
    network = Network(ub)
    response = httpx.Response(
        status_code,
        request=httpx.Request('GET', 'https://example.com/api'),
        text='boom',
    )
    try:
        with pytest.raises(expected_exc) as exc_info:
            network._handle_response(response)
    finally:
        await network.close()

    assert exc_info.value.failure_kind is expected_kind


def test_redact_url_path_api_key() -> None:
    """Key-shaped path segments (NodeReal /v1/{key}) must be redacted."""
    url = 'https://bsc-mainnet.nodereal.io/v1/64a9df0874fb4a93b9d0a3849de012d3'
    redacted = _redact_url(url)

    assert '64a9df0874fb4a93b9d0a3849de012d3' not in redacted
    assert redacted == 'https://bsc-mainnet.nodereal.io/v1/***REDACTED***'


def test_redact_url_path_open_platform_key() -> None:
    """open-platform endpoints embed the key mid-path."""
    url = (
        'https://open-platform.nodereal.io/64a9df0874fb4a93b9d0a3849de012d3/bsc-mainnet/contract/'
    )
    redacted = _redact_url(url)

    assert '64a9df08' not in redacted
    assert '/***REDACTED***/bsc-mainnet/contract/' in redacted


def test_redact_url_keeps_non_key_path_segments() -> None:
    """Real path resources (addresses, tx hashes) must not be redacted."""
    url = 'https://eth.blockscout.com/api/v2/transactions/0x' + 'ab' * 32
    redacted = _redact_url(url)

    assert '0x' + 'ab' * 32 in redacted


def test_redact_url_query_case_insensitive() -> None:
    """Redaction must be case-insensitive for query parameter names."""
    url = 'https://example.com/api?API_KEY=topsecret&key=abc&foo=bar'
    redacted = _redact_url(url)

    assert 'topsecret' not in redacted
    assert 'abc' not in redacted
    assert 'API_KEY=%2A%2A%2AREDACTED%2A%2A%2A' in redacted
    assert 'key=%2A%2A%2AREDACTED%2A%2A%2A' in redacted
    assert 'foo=bar' in redacted


# ---------------------------------------------------------------------------
# First-request guard: transient vs fatal failure memory
# ---------------------------------------------------------------------------


class TestFirstRequestGuardFailureMemory:
    """A transient probe failure must not brick the client forever.

    The guard runs outside the retry policy; before the fix, ANY guard error
    (including one-off 429/5xx/DNS blips on the probe itself) was cached and
    re-raised from every subsequent request for the client's lifetime.
    """

    @staticmethod
    def _guarded_network(ub: UrlBuilder, guard: Any) -> Network:
        network = Network(ub, timeout=10.0, first_request_guard=guard)
        network._client = httpx.AsyncClient(transport=httpx.MockTransport(_ok_handler))
        return network

    @staticmethod
    async def _close(network: Network) -> None:
        # Drop the injected client so close() does not double-close it.
        injected = network._client
        network._client = None
        await injected.aclose()
        await network.close()

    async def test_transient_guard_error_re_probes_on_next_request(self, ub: UrlBuilder) -> None:
        guard_calls = 0

        async def guard() -> None:
            nonlocal guard_calls
            guard_calls += 1
            if guard_calls == 1:
                raise ChainscanRateLimitError('HTTP 429', 'Too Many Requests')

        network = self._guarded_network(ub, guard)
        try:
            with pytest.raises(ChainscanRateLimitError):
                await network.get(params={'module': 'proxy', 'action': 'test'})
            # The next request re-probes the guard and succeeds.
            result = await network.get(params={'module': 'proxy', 'action': 'test'})
            assert result == 'ok'
            assert guard_calls == 2
        finally:
            await self._close(network)

    async def test_config_guard_error_fails_fast_forever(self, ub: UrlBuilder) -> None:
        async def guard() -> None:
            raise ChainscanDataError('Chain mismatch: expected 137, instance serves 1')

        network = self._guarded_network(ub, guard)
        try:
            for _ in range(2):
                with pytest.raises(ChainscanDataError, match='Chain mismatch'):
                    await network.get(params={'module': 'proxy', 'action': 'test'})
            # The guard runs only once — the error is remembered, not re-probed.
        finally:
            await self._close(network)
