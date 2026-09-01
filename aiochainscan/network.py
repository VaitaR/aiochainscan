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

import asyncio
import logging
import re
import urllib.parse
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx
import orjson

from aiochainscan.constants import (
    NETWORK_DEFAULT_TIMEOUT,
    NETWORK_ERROR_EXCERPT_BYTES,
    NETWORK_MAX_CONNECTIONS,
    NETWORK_MAX_RESPONSE_BYTES,
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
    ChainscanResponseTooLargeError,
)
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy

# Sensitive headers that should be redacted in logs
SENSITIVE_HEADERS = {
    'authorization',
    'cookie',
    'proxy-authorization',
    'x-api-key',
    'x-apikey',
    'apikey',
    'api-key',
    'token',
    'x-token',
    'access-token',
    'x-access-token',
    'auth-token',
    'x-auth-token',
}
SENSITIVE_QUERY_PARAMS = {
    'apikey',
    'api_key',
    'api-key',
    'key',
    'token',
    'access_token',
    'access-token',
    'auth_token',
    'auth-token',
    'authorization',
    'auth',
    'access_key',
    'client_secret',
    'password',
    'secret',
}
_NORMALIZED_SENSITIVE_QUERY_PARAMS = {param.replace('-', '_') for param in SENSITIVE_QUERY_PARAMS}


def _is_sensitive_header(name: str) -> bool:
    normalized = name.lower()
    compact = normalized.replace('-', '').replace('_', '')
    return (
        normalized in SENSITIVE_HEADERS
        or 'authorization' in normalized
        or 'apikey' in compact
        or 'token' in compact
    )


def _is_sensitive_query_name(name: str) -> bool:
    normalized = name.lower().replace('-', '_')
    return (
        normalized in _NORMALIZED_SENSITIVE_QUERY_PARAMS
        or normalized.endswith('_key')
        or normalized.endswith('_token')
    )


# Key-shaped path segments (e.g. NodeReal rides the API key in the URL path:
# /v1/{key}, open-platform.nodereal.io/{key}/bsc-mainnet/...). Exactly 32 hex
# chars so real path resources (0x-prefixed tx hashes, 40-char addresses)
# never match.
SENSITIVE_PATH_SEGMENT = re.compile(r'(?<=/)[0-9a-fA-F]{32}(?=/|$)')


def _redact_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    """Redact sensitive headers for safe logging."""
    if headers is None:
        return None
    return {k: ('***REDACTED***' if _is_sensitive_header(k) else v) for k, v in headers.items()}


def _redact_url(url: str | httpx.URL) -> str:
    """Redact sensitive query parameters and key-shaped path segments for logging."""
    parsed = urllib.parse.urlparse(str(url))
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)

    redacted_pairs = [
        (k, '***REDACTED***' if _is_sensitive_query_name(k) else v) for k, v in query_pairs
    ]
    redacted_query = urllib.parse.urlencode(redacted_pairs, doseq=True)
    redacted_path = SENSITIVE_PATH_SEGMENT.sub('***REDACTED***', parsed.path)
    netloc = parsed.netloc
    if '@' in netloc:
        netloc = f'***REDACTED***@{netloc.rsplit("@", 1)[1]}'
    return urllib.parse.urlunparse(
        parsed._replace(netloc=netloc, path=redacted_path, query=redacted_query)
    )


def _redact_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Redact sensitive values in request payload/query dictionaries."""
    if payload is None:
        return None

    def redact_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: ('***REDACTED***' if _is_sensitive_query_name(k) else redact_value(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [redact_value(item) for item in value]
        return value

    return cast(dict[str, Any], redact_value(payload))


def _excerpt(value: Any, limit: int = NETWORK_ERROR_EXCERPT_BYTES) -> Any:
    """Return a bounded representation suitable for an exception message."""
    if isinstance(value, str):
        return value if len(value) <= limit else f'{value[:limit]}... [truncated]'
    if isinstance(value, bytes):
        return value[:limit].decode('utf-8', errors='replace')
    if isinstance(value, dict | list):
        return f'<{type(value).__name__} with {len(value)} items>'
    return value


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
        max_response_bytes: int = NETWORK_MAX_RESPONSE_BYTES,
        first_request_guard: Callable[[], Awaitable[None]] | None = None,
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
            max_response_bytes: Maximum buffered response size (default 64 MiB).
            first_request_guard: Optional async hook executed once, before the
                first admitted request (outside the retry policy). Used for
                fail-fast configuration checks such as expected-chain-id
                validation. The guard may itself issue requests through this
                Network (re-entrancy is detected and allowed); a guard error
                is remembered and re-raised for every subsequent request.
        """
        if max_response_bytes <= 0:
            raise ValueError('max_response_bytes must be greater than zero')

        self._url_builder = url_builder
        self._timeout = self._prepare_timeout(timeout)
        self._proxy = proxy
        self._http2 = http2
        self._max_connections = (
            max_connections if max_connections is not None else NETWORK_MAX_CONNECTIONS
        )
        self._max_response_bytes = max_response_bytes

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
        self._state_lock = asyncio.Lock()
        self._active_requests = 0
        self._active_requests_zero = asyncio.Event()
        self._active_requests_zero.set()
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None

        # First-request guard (fail-fast config checks). Uses its own lock so
        # the guard can issue requests through this same Network without
        # deadlocking on _state_lock.
        self._first_request_guard = first_request_guard
        self._guard_lock = asyncio.Lock()
        self._guard_done = False
        self._guard_error: BaseException | None = None
        self._guard_owner: asyncio.Task[None] | None = None

    async def _run_first_request_guard(self) -> None:
        """Run the first-request guard exactly once (see ``__init__`` docs).

        Concurrency: waiters block until the guard completes, then either
        proceed or re-raise the remembered guard error. Re-entrancy: requests
        made by the guard itself (same task) skip the hook so the probe can
        reach the transport.
        """
        if self._first_request_guard is None:
            return
        if self._guard_done:
            if self._guard_error is not None:
                raise self._guard_error
            return
        if self._guard_owner is asyncio.current_task():
            return  # the guard itself is issuing this request

        async with self._guard_lock:
            if self._guard_done:
                if self._guard_error is not None:
                    raise self._guard_error
                return
            if self._guard_owner is asyncio.current_task():
                return
            self._guard_owner = asyncio.current_task()
            try:
                await self._first_request_guard()
            except BaseException as e:
                self._guard_error = e
                raise
            finally:
                self._guard_owner = None
                self._guard_done = True

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
        async with self._state_lock:
            self._raise_if_closed()
            return self._get_or_create_client()

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        async with self._state_lock:
            if not self._closed:
                self._closed = True
                self._close_task = asyncio.create_task(self._finish_close(self._client))
            close_task = self._close_task

        if close_task is not None:
            # A cancelled waiter must not cancel the shared cleanup task.
            await asyncio.shield(close_task)

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise ChainscanClientError('Network is closed')

    def _get_or_create_client(self) -> httpx.AsyncClient:
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

    async def _start_request(self) -> httpx.AsyncClient:
        """Admit one request and account for it atomically with client access."""
        async with self._state_lock:
            self._raise_if_closed()
            client = self._get_or_create_client()
            self._active_requests += 1
            self._active_requests_zero.clear()
            return client

    async def _finish_request(self) -> None:
        async with self._state_lock:
            self._active_requests -= 1
            if self._active_requests == 0:
                self._active_requests_zero.set()

    async def _finish_close(self, client: httpx.AsyncClient | None) -> None:
        await self._active_requests_zero.wait()
        if client is not None:
            await client.aclose()
        async with self._state_lock:
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
        # Fail-fast config checks (e.g. expected chain validation) run before
        # the retry policy so a validation error is never retried.
        await self._run_first_request_guard()

        async def do_request() -> dict[str, Any] | list[Any] | str:
            # Acquire rate limit token before making request
            await self._rate_limiter.acquire('network:request')

            client = await self._start_request()
            try:
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
            finally:
                await self._finish_request()

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
        # Fail-fast config checks (e.g. expected chain validation) run before
        # the retry policy so a validation error is never retried.
        await self._run_first_request_guard()

        async def do_request() -> dict[str, Any] | list[Any] | str:
            # Acquire rate limit token before making request
            await self._rate_limiter.acquire('network:request')

            client = await self._start_request()
            try:
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
            finally:
                await self._finish_request()

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

        content = response.content
        content_size = len(content)
        if content_size > self._max_response_bytes:
            raise ChainscanResponseTooLargeError(content_size, self._max_response_bytes)

        # Classify HTTP-level errors directly. Calling response.raise_for_status()
        # would create an httpx.HTTPStatusError containing the original request,
        # which can retain credentials in the exception chain.
        if status_code >= 400:
            if status_code == 429:
                raise ChainscanRateLimitError('HTTP 429', 'Too Many Requests')
            safe_url = _redact_url(response.url)
            if 500 <= status_code <= 599:
                raise ChainscanNetworkError(
                    f'HTTP {status_code} for {safe_url}: {response.reason_phrase}',
                    retryable=True,
                )
            raise ChainscanClientError(
                f'HTTP {status_code} for {safe_url}: {response.reason_phrase}'
            )

        # Parse JSON response
        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            raise ChainscanClientContentTypeError(status_code, _excerpt(content))

        try:
            # Use orjson for 3-5x faster parsing compared to stdlib json
            # response.content returns bytes, which orjson handles directly
            response_json = orjson.loads(content)
        except orjson.JSONDecodeError as e:
            raise ChainscanClientContentTypeError(status_code, _excerpt(content)) from e

        self._logger.debug('Response parsed as %s', type(response_json).__name__)

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
    def _raise_if_error(response_json: Any) -> None:
        """Check response for API errors and raise appropriate exceptions."""
        if not isinstance(response_json, dict):
            return

        status = response_json.get('status')
        if status not in (None, '1', 1, 'OK', 'ok', 'Success', 'success'):
            message = _excerpt(response_json.get('message'))
            result = _excerpt(response_json.get('result'))

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
            if isinstance(err, dict):
                code, message = err.get('code'), _excerpt(err.get('message'))
            else:
                code, message = None, _excerpt(err)
            raise ChainscanClientProxyError(code, message)
