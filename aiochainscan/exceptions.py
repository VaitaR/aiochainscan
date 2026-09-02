from __future__ import annotations

from typing import Any


class ChainscanClientError(Exception):
    """Base error type for aiochainscan client failures."""

    pass


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
    def __init__(self, message: str | None, result: Any) -> None:
        self.message: str | None = message
        self.result: Any = result

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'[{self.message}] {self.result}'


class ChainscanClientProxyError(ChainscanClientError):
    """JSON-RPC 2.0 Specification

    https://www.jsonrpc.org/specification#error_object
    """

    def __init__(self, code: int | None, message: str | None) -> None:
        self.code: int | None = code
        self.message: str | None = message

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'[{self.code}] {self.message}'


class FeatureNotSupportedError(ChainscanClientError):
    """Raised when a feature is not supported by the specific blockchain scanner."""

    def __init__(self, feature: str, scanner: str) -> None:
        self.feature = feature
        self.scanner = scanner
        super().__init__(f'Feature "{feature}" is not supported by {scanner}')

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'Feature "{self.feature}" is not supported by {self.scanner}'


class SourceNotVerifiedError(ChainscanClientError):
    """Contract source code is not verified on explorer."""

    def __init__(self, address: str) -> None:
        self.address = address
        super().__init__(f'Contract source code not verified for address {address}')

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'Contract source code not verified for address {self.address}'


class ChainscanRateLimitError(ChainscanClientError):
    """Rate limit exceeded.

    Etherscan and similar APIs often return HTTP 200 with error message
    like {"status":"0","message":"NOTOK","result":"Max rate limit reached"}.
    This exception signals that the request should be retried after a delay.
    """

    def __init__(
        self, message: str | None = None, result: Any = None, retry_after: int = 5
    ) -> None:
        self.message: str | None = message
        self.result: Any = result
        self.retry_after = retry_after
        super().__init__(str(self))

    def __str__(self) -> str:
        return f'Rate limit exceeded: [{self.message}] {self.result}'


class ChainscanInvalidAddressError(ChainscanClientError):
    """Invalid address format."""

    def __init__(self, address: str) -> None:
        self.address = address
        super().__init__(str(self))

    def __str__(self) -> str:
        return f'Invalid address format: {self.address}'


class ChainscanNetworkError(ChainscanClientError):
    """Network/connection error."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        self.message = message
        self.retryable = retryable
        super().__init__(str(self))

    def __str__(self) -> str:
        return self.message


class ChainscanDataError(ChainscanClientError):
    """Data quality or contract violation in API responses.

    This exception is raised when API data cannot be processed due to:
    - Invalid data types (e.g., None where int expected)
    - Missing required fields
    - Sorting failures due to malformed data
    - Data that violates expected contracts
    """

    def __init__(self, message: str, details: Any = None) -> None:
        self.message = message
        self.details = details
        super().__init__(str(self))

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
