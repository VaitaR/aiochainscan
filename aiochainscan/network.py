"""Network transport layer using httpx, tenacity, and aiolimiter.

This module provides the Network class for making HTTP requests to blockchain
explorer APIs with automatic rate limiting and retry functionality.

v0.4.0: Migrated from aiohttp/aiohttp-retry/asyncio-throttle to httpx/tenacity/aiolimiter
for better HTTP/2 support, cleaner retry semantics, and token-bucket rate limiting.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from aiochainscan.adapters.aiolimiter_adapter import AioLimiterAdapter
from aiochainscan.adapters.tenacity_retry import TenacityRetryAdapter
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanRateLimitError,
)
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.url_builder import UrlBuilder


class Network:
    """HTTP transport layer for blockchain explorer APIs.

    Uses modern async libraries:
    - httpx for HTTP/2 support and connection pooling
    - tenacity for flexible retry logic (including business-logic errors)
    - aiolimiter for token-bucket rate limiting

    The public interface (get, post, close) remains unchanged from previous versions.
    """

    def __init__(
        self,
        url_builder: UrlBuilder,
        timeout: float | httpx.Timeout | None = 10.0,
        proxy: str | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
        http2: bool = True,
        max_connections: int = 100,
    ) -> None:
        """Initialize Network transport.

        Args:
            url_builder: URL builder for the target API.
            timeout: Request timeout in seconds, or httpx.Timeout instance.
            proxy: Optional proxy URL (e.g., "http://localhost:8080").
            rate_limiter: Rate limiter implementation (default: AioLimiterAdapter).
            retry_policy: Retry policy implementation (default: TenacityRetryAdapter).
            http2: Whether to use HTTP/2 (default True).
            max_connections: Maximum connections in the pool (default 100).
        """
        self._url_builder = url_builder
        self._timeout = self._prepare_timeout(timeout)
        self._proxy = proxy
        self._http2 = http2
        self._max_connections = max_connections

        # Rate limiting with token bucket algorithm (default: 5 req/s)
        self._rate_limiter: RateLimiter = rate_limiter or AioLimiterAdapter(
            max_rate=5.0, time_period=1.0
        )

        # Retry policy with exponential backoff (retries on rate limit errors)
        self._retry_policy: RetryPolicy = retry_policy or TenacityRetryAdapter(
            max_attempts=5,
            min_wait=1.0,
            max_wait=30.0,
            retry_exceptions=(ChainscanRateLimitError, httpx.TimeoutException),
        )

        self._client: httpx.AsyncClient | None = None
        self._logger = logging.getLogger(__name__)

    def _prepare_timeout(self, timeout: float | httpx.Timeout | None) -> httpx.Timeout:
        """Convert timeout parameter to httpx.Timeout."""
        if isinstance(timeout, httpx.Timeout):
            return timeout
        elif isinstance(timeout, int | float):
            return httpx.Timeout(float(timeout))
        else:
            return httpx.Timeout(10.0)  # Default timeout

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily initialize the httpx client."""
        if self._client is None:
            limits = httpx.Limits(
                max_connections=self._max_connections,
                max_keepalive_connections=self._max_connections // 5,
            )
            self._client = httpx.AsyncClient(
                http2=self._http2,
                timeout=self._timeout,
                limits=limits,
                proxy=self._proxy,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(
        self, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any] | list[Any] | str:
        """Perform GET request with rate limiting and retries.

        Args:
            params: Query parameters.
            headers: Request headers.

        Returns:
            Parsed response data (result or data field from JSON).
        """
        params, headers = self._url_builder.filter_and_sign(params, headers)
        return await self._request('GET', params=params, headers=headers)

    async def post(
        self, data: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any] | list[Any] | str:
        """Perform POST request with rate limiting and retries.

        Args:
            data: Form data to send.
            headers: Request headers.

        Returns:
            Parsed response data (result or data field from JSON).
        """
        data, headers = self._url_builder.filter_and_sign(data, headers)
        return await self._request('POST', data=data, headers=headers)

    async def _request(
        self,
        method: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any] | str:
        """Execute HTTP request with rate limiting and retry logic."""

        async def do_request() -> dict[str, Any] | list[Any] | str:
            # Acquire rate limit token before making request
            await self._rate_limiter.acquire()

            client = await self._ensure_client()

            if method == 'GET':
                response = await client.get(
                    self._url_builder.API_URL,
                    params=params,
                    headers=headers,
                )
            else:  # POST
                response = await client.post(
                    self._url_builder.API_URL,
                    data=data,
                    headers=headers,
                )

            self._logger.debug(
                '[%s %s] url=%r data=%r headers=%r',
                method,
                response.status_code,
                str(response.url),
                data,
                headers,
            )

            return self._handle_response(response)

        # Use retry policy to handle transient errors
        return await self._retry_policy.run(do_request)

    def _handle_response(self, response: httpx.Response) -> dict[str, Any] | list[Any] | str:
        """Process HTTP response and extract payload.

        Args:
            response: httpx Response object.

        Returns:
            Parsed response data.

        Raises:
            ChainscanClientContentTypeError: If response is not JSON.
            ChainscanClientApiError: If API returns an error status.
            ChainscanRateLimitError: If rate limit is exceeded.
            ChainscanClientProxyError: If proxy error is returned.
        """
        status_code = response.status_code

        # Check for HTTP-level errors (4xx, 5xx)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Convert to our exception types for consistent handling
            if status_code == 429:
                raise ChainscanRateLimitError('HTTP 429', 'Too Many Requests') from e
            raise ChainscanClientError(str(e)) from e

        # Parse JSON response
        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            raise ChainscanClientContentTypeError(status_code, response.text)

        try:
            response_json = response.json()
        except Exception as e:
            raise ChainscanClientContentTypeError(status_code, response.text) from e

        self._logger.debug('Response: %r', str(response_json)[0:200])

        # Check for API-level errors
        self._raise_if_error(response_json)

        # Extract payload from response
        payload: Any
        if isinstance(response_json, dict):
            if 'result' in response_json:
                payload = response_json['result']
            elif 'data' in response_json:
                payload = response_json['data']
            else:
                payload = response_json
        else:
            payload = response_json

        return cast(dict[str, Any] | list[Any] | str, payload)

    @staticmethod
    def _raise_if_error(response_json: dict[str, Any]) -> None:
        """Check response for API errors and raise appropriate exceptions."""
        status = response_json.get('status') if isinstance(response_json, dict) else None
        if status not in (None, '1', 1, 'OK', 'ok', 'Success', 'success'):
            message = response_json.get('message') if isinstance(response_json, dict) else None
            result = response_json.get('result') if isinstance(response_json, dict) else None

            # Detect hidden rate limit errors (HTTP 200 with rate limit message)
            # Etherscan returns: {"status":"0","message":"NOTOK","result":"Max rate limit reached"}
            if isinstance(result, str) and (
                'rate limit' in result.lower()
                or 'limit reached' in result.lower()
                or 'too many requests' in result.lower()
            ):
                raise ChainscanRateLimitError(message, result)

            raise ChainscanClientApiError(message, result)

        if 'error' in response_json:
            err = response_json['error']
            code, message = err.get('code'), err.get('message')
            raise ChainscanClientProxyError(code, message)
