from __future__ import annotations

import re
from enum import Enum
from typing import Any

import httpx


class FailureKind(Enum):
    """What a provider failure means for pool routing.

    The single failure-classification vocabulary: exceptions carry their
    kind as a ``failure_kind`` attribute — a class-level default per
    exception class, overridable per raise site via the ``failure_kind``
    constructor keyword.
    :func:`aiochainscan.core.pool.classify_failure` returns a carried kind
    as-is, so the meaning of a failure is decided where the failure is
    detected (the transport detecting a rate limit inside HTTP 200, a
    scanner translating its provider's rejection) instead of being
    re-parsed from message text in core. A new scanner's failure mode
    becomes wireable by raising a kind-carrying exception — no core edits
    required.
    """

    RATE_LIMIT = 'rate_limit'
    """Provider is throttling us — cooldown honours ``retry_after``."""

    TRANSIENT = 'transient'
    """Network/5xx trouble that survived the client's transport retries."""

    AUTH = 'auth'
    """Missing or invalid API key — will not heal itself, long cooldown."""

    PLAN_RESTRICTED = 'plan_restricted'
    """The current API plan does not serve the chain/endpoint (e.g. Etherscan
    V2 free tier answering ``Free API Access is not supported for this chain``)."""

    METHOD_UNDECLARED = 'method_undeclared'
    """The provider never declared this method in its SPECS — capability
    routing, not a failure: no cooldown, no warning, just next provider."""

    FATAL = 'fatal'
    """Caller's problem (bad arguments, not-found, data contract) — switching
    providers cannot help; propagate immediately."""


class ChainscanClientError(Exception):
    """Base error type for aiochainscan client failures.

    Routing: every exception class declares a :attr:`failure_kind` default
    mirroring its historical classification in the pool's fallback ladder;
    raise sites that know better override it per instance via the
    ``failure_kind`` constructor keyword.
    """

    failure_kind: FailureKind | None = FailureKind.FATAL
    """Default routing classification for this exception class."""

    def __init__(self, *args: object, failure_kind: FailureKind | None = None) -> None:
        super().__init__(*args)
        if failure_kind is not None:
            self.failure_kind = failure_kind


class MethodNotDeclaredError(ValueError):
    """The scanner does not declare the requested method in its ``SPECS``.

    Subclasses :class:`ValueError`, preserving the historical contract of
    ``Scanner.call`` for undeclared methods, while giving the provider pool
    a precise type to classify: a provider without the method is *routed
    around* (failover to the next provider) instead of failing the call.
    Deliberately not a :class:`ChainscanClientError` — existing
    ``except ChainscanClientError`` handlers must not start catching
    capability errors.
    """

    failure_kind: FailureKind | None = FailureKind.METHOD_UNDECLARED


class BlockRangeNotSupportedError(MethodNotDeclaredError):
    """The scanner declares the method but not a block-range bound for it.

    Raised by the streaming/paginated client paths *before any request* when
    a BOUNDED block range (``from_block > 0`` or a concrete ``to_block``) is
    requested from a scanner whose ``EndpointSpec.param_map`` declares no
    block-range parameter for that method — the bounds would otherwise be
    silently dropped on the wire (BlockScout V2's address endpoints, for
    example, take no Etherscan-style block bounds). The remedy is an
    unbounded call (``from_block=0, to_block=None``) or a provider whose
    spec declares the range; the message names both.

    Subclasses :class:`MethodNotDeclaredError` (hence :class:`ValueError`)
    so the provider pool routes around this capability gap exactly as it
    does an undeclared method: silent failover, no cooldown.
    """


class AbiTypeNotSupportedError(ValueError):
    """The pure-Python ABI codec does not implement this Solidity type.

    Raised by :mod:`aiochainscan.abi_pure` instead of returning a wrong or
    empty value. The decode paths in :mod:`aiochainscan.decode` swallow
    ordinary decode failures (malformed calldata is expected in the wild) but
    let this one through: an unimplemented type is a gap in this library, not
    bad input, and silently reporting no decoded data would hide it.

    Subclasses :class:`ValueError`, matching what the codec's other rejections
    raise, so MCP argument validation keeps its historical contract.
    """

    def __init__(self, abi_type: str) -> None:
        self.abi_type = abi_type
        super().__init__(
            f'Unsupported ABI type {abi_type!r}. The pure-Python codec covers '
            'uintN/intN, address, bool, bytesN, bytes, string, arrays and '
            'tuples; install aiochainscan[fallback] or aiochainscan[fastabi] '
            'for wider coverage.'
        )


class InputLimitExceededError(ChainscanClientError):
    """A call would exceed a documented API input ceiling.

    Raised before any request when the caller supplies more items than the
    provider's documented maximum for a single call — e.g. Etherscan's
    ``getcontractcreation`` documents "Up to 5 contract addresses" and
    ``topholders`` documents "up to 1000" top holders. Refused locally
    instead of letting an oversized request reach the API, where it would
    answer with silent clamping/truncation or an opaque error envelope
    rather than a clear local exception.

    Positioned as a :class:`ChainscanClientError`, NOT the
    :class:`MethodNotDeclaredError` (``ValueError``) capability family —
    this is not a capability gap the provider pool should route around
    (every provider would refuse the same oversized input, so failing over
    cannot help). The placement also matters mechanically:
    ``scanners.base.translate_unexpected_errors`` — the ladder every
    ``Scanner.call`` applies exactly once — re-raises ``ChainscanClientError``
    unchanged on its first branch, before its catch-all masks anything else
    into a ``ChainscanNetworkError``. Landing outside that branch (e.g. as a
    bare ``ValueError``) would have this exception's identity and
    ``FailureKind`` erased into a masked, misclassified transient error.
    ``failure_kind`` is restated explicitly (it already equals
    :class:`ChainscanClientError`'s own default) so
    :func:`core.pool.classify_failure`'s "carried kind wins" rule always
    reads this as the caller's problem: propagate immediately, no cooldown,
    no failover. Same shape as :class:`PaginationDataLossError` /
    :class:`CompletenessUnavailableError` — both also
    :class:`ChainscanClientError` subclasses for "this call cannot be served
    as asked", not capability gaps.

    Attributes:
        what: Human-readable name of the limited input (e.g.
            ``'contract addresses'``).
        limit: The documented maximum.
        provided: The count actually supplied.
    """

    failure_kind: FailureKind | None = FailureKind.FATAL

    def __init__(self, what: str, limit: int, provided: int) -> None:
        self.what = what
        self.limit = limit
        self.provided = provided
        super().__init__(str(self))

    def __str__(self) -> str:
        return f'{self.what}: up to {self.limit} allowed per call, got {self.provided}'


class ScannerArgumentError(ChainscanClientError):
    """A scanner refused an argument before any request was sent.

    Raised by scanner-side input validation when the call as asked cannot be
    served by this provider — e.g. NodeReal's ``closest`` hint outside
    ``before``/``after``, more than one address for its one-per-call
    ``CONTRACT_CREATION``, a non-numeric timestamp, or a transfer filter
    without its required ``address``. Sibling of
    :class:`InputLimitExceededError`: that one means "more items than the
    provider documents per call"; this one means "this argument is invalid
    for this method on this scanner". Both are the caller's problem — every
    provider would refuse the same input, so the pool must propagate
    immediately: no failover, no cooldown.

    Raised from BOTH scanner seams (:meth:`Scanner.call` and
    ``fetch_page``) under one identity. Previously these validations raised
    a bare ``ValueError``, which the ``call()`` ladder masked into a
    TRANSIENT ``ChainscanNetworkError`` — a caller bug reading to the pool
    as a provider fault — while the ``fetch_page`` paths let it escape raw.

    Positioned as a :class:`ChainscanClientError` so
    ``scanners.base.translate_unexpected_errors`` re-raises it unchanged on
    its first branch, keeping the identity and ``FailureKind`` a bare
    ``ValueError`` would lose to the catch-all mask. ``failure_kind`` is
    restated explicitly (it already equals :class:`ChainscanClientError`'s
    own default) so :func:`core.pool.classify_failure`'s "carried kind wins"
    rule always reads it as the caller's problem.
    """

    failure_kind: FailureKind | None = FailureKind.FATAL


class ProviderPoolExhaustedError(ChainscanClientError):
    """Every provider in the pool failed (or is in cooldown) for a request.

    Attributes:
        operation: Description of the attempted operation (method or stream
            name) for which all providers were tried.
        attempts: Ordered ``(provider_label, exception)`` pairs — one per
            provider that was tried, in pool priority order. Providers
            skipped because of an active cooldown contribute the error that
            put them into cooldown, so the list always covers the whole pool
            when exhaustion is caused by failures.
    """

    def __init__(self, operation: str, attempts: list[tuple[str, Exception]]) -> None:
        self.operation = operation
        self.attempts = attempts
        summary = '; '.join(f'{label}: {type(exc).__name__}: {exc}' for label, exc in attempts)
        suffix = f': {summary}' if attempts else ''
        super().__init__(f'All {len(attempts)} providers failed for {operation!r}{suffix}')


class ChainscanProviderSwitchWarning(UserWarning):
    """Emitted when the provider pool routes away from a provider.

    Fired on failure-driven switches (rate limit, network errors, auth/plan
    rejections) and on providers skipped at construction time. Capability
    routing (a provider that never declared the method) is deterministic and
    therefore silent.
    """


class PureAbiDecodeWarning(UserWarning):
    """Emitted once per process when a bulk decode runs on the pure-Python floor.

    The pure floor is correct but roughly an order of magnitude slower than the
    Rust backend, and bulk callers are the only ones where that difference is
    large enough to be worth a message.
    """


class ChainscanDependencyError(ChainscanClientError):
    """An optional dependency required for the requested operation is missing.

    Raised when neither the fastabi Rust extension (bundled in all wheels)
    nor the pure-Python fallback packages are importable.
    """


class ChainscanClientContentTypeError(ChainscanClientError):
    def __init__(self, status: int, content: Any) -> None:
        self.status: int = status
        self.content: Any = content

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'[{self.status}] {self.content!r}'


class ChainscanResponseTooLargeError(ChainscanClientError):
    """Raised when a response exceeds the configured transport limit."""

    def __init__(self, actual_bytes: int, max_bytes: int) -> None:
        self.actual_bytes = actual_bytes
        self.max_bytes = max_bytes
        super().__init__(
            f'Response body is too large: {actual_bytes} bytes exceeds the {max_bytes}-byte limit'
        )


class ChainscanClientApiError(ChainscanClientError):
    """An explorer API answered an error envelope (``status != 1``)."""

    failure_kind: FailureKind | None = None
    """``None`` (the class default) means *not decided at the raise site*:
    classification falls back to the Etherscan-style text patterns in
    :func:`api_error_failure_kind` (this module). The Network transport
    passes the computed kind when raising, so exceptions that travelled
    through it classify without any text matching."""

    def __init__(
        self,
        message: str | None,
        result: Any,
        *,
        failure_kind: FailureKind | None = None,
    ) -> None:
        self.message: str | None = message
        self.result: Any = result
        if failure_kind is not None:
            self.failure_kind = failure_kind

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'[{self.message}] {self.result}'


# Etherscan-style API error texts (message+result) that mean "bad credential".
# Relocated from ``core/pool.py`` (via ``network.py``): the failure kind is
# decided where the failure is detected — at the raise site in the Network
# transport's Etherscan envelope adapter — and the pool's fallback ladder for
# kind-less ``ChainscanClientApiError`` instances calls the same helper, so
# raise-site and fallback classification can never drift.
_AUTH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'invalid api[- ]key', re.IGNORECASE),
    re.compile(r'missing[ /]+api[- ]key', re.IGNORECASE),
    re.compile(r'api[- ]key.{0,24}(invalid|missing|required)', re.IGNORECASE),
    re.compile(r'no api[- ]key', re.IGNORECASE),
)

# Error texts meaning "the plan does not cover this chain/endpoint".
_PLAN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'free api', re.IGNORECASE),
    re.compile(r'upgrade (?:your )?api plan', re.IGNORECASE),
    re.compile(r'api pro endpoint', re.IGNORECASE),
    re.compile(r'not supported for this chain', re.IGNORECASE),
)


def api_error_failure_kind(message: str | None, result: Any) -> FailureKind:
    """Classify an Etherscan-style API error envelope by its text.

    Used at the raise site in the Network transport's Etherscan envelope
    adapter so the exception carries its :class:`FailureKind` from the
    moment it is raised; the pool's classification fallback calls the same
    helper for ``ChainscanClientApiError`` instances constructed without an
    explicit kind.

    Args:
        message: The envelope's ``message`` field (``None`` tolerated).
        result: The envelope's ``result`` field (any type; non-strings
            simply contribute nothing matchable beyond their repr).

    Returns:
        :attr:`FailureKind.AUTH` for bad-credential texts,
        :attr:`FailureKind.PLAN_RESTRICTED` for plan-coverage texts,
        :attr:`FailureKind.FATAL` otherwise.
    """
    text = f'{message or ""} {result or ""}'
    if any(pattern.search(text) for pattern in _AUTH_PATTERNS):
        return FailureKind.AUTH
    if any(pattern.search(text) for pattern in _PLAN_PATTERNS):
        return FailureKind.PLAN_RESTRICTED
    return FailureKind.FATAL


class ChainscanClientProxyError(ChainscanClientError):
    """JSON-RPC 2.0 Specification

    https://www.jsonrpc.org/specification#error_object
    """

    failure_kind: FailureKind | None = FailureKind.FATAL

    def __init__(
        self,
        code: int | None,
        message: str | None,
        *,
        failure_kind: FailureKind | None = None,
    ) -> None:
        self.code: int | None = code
        self.message: str | None = message
        if failure_kind is not None:
            self.failure_kind = failure_kind

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'[{self.code}] {self.message}'


class ChainscanRateLimitError(ChainscanClientError):
    """Rate limit exceeded.

    Etherscan and similar APIs often return HTTP 200 with error message
    like {"status":"0","message":"NOTOK","result":"Max rate limit reached"}.
    This exception signals that the request should be retried after a delay.
    """

    failure_kind: FailureKind | None = FailureKind.RATE_LIMIT

    def __init__(
        self,
        message: str | None = None,
        result: Any = None,
        retry_after: int = 5,
        *,
        failure_kind: FailureKind | None = None,
    ) -> None:
        self.message: str | None = message
        self.result: Any = result
        self.retry_after = retry_after
        super().__init__(str(self), failure_kind=failure_kind)

    def __str__(self) -> str:
        return f'Rate limit exceeded: [{self.message}] {self.result}'


class ChainscanNetworkError(ChainscanClientError):
    """Network/connection error."""

    failure_kind: FailureKind | None = FailureKind.TRANSIENT

    def __init__(
        self,
        message: str,
        retryable: bool = True,
        *,
        failure_kind: FailureKind | None = None,
    ) -> None:
        self.message = message
        self.retryable = retryable
        super().__init__(str(self), failure_kind=failure_kind)

    def __str__(self) -> str:
        return self.message


# The ONE transient-failure vocabulary: the Network transport's retry policy
# retries exactly these, and its first-request guard treats exactly these as
# "the probe blipped — stay armed and re-probe on the next request". Defined
# here so the guard list and the retry list cannot drift (they were equal by
# discipline and a "mirrors" comment before; they are equal by construction
# now). ``TenacityRetryAdapter.DEFAULT_RETRY_EXCEPTIONS`` is this constant as
# well — previously only ``(ChainscanRateLimitError,)``, an intentional
# strengthening of the adapter's *standalone* default that changes no Network
# wire behavior (Network always passed the full list explicitly).
TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    ChainscanRateLimitError,
    ChainscanNetworkError,
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)


class ChainscanDataError(ChainscanClientError):
    """Data quality or contract violation in API responses.

    This exception is raised when API data cannot be processed due to:
    - Invalid data types (e.g., None where int expected)
    - Missing required fields
    - Sorting failures due to malformed data
    - Data that violates expected contracts
    """

    failure_kind: FailureKind | None = FailureKind.FATAL

    def __init__(
        self,
        message: str,
        details: Any = None,
        *,
        failure_kind: FailureKind | None = None,
    ) -> None:
        self.message = message
        self.details = details
        super().__init__(str(self), failure_kind=failure_kind)

    def __str__(self) -> str:
        if self.details:
            return f'{self.message} | Details: {self.details}'
        return self.message


class ChainscanWaitTimeoutError(ChainscanClientError, TimeoutError):
    """A ``wait_for_*`` polling helper exceeded its timeout before reaching a final state.

    Raised by :meth:`~aiochainscan.core.client.ChainscanClient.wait_for_transaction`,
    ``wait_for_verification`` and ``wait_for_block`` when the awaited condition
    (mined transaction, terminal verification verdict, reached block) did not
    materialize within the requested budget. Subclasses the builtin
    ``TimeoutError`` so generic wait/timeout handling catches it too.

    Attributes:
        what: Human-readable description of the awaited condition.
        waited: Seconds actually spent waiting before giving up.
        last_state: Last non-final observation for diagnosis — the pending
            API payload or the transient exception returned by the probe.
    """

    def __init__(self, what: str, waited: float, last_state: Any = None) -> None:
        self.what = what
        self.waited = waited
        self.last_state = last_state
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f'Timed out after {self.waited:.1f}s waiting for {self.what}. '
            f'Last state: {self.last_state!r}'
        )


class CompletenessUnavailableError(ChainscanClientError):
    """Raised when ``guarantee_complete`` cannot be honoured for an endpoint.

    Sibling of :class:`PaginationDataLossError`, for the case splitting cannot
    address: the endpoint has **no splittable dimension** on this provider.
    Token holders are the practical example — a holder list has no block range,
    so a provider that caps its result window can never serve a complete one,
    no matter how the request is narrowed.

    This is a statement about the provider, not about the data: another
    provider that paginates the same method by an exhaustible cursor
    (``Scanner.result_window is None``) can serve it completely, and the
    message names the ones that can.

    Attributes:
        method: Logical method name (``Method.TOKEN_HOLDERS.name``).
        provider: Label of the provider that cannot complete it.
        items_fetched: Records reachable before the window ran out.
        api_limit: The provider's declared result window.
        alternatives: Provider labels declaring ``method`` with no result
            window. Computed from the scanner registry by the caller; empty
            when none is registered.
        confirmed: ``True`` when the provider signalled more records beyond
            the window; ``False`` when it came back exactly full with no
            continuation (possibly complete, unprovably so).
    """

    def __init__(
        self,
        method: str,
        provider: str,
        items_fetched: int,
        api_limit: int,
        alternatives: tuple[str, ...] = (),
        *,
        confirmed: bool = True,
    ) -> None:
        self.method = method
        self.provider = provider
        self.items_fetched = items_fetched
        self.api_limit = api_limit
        self.alternatives = alternatives
        self.confirmed = confirmed
        super().__init__(self._describe())

    def _describe(self) -> str:
        if self.confirmed:
            cause = (
                f'{self.provider} stopped at its {self.api_limit}-record window after '
                f'{self.items_fetched} records and signalled more'
            )
        else:
            cause = (
                f'{self.provider} returned exactly its {self.api_limit}-record window '
                f'({self.items_fetched} records) and offered no continuation, so the result '
                f'is possibly truncated at exactly the cap'
            )
        if self.alternatives:
            remedy = f'Providers that can serve it completely: {", ".join(self.alternatives)}.'
        else:
            remedy = 'No registered provider serves this method without a result window.'
        return (
            f'CANNOT GUARANTEE A COMPLETE {self.method} RESULT: {cause}. This endpoint has no '
            f'block range to narrow, so range splitting cannot help. {remedy} '
            f'Or pass guarantee_complete=False to accept a possibly truncated result.'
        )

    def __str__(self) -> str:
        return self._describe()


class PaginationDataLossError(ChainscanClientError):
    """Raised when a single block contains more transactions than the API's pagination limit.

    This is the "whale block" problem: when a block has 10,000+ transactions and the API
    only allows fetching 10,000 items per request. Without per-transaction pagination
    or GraphQL support, we cannot retrieve all data without loss.

    This exception prevents silent data loss by failing loudly when this scenario is detected.

    Attributes:
        block_number: The block that contains too many transactions.
        items_fetched: Number of items successfully fetched (limited by API).
        api_limit: The API's maximum items per request.
        suggested_action: Human-readable guidance on how to resolve the issue.
        start_block: Lower bound of the block range that overflowed. Defaults
            to ``block_number`` (the single-block case).
        end_block: Upper bound of the overflowing block range (see above).
        confirmed: ``True`` when the provider itself signalled more records
            beyond the window (data was definitely lost). ``False`` when the
            window came back exactly full with no continuation — possibly
            complete, unprovably so; see :meth:`_describe`.

    An endpoint with no block-range dimension at all raises
    :class:`CompletenessUnavailableError` instead — splitting cannot apply
    there, so reporting it as a whale block would misdescribe it.
    """

    def __init__(
        self,
        block_number: int,
        items_fetched: int,
        api_limit: int,
        suggested_action: str = 'Use GraphQL API, transaction index pagination, or topic filters.',
        *,
        start_block: int | None = None,
        end_block: int | None = None,
        confirmed: bool = True,
    ) -> None:
        self.block_number = block_number
        self.items_fetched = items_fetched
        self.api_limit = api_limit
        self.suggested_action = suggested_action
        self.start_block = block_number if start_block is None else start_block
        self.end_block = block_number if end_block is None else end_block
        self.confirmed = confirmed
        super().__init__(self._describe())

    def _subject(self) -> str:
        """Describe what overflowed: one block or a block range."""
        if self.start_block != self.end_block:
            return f'block range [{self.start_block}, {self.end_block}]'
        return f'block {self.block_number}'

    def _describe(self) -> str:
        if self.confirmed:
            return (
                f'PAGINATION DATA LOSS: {self._subject()} holds more than the '
                f'{self.api_limit}-record window this API serves, and cannot be narrowed '
                f'further. {self.items_fetched} records were reachable; the rest are not. '
                f'Suggested action: {self.suggested_action}'
            )
        return (
            f'PAGINATION COMPLETENESS UNPROVEN: {self._subject()} returned exactly the '
            f'{self.api_limit}-record window this API serves and offered no continuation, '
            f'so the result is POSSIBLY truncated at exactly the cap — the API gives no way '
            f'to tell a complete result of {self.items_fetched} records from a capped one. '
            f'The range cannot be narrowed further. '
            f'Suggested action: {self.suggested_action}'
        )

    def __str__(self) -> str:
        return self._describe()
