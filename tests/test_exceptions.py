"""Offline tests for the exception taxonomy and its routing kinds."""

from __future__ import annotations

from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanDataError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
    ChainscanResponseTooLargeError,
    CompletenessUnavailableError,
    FailureKind,
    MethodNotDeclaredError,
    PaginationDataLossError,
    ProviderPoolExhaustedError,
)


def test_all_exceptions_inherit_properly():
    """Test that all custom exceptions inherit from ChainscanClientError."""
    exceptions_to_test = [
        ChainscanClientApiError('test', 'result'),
        ChainscanClientContentTypeError(500, 'error'),
        ChainscanClientProxyError('123', 'message'),
        ChainscanRateLimitError('NOTOK', 'Max rate limit reached'),
        ChainscanNetworkError('HTTP 503 for api'),
        ChainscanDataError('missing field'),
        ChainscanResponseTooLargeError(actual_bytes=11, max_bytes=10),
        CompletenessUnavailableError(
            method='TOKEN_HOLDERS', provider='p', items_fetched=0, api_limit=10_000
        ),
        PaginationDataLossError(block_number=1, items_fetched=10, api_limit=10),
        ProviderPoolExhaustedError('op', [('p', ValueError('boom'))]),
        ChainscanClientError('plain'),
    ]

    for exc in exceptions_to_test:
        assert isinstance(exc, ChainscanClientError)
        assert isinstance(exc, Exception)

        # Test that they have meaningful string representations
        assert len(str(exc)) > 0

    # MethodNotDeclaredError deliberately keeps the historical ValueError
    # contract instead (see its docstring) — it must NOT be a client error.
    assert isinstance(MethodNotDeclaredError('Method X not declared'), ValueError)
    assert not isinstance(MethodNotDeclaredError('Method X not declared'), ChainscanClientError)


def test_default_failure_kind_per_class():
    """Every exception class declares the failure_kind the pool's fallback
    ladder used to derive from its type — no second taxonomy."""
    assert ChainscanClientError('x').failure_kind is FailureKind.FATAL
    assert ChainscanRateLimitError('NOTOK', 'Max rate limit reached').failure_kind is (
        FailureKind.RATE_LIMIT
    )
    assert ChainscanNetworkError('HTTP 503 for api').failure_kind is FailureKind.TRANSIENT
    assert MethodNotDeclaredError('Method X not declared').failure_kind is (
        FailureKind.METHOD_UNDECLARED
    )
    assert ChainscanDataError('missing field').failure_kind is FailureKind.FATAL
    assert ChainscanClientProxyError(-32000, 'missing value').failure_kind is FailureKind.FATAL
    assert ChainscanClientContentTypeError(200, 'html').failure_kind is FailureKind.FATAL
    assert (
        ChainscanResponseTooLargeError(actual_bytes=11, max_bytes=10).failure_kind
        is FailureKind.FATAL
    )


def test_api_error_default_kind_is_undecided():
    """A ChainscanClientApiError constructed without an explicit kind carries
    ``None``: classification falls back to the Etherscan-style text patterns
    (see network.api_error_failure_kind), exactly as the pool ladder did."""
    assert ChainscanClientApiError.failure_kind is None
    assert ChainscanClientApiError('NOTOK', 'Invalid API Key').failure_kind is None


def test_raise_site_failure_kind_override_wins():
    """The ``failure_kind`` constructor keyword overrides the class default
    on the instance — this is the seam that lets a scanner wire a new
    failure mode without core edits."""
    exc = ChainscanClientApiError(
        'WeirdScanner quota exceeded', 'see provider docs', failure_kind=FailureKind.AUTH
    )
    assert exc.failure_kind is FailureKind.AUTH

    # Also available on the other transport-seam exceptions.
    assert ChainscanNetworkError('m', failure_kind=FailureKind.FATAL).failure_kind is (
        FailureKind.FATAL
    )
    assert (
        ChainscanRateLimitError(
            'NOTOK', 'Max rate limit reached', failure_kind=FailureKind.TRANSIENT
        ).failure_kind
        is FailureKind.TRANSIENT
    )
    assert ChainscanDataError('m', failure_kind=FailureKind.TRANSIENT).failure_kind is (
        FailureKind.TRANSIENT
    )
    assert (
        ChainscanClientProxyError(
            -32005, 'usage limit', failure_kind=FailureKind.RATE_LIMIT
        ).failure_kind
        is FailureKind.RATE_LIMIT
    )
    assert (
        ChainscanClientError('m', failure_kind=FailureKind.AUTH).failure_kind is FailureKind.AUTH
    )


def test_instance_override_does_not_mutate_class_default():
    """An instance override must not leak into the class-level default."""
    _exc = ChainscanClientApiError('m', 'r', failure_kind=FailureKind.PLAN_RESTRICTED)
    assert ChainscanClientApiError.failure_kind is None
    assert ChainscanClientApiError('m', 'r').failure_kind is None


def test_exception_messages():
    """Test exception message formatting."""
    exc = ChainscanClientApiError('NOTOK', 'No transactions found')
    assert str(exc) == '[NOTOK] No transactions found'

    exc = ChainscanClientProxyError(-32000, 'missing value')
    assert str(exc) == '[-32000] missing value'

    exc = ChainscanDataError('missing field', details={'field': 'blockNumber'})
    assert 'missing field' in str(exc)
    assert 'blockNumber' in str(exc)
