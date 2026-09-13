"""Response-envelope dialects: the seam between raw JSON payloads and typed errors.

A dialect knows (a) how to detect an error in a parsed JSON payload and raise
the matching transport exception and (b) how to extract the caller-facing
payload from a success envelope. The transport (:mod:`aiochainscan.network`)
selects a dialect per request path and applies it inside the retry policy, so
a dialect that translates an overloaded error code (NodeReal's ``-32005``)
shifts that meaning before the retry decision, not after.

This module owns the envelope contract only: the :class:`ResponseDialect`
protocol, the default Etherscan + JSON-RPC composite, and the
payload-extraction / error-raising helpers both envelopes share. HTTP status
classification, Retry-After parsing, content-type gating and the response
size cap are transport concerns and stay in :mod:`aiochainscan.network`.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from aiochainscan.constants import NETWORK_ERROR_EXCERPT_BYTES
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientProxyError,
    ChainscanDataError,
    ChainscanRateLimitError,
    api_error_failure_kind,
    mentions_rate_limit,
)


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

        if mentions_rate_limit(result) or mentions_rate_limit(message):
            raise ChainscanRateLimitError(message, result)

        raise ChainscanClientApiError(
            message, result, failure_kind=api_error_failure_kind(message, result)
        )


def _is_jsonrpc_batch(response_json: Any) -> bool:
    """Whether the payload is a non-empty list of JSON-RPC envelopes.

    Deliberately narrow: a top-level list is a legitimate payload shape for
    other dialects, so only elements that identify themselves as JSON-RPC
    (a ``jsonrpc`` member, or an ``id`` alongside ``result``/``error``) count.
    """
    if not isinstance(response_json, list) or not response_json:
        return False
    return all(
        isinstance(item, dict)
        and ('jsonrpc' in item or ('id' in item and ('result' in item or 'error' in item)))
        for item in response_json
    )


def _raise_if_jsonrpc_error(response_json: Any) -> None:
    """JSON-RPC 2.0 error-object check (``{"jsonrpc", "id", "result"|"error"}``).

    A present-but-null ``error`` is not an error: several nodes emit both
    members and null the unused one, so the key's presence cannot be the
    signal — its value must be.

    A batch answer (a list of envelopes) is refused rather than passed on:
    this library never batches, so the caller would receive a list of
    envelopes where a single payload is expected, and any ``error`` member
    inside it would go unread. The request ``id`` is deliberately NOT
    checked — the dialect sees the response only, and each HTTP response is
    paired with its own request by the transport.
    """
    if _is_jsonrpc_batch(response_json):
        raise ChainscanDataError(
            'JSON-RPC batch response received for a single request '
            f'({len(response_json)} envelopes); '
            'this transport sends no batches and cannot unwrap one.'
        )
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
