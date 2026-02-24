"""Tests for HttpxClientAdapter with HTTP/2 support."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import orjson
import pytest

from aiochainscan.adapters.httpx_client import HttpxClientAdapter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def client() -> AsyncGenerator[HttpxClientAdapter, None]:
    """Create a client fixture for tests."""
    async with HttpxClientAdapter(timeout=10.0, http2=True) as client:
        yield client


class TestHttpxClientAdapterInit:
    """Test HttpxClientAdapter initialization."""

    def test_default_init(self) -> None:
        """Test default initialization values.

        HTTP/2 is disabled by default because rate-limited APIs behind
        Cloudflare interpret multiplexed streams as DDoS attacks.
        """
        adapter = HttpxClientAdapter()
        assert adapter._http2 is False
        assert adapter._timeout is not None
        assert adapter._timeout.connect == 30.0
        assert adapter._headers == {}
        assert adapter._max_connections == 10
        assert adapter._max_keepalive_connections == 5
        assert adapter._proxy is None
        assert adapter._client is None

    def test_custom_init(self) -> None:
        """Test custom initialization values."""
        headers = {'X-Custom': 'value'}
        adapter = HttpxClientAdapter(
            timeout=60.0,
            http2=False,
            headers=headers,
            max_connections=50,
            max_keepalive_connections=10,
            proxy='http://proxy:8080',
        )
        assert adapter._http2 is False
        assert adapter._timeout.connect == 60.0
        assert adapter._headers == {'X-Custom': 'value'}
        assert adapter._max_connections == 50
        assert adapter._max_keepalive_connections == 10
        assert adapter._proxy == 'http://proxy:8080'

    def test_none_timeout(self) -> None:
        """Test initialization with no timeout."""
        adapter = HttpxClientAdapter(timeout=None)
        assert adapter._timeout is None


class TestHttpxClientAdapterContextManager:
    """Test context manager lifecycle."""

    async def test_context_manager_creates_client(self) -> None:
        """Test that entering context creates the client."""
        adapter = HttpxClientAdapter()
        assert adapter._client is None

        async with adapter:
            assert adapter._client is not None
            assert isinstance(adapter._client, httpx.AsyncClient)

        assert adapter._client is None

    async def test_context_manager_closes_on_exception(self) -> None:
        """Test that client is closed even on exception."""
        adapter = HttpxClientAdapter()

        with pytest.raises(ValueError, match='test error'):
            async with adapter:
                assert adapter._client is not None
                raise ValueError('test error')

        assert adapter._client is None

    async def test_aclose_idempotent(self) -> None:
        """Test that aclose can be called multiple times safely."""
        adapter = HttpxClientAdapter()
        async with adapter:
            pass

        # Should not raise
        await adapter.aclose()
        await adapter.aclose()
        assert adapter._client is None


class TestHttpxClientAdapterGet:
    """Test GET request functionality."""

    async def test_get_json_response(self) -> None:
        """Test GET request with JSON response."""
        adapter = HttpxClientAdapter()

        mock_response = MagicMock()
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.content = orjson.dumps({'status': '1', 'result': 'success'})
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            async with adapter:
                result = await adapter.get('https://api.example.com/test')

            assert result == {'status': '1', 'result': 'success'}
            mock_get.assert_called_once_with(
                'https://api.example.com/test',
                params=None,
                headers=None,
            )

    async def test_get_with_params(self) -> None:
        """Test GET request with query parameters."""
        adapter = HttpxClientAdapter()

        mock_response = MagicMock()
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.content = orjson.dumps({'balance': '1000000'})
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            async with adapter:
                result = await adapter.get(
                    'https://api.example.com/balance',
                    params={'address': '0x123', 'tag': 'latest'},
                )

            assert result == {'balance': '1000000'}
            mock_get.assert_called_once()
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs['params'] == {'address': '0x123', 'tag': 'latest'}

    async def test_get_with_headers(self) -> None:
        """Test GET request with custom headers."""
        adapter = HttpxClientAdapter()

        mock_response = MagicMock()
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.content = orjson.dumps({})
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            async with adapter:
                await adapter.get(
                    'https://api.example.com/test',
                    headers={'Authorization': 'Bearer token123'},
                )

            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs['headers'] == {'Authorization': 'Bearer token123'}

    async def test_get_text_response(self) -> None:
        """Test GET request with text response."""
        adapter = HttpxClientAdapter()

        mock_response = MagicMock()
        mock_response.headers = {'content-type': 'text/plain'}
        mock_response.text = 'plain text response'
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            async with adapter:
                result = await adapter.get('https://api.example.com/text')

            assert result == 'plain text response'


class TestHttpxClientAdapterPost:
    """Test POST request functionality."""

    async def test_post_with_json(self) -> None:
        """Test POST request with JSON body."""
        adapter = HttpxClientAdapter()

        mock_response = MagicMock()
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.content = orjson.dumps({'id': 1, 'result': 'created'})
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with adapter:
                result = await adapter.post(
                    'https://api.example.com/create',
                    json={'name': 'test'},
                )

            assert result == {'id': 1, 'result': 'created'}
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs['json'] == {'name': 'test'}

    async def test_post_with_form_data(self) -> None:
        """Test POST request with form data."""
        adapter = HttpxClientAdapter()

        mock_response = MagicMock()
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.content = orjson.dumps({'success': True})
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with adapter:
                result = await adapter.post(
                    'https://api.example.com/submit',
                    data={'field1': 'value1', 'field2': 'value2'},
                )

            assert result == {'success': True}
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs['data'] == {'field1': 'value1', 'field2': 'value2'}


class TestHttpxClientAdapterTimeout:
    """Test timeout handling."""

    async def test_timeout_exception(self) -> None:
        """Test that timeout exceptions propagate correctly."""
        adapter = HttpxClientAdapter(timeout=0.001)

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException('Request timed out')

            async with adapter:
                with pytest.raises(httpx.TimeoutException, match='timed out'):
                    await adapter.get('https://api.example.com/slow')


class TestHttpxClientAdapterErrorHandling:
    """Test error status handling."""

    async def test_http_4xx_error(self) -> None:
        """Test handling of 4xx HTTP errors."""
        adapter = HttpxClientAdapter()

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            'Not Found',
            request=MagicMock(),
            response=mock_response,
        )

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            async with adapter:
                with pytest.raises(httpx.HTTPStatusError):
                    await adapter.get('https://api.example.com/missing')

    async def test_http_5xx_error(self) -> None:
        """Test handling of 5xx HTTP errors."""
        adapter = HttpxClientAdapter()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            'Internal Server Error',
            request=MagicMock(),
            response=mock_response,
        )

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            async with adapter:
                with pytest.raises(httpx.HTTPStatusError):
                    await adapter.get('https://api.example.com/error')


class TestHttpxClientAdapterConcurrency:
    """Test concurrent request handling."""

    async def test_concurrent_requests(self) -> None:
        """Test that multiple concurrent requests work correctly."""
        adapter = HttpxClientAdapter()
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate network delay
            mock_response = MagicMock()
            mock_response.headers = {'content-type': 'application/json'}
            mock_response.content = orjson.dumps({'request': call_count})
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch.object(httpx.AsyncClient, 'get', side_effect=mock_get):
            async with adapter:
                tasks = [adapter.get(f'https://api.example.com/endpoint/{i}') for i in range(10)]
                results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert call_count == 10


class TestHttpxClientAdapterLazyInit:
    """Test lazy initialization without context manager."""

    async def test_lazy_client_creation(self) -> None:
        """Test that client is created lazily on first request."""
        adapter = HttpxClientAdapter()
        assert adapter._client is None

        mock_response = MagicMock()
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.content = orjson.dumps({'lazy': True})
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            # First request should create client
            result = await adapter.get('https://api.example.com/test')
            assert adapter._client is not None
            assert result == {'lazy': True}

            # Second request should reuse client
            await adapter.get('https://api.example.com/test2')
            # Client should still be the same instance

        # Cleanup
        await adapter.aclose()
        assert adapter._client is None


class TestHttpxClientAdapterHttp2:
    """Test HTTP/2 configuration."""

    def test_http2_disabled_by_default(self) -> None:
        """Test that HTTP/2 is disabled by default.

        HTTP/2 multiplexing on rate-limited APIs behind Cloudflare
        (Etherscan, BlockScout) triggers WAF blocks (GOAWAY/RST_STREAM)
        instead of HTTP 429 responses.
        """
        adapter = HttpxClientAdapter()
        assert adapter._http2 is False

    def test_http2_can_be_enabled(self) -> None:
        """Test that HTTP/2 can be enabled when needed."""
        adapter = HttpxClientAdapter(http2=True)
        assert adapter._http2 is True

    async def test_client_created_with_http2(self) -> None:
        """Test that client is created with HTTP/2 config."""
        adapter = HttpxClientAdapter(http2=True)

        async with adapter:
            # The actual HTTP/2 setting is passed to AsyncClient
            # We can verify the adapter stored the correct value
            assert adapter._http2 is True


class TestHttpxClientAdapterProtocolCompliance:
    """Test that adapter complies with HttpClient protocol."""

    def test_implements_http_client_protocol(self) -> None:
        """Verify adapter implements HttpClient protocol methods."""
        adapter = HttpxClientAdapter()

        # Check required methods exist
        assert hasattr(adapter, 'aclose')
        assert hasattr(adapter, 'get')
        assert hasattr(adapter, 'post')

        # Check methods are callable
        assert callable(adapter.aclose)
        assert callable(adapter.get)
        assert callable(adapter.post)
