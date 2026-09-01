"""Network transport layer using httpx, tenacity, and aiolimiter.

This module provides the Network class for making HTTP requests to blockchain
explorer APIs with automatic rate limiting and retry functionality.

v0.4.0: Migrated from aiohttp/aiohttp-retry/asyncio-throttle to httpx/tenacity/aiolimiter
for cleaner retry semantics and token-bucket rate limiting.

v0.4.1: Disabled HTTP/2 by default and added comprehensive retry exceptions.
HTTP/2 multiplexing triggers Cloudflare WAF blocks on rate-limited APIs (Etherscan,
BlockScout). Added httpx.NetworkError and httpx.RemoteProtocolError to retry on
connection resets and protocol errors.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import TYPE_CHECKING, Any, cast

import httpx
import orjson

from aiochainscan.constants import (
    NETWORK_DEFAULT_TIMEOUT,
    NETWORK_MAX_CONNECTIONS,
    RATE_DEFAULT_BURST,
    RATE_DEFAULT_RPS,
    RATE_TIME_PERIOD,
    RETRY_MAX_ATTEMPTS,
    RETRY_MAX_WAIT,
    RETRY_MIN_WAIT,
)
from aiochainscan.core.url_builder import UrlBuilder
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
)
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy

if TYPE_CHECKING:
    pass

# Sensitive headers that should be redacted in logs
SENSITIVE_HEADERS = {'authorization', 'x-api-key', 'apikey'}
SENSITIVE_QUERY_PARAMS = {'apikey', 'api_key', 'key'}

# Key-shaped path segments (e.g. NodeReal rides the API key in the URL path:
# /v1/{key}, open-platform.nodereal.io/{key}/bsc-mainnet/...). Exactly 32 hex
# chars so real path resources (0x-prefixed tx hashes, 40-char addresses)
# never match.
SENSITIVE_PATH_SEGMENT = re.compile(r'(?<=/)[0-9a-fA-F]{32}(?=/|$)')


def _redact_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    """Redact sensitive headers for safe logging."""
    if headers is None:
        return None
    return {
        k: ('***REDACTED***' if k.lower() in SENSITIVE_HEADERS else v) for k, v in headers.items()
    }


def _redact_url(url: str | httpx.URL) -> str:
    """Redact sensitive query parameters and key-shaped path segments for logging."""
    parsed = urllib.parse.urlparse(str(url))
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)

    redacted_pairs = [
        (k, '***REDACTED***' if k.lower() in SENSITIVE_QUERY_PARAMS else v) for k, v in query_pairs
    ]
    redacted_query = urllib.parse.urlencode(redacted_pairs, doseq=True)
    redacted_path = SENSITIVE_PATH_SEGMENT.sub('***REDACTED***', parsed.path)
    return urllib.parse.urlunparse(parsed._replace(path=redacted_path, query=redacted_query))


def _redact_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Redact sensitive values in request payload/query dictionaries."""
    if payload is None:
        return None
    return {
        k: ('***REDACTED***' if k.lower() in SENSITIVE_QUERY_PARAMS else v)
        for k, v in payload.items()
    }


class Network:
    """HTTP transport layer for blockchain explorer APIs.

    Uses modern async libraries:
    - httpx for HTTP/1.1 connection pooling (HTTP/2 disabled by default)
    - tenacity for flexible retry logic (including business-logic errors)
    - aiolimiter for token-bucket rate limiting

    Note: HTTP/2 is disabled by default because rate-limited APIs behind
    Cloudflare (Etherscan, BlockScout) interpret HTTP/2 multiplexed streams
    as Layer 7 DDoS attacks, resulting in GOAWAY/RST_STREAM instead of HTTP 429.

    The public interface (get, post, close) remains unchanged from previous versions.
    """

    def __init__(
        self,
        url_builder: UrlBuilder,
        timeout: float | httpx.Timeout | None = None,
        proxy: str | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
        http2: bool = False,
        max_connections: int | None = None,
    ) -> None:
        """Initialize Network transport.

        Args:
            url_builder: URL builder for the target API.
            timeout: Request timeout in seconds, or httpx.Timeout instance.
            proxy: Optional proxy URL (e.g., "http://localhost:8080").
            rate_limiter: Rate limiter implementation (default: AioLimiterAdapter).
            retry_policy: Retry policy implementation (default: TenacityRetryAdapter).
            http2: Whether to use HTTP/2 (default False for API stability).
            max_connections: Maximum connections in the pool (default 10).
        """
        self._url_builder = url_builder
        self._timeout = self._prepare_timeout(timeout)
        self._proxy = proxy
        self._http2 = http2
        self._max_connections = (
            max_connections if max_connections is not None else NETWORK_MAX_CONNECTIONS
        )

        # Rate limiting with token bucket algorithm (default: 5 req/s, burst=1)
        # Lazy import to avoid circular dependency and support DI
        # max_burst=1 prevents burst requests that trigger Cloudflare WAF/DDoS
        if rate_limiter is not None:
            self._rate_limiter: RateLimiter = rate_limiter
        else:
            from aiochainscan.adapters.aiolimiter_adapter import AioLimiterAdapter

            self._rate_limiter = AioLimiterAdapter(
                max_rate=RATE_DEFAULT_RPS,
                time_period=RATE_TIME_PERIOD,
                max_burst=RATE_DEFAULT_BURST,
            )

        # Retry policy with exponential backoff (retries on rate limit and network errors)
        # NetworkError covers ConnectError, ReadError, WriteError, CloseError
        # RemoteProtocolError covers HTTP/2 protocol errors (GOAWAY, RST_STREAM)
        # ChainscanNetworkError is our domain exception for retryable network errors
        if retry_policy is not None:
            self._retry_policy: RetryPolicy = retry_policy
        else:
            from aiochainscan.adapters.tenacity_retry import TenacityRetryAdapter

            self._retry_policy = TenacityRetryAdapter(
                max_attempts=RETRY_MAX_ATTEMPTS,
                min_wait=RETRY_MIN_WAIT,
                max_wait=RETRY_MAX_WAIT,
                retry_exceptions=(
                    ChainscanRateLimitError,
                    ChainscanNetworkError,
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    httpx.RemoteProtocolError,
                ),
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
            return httpx.Timeout(NETWORK_DEFAULT_TIMEOUT)

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

    async def request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any] | str:
        """Perform HTTP request to custom URL with rate limiting and retries.

        This method allows scanners to make requests to custom URLs while
        still benefiting from connection pooling, rate limiting, and retry logic.

        Args:
            method: HTTP method ('GET', 'POST', etc.)
            url: Full URL to request (not using url_builder.API_URL)
            params: Query parameters (for GET)
            data: Form data (for POST with form encoding)
            json_data: JSON data (for POST with JSON encoding)
            headers: Request headers

        Returns:
            Parsed response data (JSON decoded).
        """

        async def do_request() -> dict[str, Any] | list[Any] | str:
            # Acquire rate limit token before making request
            await self._rate_limiter.acquire('network:request')

            client = await self._ensure_client()

            if method == 'GET':
                response = await client.get(url, params=params, headers=headers)
            elif method == 'POST':
                if json_data is not None:
                    response = await client.post(url, json=json_data, headers=headers)
                else:
                    response = await client.post(url, data=data, headers=headers)
            else:
                raise ValueError(f'Unsupported HTTP method: {method}')

            self._logger.debug(
                '[%s %s] url=%r params=%r headers=%r',
                method,
                response.status_code,
                _redact_url(response.url),
                _redact_payload(params),
                _redact_headers(headers),
            )

            return self._handle_response(response)

        # Use retry policy to handle transient errors
        return await self._retry_policy.run(do_request)

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
            await self._rate_limiter.acquire('network:request')

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
                _redact_url(response.url),
                _redact_payload(data),
                _redact_headers(headers),
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
            safe_url = _redact_url(response.url)
            if 500 <= status_code <= 599:
                raise ChainscanNetworkError(
                    f'HTTP {status_code} for {safe_url}: {response.reason_phrase}',
                    retryable=True,
                ) from e
            raise ChainscanClientError(
                f'HTTP {status_code} for {safe_url}: {response.reason_phrase}'
            ) from e

        # Parse JSON response
        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            raise ChainscanClientContentTypeError(status_code, response.text)

        try:
            # Use orjson for 3-5x faster parsing compared to stdlib json
            # response.content returns bytes, which orjson handles directly
            response_json = orjson.loads(response.content)
        except orjson.JSONDecodeError as e:
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
