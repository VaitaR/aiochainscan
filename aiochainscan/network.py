"""Network transport layer using httpx, tenacity, and aiolimiter.

This module provides the Network class for making HTTP requests to blockchain
explorer APIs with automatic rate limiting and retry functionality.

v0.4.0: Migrated from aiohttp/aiohttp-retry/asyncio-throttle to httpx/tenacity/aiolimiter
for cleaner retry semantics and token-bucket rate limiting.

v0.4.1: Disabled HTTP/2 by default and added comprehensive retry exceptions.
HTTP/2 multiplexing triggers Cloudflare WAF blocks on rate-limited APIs (Etherscan,
BlockScout). Added httpx.NetworkError and httpx.RemoteProtocolError to retry on
connection resets and protocol errors.

Every request — UrlBuilder endpoint or custom URL — is admitted through ONE
path (:meth:`Network._send`): guard → rate-limit acquire → start → dispatch →
debug-log → handle → finish, wrapped by the retry policy. Transient failures
share one vocabulary, ``aiochainscan.exceptions.TRANSIENT_EXCEPTIONS``; the
response-envelope dialects live behind the ``ResponseDialect`` seam below.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol, cast

import httpx
import orjson

from aiochainscan._redaction import (
    SENSITIVE_HEADERS as SENSITIVE_HEADERS,
)
from aiochainscan._redaction import (
    SENSITIVE_PATH_SEGMENT as SENSITIVE_PATH_SEGMENT,
)
from aiochainscan._redaction import (
    SENSITIVE_QUERY_PARAMS as SENSITIVE_QUERY_PARAMS,
)
from aiochainscan._redaction import (
    _redact_headers as _redact_headers,
)
from aiochainscan._redaction import (
    _redact_payload as _redact_payload,
)
from aiochainscan._redaction import (
    _redact_url as _redact_url,
)
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
    TRANSIENT_EXCEPTIONS,
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
    ChainscanResponseTooLargeError,
    FailureKind,
    api_error_failure_kind,
)
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy


def _excerpt(value: Any, limit: int = NETWORK_ERROR_EXCERPT_BYTES) -> Any:
    """Return a bounded representation suitable for an exception message."""
    if isinstance(value, str):
        return value if len(value) <= limit else f'{value[:limit]}... [truncated]'
    if isinstance(value, bytes):
        return value[:limit].decode('utf-8', errors='replace')
    if isinstance(value, dict | list):
        return f'<{type(value).__name__} with {len(value)} items>'
    return value


class ResponseDialect(Protocol):
    """Internal transport seam: one provider response-envelope dialect.

    A dialect knows (a) how to detect an error in a parsed JSON payload and
    raise the matching transport exception and (b) how to extract the
    caller-facing payload from a success envelope. Adapters are stateless;
    the transport composes them per request path (see
    :class:`CompositeResponseDialect`).
    """

    def raise_if_error(self, response_json: Any) -> None:
        """Raise the dialect's transport error if the payload is an error envelope."""
        ...

    def extract(self, response_json: Any) -> Any:
        """Extract the caller-facing payload from a success envelope."""
        ...


# Etherscan-compat explorers answer an empty result set with a FAILING status
# ("No transactions found", "No logs found", "No records found") and a
# ``result`` that is still the empty list. That is a complete, correct answer
# to a query that matched nothing — not an error — so it must reach the caller
# as ``[]``.
_EMPTY_RESULT_MESSAGE = re.compile(r'^\s*no\b.*\bfound\b[.\s]*$', re.IGNORECASE)

_RATE_LIMIT_MARKERS = ('rate limit', 'limit reached', 'too many requests')


def _parse_retry_after(header: str | None) -> int | None:
    """Seconds advertised by an RFC 9110 ``Retry-After`` header, if any.

    Both spellings are accepted — delta-seconds and an HTTP-date — because
    both are served in practice. ``None`` for an absent, unparsable or past
    value leaves :class:`ChainscanRateLimitError` on its own default, which
    is what the provider pool then uses to size the cooldown.
    """
    if not header:
        return None
    raw = header.strip()
    try:
        return max(0, int(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delta = (when - datetime.now(UTC)).total_seconds()
    return int(delta) if delta > 0 else None


def _mentions_rate_limit(text: Any) -> bool:
    return isinstance(text, str) and any(marker in text.lower() for marker in _RATE_LIMIT_MARKERS)


def _is_empty_result_envelope(message: Any, raw_result: Any) -> bool:
    """Whether a failing Etherscan envelope is really an empty result set.

    Both halves are required: the "no ... found" message AND a list-shaped
    ``result``. A genuine error carries its detail as a string, so a string
    ``result`` never qualifies however the message reads.
    """
    return (
        isinstance(raw_result, list)
        and isinstance(message, str)
        and _EMPTY_RESULT_MESSAGE.match(message) is not None
    )


def _raise_if_etherscan_error(response_json: Any) -> None:
    """Etherscan status-envelope check (``{"status", "message", "result"}``).

    ``status`` outside the success set raises, EXCEPT for the empty result
    set (see :func:`_is_empty_result_envelope`), which is a success answering
    ``[]``.

    Rate-limit TEXT inside an HTTP 200 becomes
    :class:`ChainscanRateLimitError` (its class default carries
    ``FailureKind.RATE_LIMIT``, so the raise site needs no explicit kind).
    The text rides in ``result`` or in ``message`` depending on the provider:

    ``{"status":"0","message":"NOTOK","result":"Max rate limit reached"}``
    ``{"status":"0","message":"Max calls rate limit reached","result":"NOTOK"}``

    Any other failing status raises :class:`ChainscanClientApiError` with
    the kind computed by :func:`aiochainscan.exceptions.api_error_failure_kind`
    — decided here, where the failure is detected, so the pool classifies
    by lookup instead of re-parsing the text.
    """
    if not isinstance(response_json, dict):
        return

    status = response_json.get('status')
    if status not in (None, '1', 1, 'OK', 'ok', 'Success', 'success'):
        raw_message = response_json.get('message')
        if _is_empty_result_envelope(raw_message, response_json.get('result')):
            return

        message = _excerpt(raw_message)
        result = _excerpt(response_json.get('result'))

        if _mentions_rate_limit(result) or _mentions_rate_limit(message):
            raise ChainscanRateLimitError(message, result)

        raise ChainscanClientApiError(
            message, result, failure_kind=api_error_failure_kind(message, result)
        )


def _raise_if_jsonrpc_error(response_json: Any) -> None:
    """JSON-RPC 2.0 error-object check (``{"jsonrpc", "id", "result"|"error"}``).

    A present-but-null ``error`` is not an error: several nodes emit both
    members and null the unused one, so the key's presence cannot be the
    signal — its value must be.
    """
    if not isinstance(response_json, dict):
        return
    err = response_json.get('error')
    if err is not None:
        if isinstance(err, dict):
            code, message = err.get('code'), _excerpt(err.get('message'))
        else:
            code, message = None, _excerpt(err)
        raise ChainscanClientProxyError(code, message)


def _extract_envelope_payload(response_json: Any) -> Any:
    """Unwrap the caller-facing payload: ``result`` first, then ``data``.

    Covers the Etherscan envelope, the JSON-RPC envelope (whose success
    member is ``result``) and envelope-less payloads (returned as-is, e.g.
    BlockScout V2 ``{"items": [...], "next_page_params": {...}}``).
    """
    if isinstance(response_json, dict):
        if 'result' in response_json:
            return response_json['result']
        if 'data' in response_json:
            return response_json['data']
        return response_json
    return response_json


class EtherscanEnvelope:
    """Etherscan-style envelope: ``status`` values, hidden rate-limit text."""

    def raise_if_error(self, response_json: Any) -> None:
        _raise_if_etherscan_error(response_json)

    def extract(self, response_json: Any) -> Any:
        return _extract_envelope_payload(response_json)


class JsonRpcEnvelope:
    """JSON-RPC 2.0 envelope: the ``error`` object becomes a proxy error."""

    def raise_if_error(self, response_json: Any) -> None:
        _raise_if_jsonrpc_error(response_json)

    def extract(self, response_json: Any) -> Any:
        return _extract_envelope_payload(response_json)


class CompositeResponseDialect:
    """Several dialects applied in order; extraction follows the last one.

    The transport default composes the Etherscan and JSON-RPC checks because
    every current request path serves both dialects: the custom-URL path
    (``request``) carries Etherscan-compat ``/api`` traffic AND JSON-RPC
    probes (BlockScout ``/api/eth-rpc``, NodeReal ``nr_*``), and the
    pre-seam transport applied both checks to every response. Composing the
    same checks in the same order keeps every path byte-identical to that
    behaviour; a dialect-only path can select a single adapter instead.
    """

    def __init__(self, *dialects: ResponseDialect) -> None:
        if not dialects:
            raise ValueError('CompositeResponseDialect needs at least one dialect')
        self._dialects = dialects

    def raise_if_error(self, response_json: Any) -> None:
        for dialect in self._dialects:
            dialect.raise_if_error(response_json)

    def extract(self, response_json: Any) -> Any:
        return self._dialects[-1].extract(response_json)


_ETHERSCAN_ENVELOPE = EtherscanEnvelope()
_JSONRPC_ENVELOPE = JsonRpcEnvelope()

# The dialect every current request path is served with (see
# :class:`CompositeResponseDialect` for why it is the composition).
_DEFAULT_DIALECT: ResponseDialect = CompositeResponseDialect(
    _ETHERSCAN_ENVELOPE,
    _JSONRPC_ENVELOPE,
)


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
                Network (re-entrancy is detected and allowed). A
                configuration error is remembered and re-raised for every
                subsequent request; a transient error (rate limit, network)
                leaves the guard armed so the next request re-probes instead
                of failing forever.
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
        # TRANSIENT_EXCEPTIONS is the one shared vocabulary — the first-request
        # guard below reads the same constant, so guard and retry cannot drift.
        if retry_policy is not None:
            self._retry_policy: RetryPolicy = retry_policy
        else:
            from aiochainscan.adapters.tenacity_retry import TenacityRetryAdapter

            self._retry_policy = TenacityRetryAdapter(
                max_attempts=RETRY_MAX_ATTEMPTS,
                min_wait=RETRY_MIN_WAIT,
                max_wait=RETRY_MAX_WAIT,
                retry_exceptions=TRANSIENT_EXCEPTIONS,
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

        Failure memory: only configuration errors (an ``Exception`` outside
        ``TRANSIENT_EXCEPTIONS``) are cached as fatal — every later
        request fails fast with the remembered error. Transient probe
        failures are re-raised but NOT remembered: the guard stays armed and
        the next request probes again, so one unlucky 429/DNS blip cannot
        brick the client for its whole lifetime. Neither is a bare
        ``BaseException``: cancelling the task that happened to run the probe
        (or Ctrl-C) says nothing about the configuration, and remembering it
        would re-raise one task's ``CancelledError`` into every later,
        unrelated request — marking their tasks cancelled for the client's
        whole lifetime.
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
                if isinstance(e, Exception) and not isinstance(e, TRANSIENT_EXCEPTIONS):
                    self._guard_error = e
                    self._guard_done = True
                # Transient failure or a bare BaseException (cancellation,
                # KeyboardInterrupt): nothing remembered — the guard re-runs
                # on the next request.
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
        dialect: ResponseDialect | None = None,
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
            dialect: Response-envelope handling for this request (default: the
                composite Etherscan + JSON-RPC dialect). A scanner whose
                provider overloads an envelope code passes its own adapter so
                the classification happens INSIDE the retry policy —
                translating after this method returns yields a "retryable"
                exception class the retried function never saw.

        Returns:
            Parsed response data (JSON decoded).
        """
        return await self._send(
            method=method,
            url=url,
            params=params,
            data=data,
            json_data=json_data,
            headers=headers,
            dialect=dialect if dialect is not None else _DEFAULT_DIALECT,
            log_format='[%s %s] url=%r params=%r headers=%r',
            log_payload=params,
        )

    async def _request(
        self,
        method: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any] | str:
        """Execute HTTP request with rate limiting and retry logic."""
        return await self._send(
            method=method,
            url=self._url_builder.API_URL,
            params=params,
            data=data,
            json_data=None,
            headers=headers,
            dialect=_DEFAULT_DIALECT,
            log_format='[%s %s] url=%r data=%r headers=%r',
            log_payload=data,
        )

    async def _send(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        data: dict[str, Any] | None,
        json_data: dict[str, Any] | None,
        headers: dict[str, str] | None,
        dialect: ResponseDialect,
        log_format: str,
        log_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | list[Any] | str:
        """The ONE admission path for every Network request.

        ``request`` (custom URLs) and ``_request`` (the UrlBuilder endpoint)
        are thin specializations over this method; the admission order —
        guard → rate-limit acquire → start → dispatch → debug-log → handle
        → finish, wrapped by the retry policy — is written exactly once,
        here. ``dialect`` selects the response-envelope handling per request
        path; ``log_format``/``log_payload`` preserve each entry point's
        debug-log shape ('params=' vs 'data=').
        """
        # An unsupported verb is the caller's bug, not a request outcome:
        # rejecting it here keeps it out of the retry policy and off the rate
        # limiter, which would otherwise spend a token per attempt on a
        # request that is never dispatched.
        if method not in ('GET', 'POST'):
            raise ValueError(f'Unsupported HTTP method: {method}')

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
                    log_format,
                    method,
                    response.status_code,
                    _redact_url(response.url),
                    _redact_payload(log_payload),
                    _redact_headers(headers),
                )

                return self._handle_response(response, dialect)
            finally:
                await self._finish_request()

        # Use retry policy to handle transient errors
        return await self._retry_policy.run(do_request)

    def _handle_response(
        self,
        response: httpx.Response,
        dialect: ResponseDialect = _DEFAULT_DIALECT,
    ) -> dict[str, Any] | list[Any] | str:
        """Process HTTP response and extract payload.

        Args:
            response: httpx Response object.
            dialect: Response-envelope handling (checks + payload extraction);
                defaults to the composite Etherscan + JSON-RPC dialect every
                request path is served with.

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
                retry_after = _parse_retry_after(response.headers.get('retry-after'))
                if retry_after is None:
                    raise ChainscanRateLimitError('HTTP 429', 'Too Many Requests')
                raise ChainscanRateLimitError('HTTP 429', 'Too Many Requests', retry_after)
            safe_url = _redact_url(response.url)
            if 500 <= status_code <= 599:
                raise ChainscanNetworkError(
                    f'HTTP {status_code} for {safe_url}: {response.reason_phrase}',
                    retryable=True,
                )
            if status_code in (401, 403):
                # Credential/authorization refusal at the HTTP layer: NodeReal
                # answers an invalid path key with 401; WAF/geo-blocks and
                # role-restricted proxies answer 403. In every observed flavour
                # the refusal is THIS provider's — the pool should fail over
                # and cool the provider (AUTH), not treat it as the caller's
                # problem. No repo provider signals plan restriction at the
                # HTTP layer (Etherscan rides 200-envelopes, NodeReal JSON-RPC
                # codes), so 403 is not split into PLAN_RESTRICTED.
                raise ChainscanClientError(
                    f'HTTP {status_code} for {safe_url}: {response.reason_phrase}',
                    failure_kind=FailureKind.AUTH,
                )
            raise ChainscanClientError(
                f'HTTP {status_code} for {safe_url}: {response.reason_phrase}'
            )

        # Parse JSON response. The gate matches any JSON media type, not the
        # exact ``application/json`` string: structured suffixes
        # (``application/vnd.api+json``) and ``text/json`` are JSON, and
        # rejecting them turns a parseable body into a content-type error.
        content_type = response.headers.get('content-type', '')
        if 'json' not in content_type.lower():
            raise ChainscanClientContentTypeError(status_code, _excerpt(content))

        try:
            # Use orjson for 3-5x faster parsing compared to stdlib json
            # response.content returns bytes, which orjson handles directly
            response_json = orjson.loads(content)
        except orjson.JSONDecodeError as e:
            raise ChainscanClientContentTypeError(status_code, _excerpt(content)) from e

        self._logger.debug('Response parsed as %s', type(response_json).__name__)

        # Check for API-level errors (per the selected envelope dialect) …
        dialect.raise_if_error(response_json)

        # … then extract the caller-facing payload.
        return cast(dict[str, Any] | list[Any] | str, dialect.extract(response_json))
