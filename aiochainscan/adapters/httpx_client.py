"""HttpClient implementation using httpx with HTTP/2 support."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
import orjson

from aiochainscan.ports.http_client import HttpClient


class HttpxClientAdapter(HttpClient):
    """Modern HTTP client using httpx.

    Note: HTTP/2 is disabled by default because API endpoints behind
    Cloudflare (Etherscan, BlockScout) interpret HTTP/2 multiplexed
    streams as Layer 7 DDoS attacks, resulting in GOAWAY/RST_STREAM
    instead of HTTP 429 responses. HTTP/1.1 is more reliable for
    rate-limited blockchain APIs.

    Example usage:
        async with HttpxClientAdapter() as client:
            result = await client.get("https://api.example.com/data")
    """

    def __init__(
        self,
        *,
        timeout: float | None = 30.0,
        http2: bool = False,
        headers: Mapping[str, str] | None = None,
        max_connections: int | None = 10,
        max_keepalive_connections: int | None = 5,
        proxy: str | None = None,
    ) -> None:
        """Create httpx-based client.

        Args:
            timeout: Request timeout in seconds. None disables timeout.
            http2: Whether to use HTTP/2 (default False for API stability).
            headers: Default headers to include in all requests.
            max_connections: Maximum number of connections in the pool.
            max_keepalive_connections: Maximum keepalive connections.
            proxy: Optional proxy URL (e.g., "http://localhost:8080").
        """
        self._timeout = httpx.Timeout(timeout) if timeout is not None else None
        self._http2 = http2
        self._headers = dict(headers) if headers else {}
        self._max_connections = max_connections
        self._max_keepalive_connections = max_keepalive_connections
        self._proxy = proxy
        self._client: httpx.AsyncClient | None = None

    def _build_client(self) -> httpx.AsyncClient:
        """Build the httpx AsyncClient with configured options."""
        limits = httpx.Limits(
            max_connections=self._max_connections,
            max_keepalive_connections=self._max_keepalive_connections,
        )

        return httpx.AsyncClient(
            http2=self._http2,
            timeout=self._timeout,
            headers=self._headers,
            limits=limits,
            proxy=self._proxy,
        )

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily initialize the client if not already created."""
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def __aenter__(self) -> HttpxClientAdapter:
        """Enter async context manager."""
        self._client = self._build_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context manager and close the client."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Perform an HTTP GET request and return parsed JSON or text.

        Args:
            url: The URL to request.
            params: Optional query parameters.
            headers: Optional headers to include (merged with default headers).

        Returns:
            Parsed JSON response or text content.

        Raises:
            httpx.TimeoutException: If the request times out.
            httpx.HTTPStatusError: If the response has an error status code.
        """
        client = await self._ensure_client()
        response = await client.get(
            url,
            params=dict(params) if params else None,
            headers=dict(headers) if headers else None,
        )
        response.raise_for_status()
        return self._maybe_json(response)

    async def post(
        self,
        url: str,
        *,
        data: Any | None = None,
        json: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Perform an HTTP POST request and return parsed JSON or text.

        Args:
            url: The URL to request.
            data: Optional form data to send.
            json: Optional JSON data to send.
            headers: Optional headers to include (merged with default headers).

        Returns:
            Parsed JSON response or text content.

        Raises:
            httpx.TimeoutException: If the request times out.
            httpx.HTTPStatusError: If the response has an error status code.
        """
        client = await self._ensure_client()
        response = await client.post(
            url,
            data=data,
            json=json,
            headers=dict(headers) if headers else None,
        )
        response.raise_for_status()
        return self._maybe_json(response)

    @staticmethod
    def _maybe_json(response: httpx.Response) -> Any:
        """Parse response as JSON if content type indicates JSON, else return text.

        Uses orjson for 3-5x faster parsing compared to stdlib json.
        This is critical for large API responses (megabytes of transactions)
        to avoid blocking the event loop.
        """
        content_type = response.headers.get('content-type', '')
        if 'application/json' in content_type:
            # Use orjson for ultra-fast JSON parsing
            # response.content returns bytes, which orjson handles directly
            return orjson.loads(response.content)
        return response.text
