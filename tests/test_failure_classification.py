"""The whole provider-signal → :class:`FailureKind` mapping, as one table.

Each rule is also tested where it is written (``test_network.py``,
``test_provider_pool.py``, ``test_nodereal.py``); this file is the only place
that states the mapping as a whole, so a rule moved between modules cannot
change what a signal means.
"""

from __future__ import annotations

import httpx
import pytest

from aiochainscan.core.pool import classify_failure
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanDataError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
    ChainscanResultWindowExceededError,
    FailureKind,
    InputLimitExceededError,
    MethodNotDeclaredError,
    http_status_failure_kind,
    mentions_rate_limit,
)
from aiochainscan.scanners.nodereal import (
    _is_result_size_refusal,
    _translate_usage_limit,
)

HTTP_STATUS_KINDS: tuple[tuple[int, FailureKind], ...] = (
    (429, FailureKind.RATE_LIMIT),
    (500, FailureKind.TRANSIENT),
    (502, FailureKind.TRANSIENT),
    (599, FailureKind.TRANSIENT),
    (401, FailureKind.AUTH),
    (403, FailureKind.AUTH),
    (400, FailureKind.FATAL),
    (404, FailureKind.FATAL),
    (418, FailureKind.FATAL),
)

ENVELOPE_TEXT_KINDS: tuple[tuple[str, FailureKind], ...] = (
    ('Invalid API Key', FailureKind.AUTH),
    ('Missing/Invalid API Key', FailureKind.AUTH),
    ('No API key specified', FailureKind.AUTH),
    ('Free API Access is not supported for this chain', FailureKind.PLAN_RESTRICTED),
    ('Upgrade your API plan', FailureKind.PLAN_RESTRICTED),
    ('This is an API Pro endpoint', FailureKind.PLAN_RESTRICTED),
    ('Error! Invalid address format', FailureKind.FATAL),
    ('', FailureKind.FATAL),
)

RATE_LIMIT_TEXTS: tuple[tuple[str, bool], ...] = (
    ('Max rate limit reached', True),
    ('rate limit exceeded', True),
    ('Too Many Requests', True),
    ('Invalid API Key', False),
    ('', False),
)

EXCEPTION_KINDS: tuple[tuple[BaseException, FailureKind], ...] = (
    (ChainscanRateLimitError('throttled', 'slow down'), FailureKind.RATE_LIMIT),
    (ChainscanNetworkError('reset', retryable=True), FailureKind.TRANSIENT),
    (httpx.ConnectTimeout('timed out'), FailureKind.TRANSIENT),
    (MethodNotDeclaredError('not declared'), FailureKind.METHOD_UNDECLARED),
    (InputLimitExceededError('getcontractcreation', 6, 5), FailureKind.FATAL),
    (ChainscanResultWindowExceededError('too many logs', limit=50_000), FailureKind.FATAL),
    (ChainscanDataError('unexpected shape'), FailureKind.FATAL),
    (ChainscanClientProxyError(-32000, 'execution reverted'), FailureKind.FATAL),
    (ValueError('bad argument'), FailureKind.FATAL),
    (ChainscanClientApiError('Invalid API Key', None), FailureKind.AUTH),
    (ChainscanClientApiError('NOTOK', 'Free API Access'), FailureKind.PLAN_RESTRICTED),
    (ChainscanClientApiError('NOTOK', 'something else'), FailureKind.FATAL),
    (ChainscanClientError('HTTP 403', failure_kind=FailureKind.AUTH), FailureKind.AUTH),
)

#: NodeReal overloads JSON-RPC -32005: throttling (retryable rate limit) vs a
#: deterministic result-size refusal (fatal, but splittable by the engine).
NODEREAL_32005: tuple[tuple[str, bool], ...] = (
    ('usage limit exceeded for this key', False),
    ('logs count exceeds the limit 50000', True),
    ('query returned more than 10000 results', True),
)


@pytest.mark.parametrize(('status', 'expected'), HTTP_STATUS_KINDS)
def test_http_status_kinds(status: int, expected: FailureKind) -> None:
    assert http_status_failure_kind(status) is expected


@pytest.mark.parametrize(('text', 'expected'), ENVELOPE_TEXT_KINDS)
def test_envelope_text_kinds(text: str, expected: FailureKind) -> None:
    assert classify_failure(ChainscanClientApiError(text, None)) is expected


@pytest.mark.parametrize(('text', 'expected'), RATE_LIMIT_TEXTS)
def test_rate_limit_markers(text: str, expected: bool) -> None:
    assert mentions_rate_limit(text) is expected


@pytest.mark.parametrize(('exc', 'expected'), EXCEPTION_KINDS)
def test_exception_kinds(exc: BaseException, expected: FailureKind) -> None:
    assert classify_failure(exc) is expected


@pytest.mark.parametrize(('message', 'is_result_size'), NODEREAL_32005)
def test_nodereal_32005_split(message: str, is_result_size: bool) -> None:
    exc = ChainscanClientProxyError(-32005, message)
    assert _is_result_size_refusal(exc) is is_result_size
    translated = _translate_usage_limit(exc)
    if is_result_size:
        assert translated is None
    else:
        assert isinstance(translated, ChainscanRateLimitError)
        assert classify_failure(translated) is FailureKind.RATE_LIMIT
