"""Credential redaction helpers for safe logging.

Self-contained (no Network state): sensitive-header/query/path matching plus
URL/payload/header redaction. Extracted verbatim from
:mod:`aiochainscan.network`, which re-exports the public names for
compatibility — the transport remains the only in-repo caller.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from collections.abc import Mapping
from typing import Any, cast

import httpx

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
_URL_IN_TEXT = re.compile(r'https?://[^\s"<>]+')
_REDACTED = '***REDACTED***'


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
    return {k: (_REDACTED if _is_sensitive_header(k) else v) for k, v in headers.items()}


def _redact_url(url: str | httpx.URL) -> str:
    """Redact sensitive query parameters and key-shaped path segments for logging."""
    parsed = urllib.parse.urlparse(str(url))
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)

    redacted_pairs = [(k, _REDACTED if _is_sensitive_query_name(k) else v) for k, v in query_pairs]
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
                k: (_REDACTED if _is_sensitive_query_name(k) else redact_value(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [redact_value(item) for item in value]
        return value

    return cast(dict[str, Any], redact_value(payload))


def _redact_log_text(value: str) -> str:
    """Redact URL credentials embedded in a preformatted log message."""

    return _URL_IN_TEXT.sub(lambda match: _redact_url(match.group(0)), value)


def _redact_log_value(value: Any) -> Any:
    """Redact URL, header, and query values in logging arguments."""

    if isinstance(value, httpx.URL):
        return _redact_url(value)
    if isinstance(value, str):
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme in {'http', 'https'} and parsed.netloc:
            return _redact_url(value)
        return value
    if isinstance(value, Mapping):
        payload = _redact_payload(dict(value)) or {}
        scalar_headers = {
            str(key): str(item) for key, item in value.items() if isinstance(item, str)
        }
        redacted_headers = _redact_headers(scalar_headers) or {}
        return {
            key: (
                redacted_headers.get(str(key), _REDACTED)
                if _is_sensitive_header(str(key))
                else payload.get(key, _redact_log_value(item))
            )
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_redact_log_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_log_value(item) for item in value]
    return value


class CredentialRedactionFilter(logging.Filter):
    """Keep third-party HTTP request records safe without dropping them."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = _redact_log_text(record.msg) if isinstance(record.msg, str) else record.msg
            args = _redact_log_value(record.args)
        except Exception:
            # Logging must remain best-effort: a malformed third-party record
            # must still reach its handlers even if its shape is unfamiliar.
            return True
        record.msg = msg
        record.args = args
        return True


_HTTP_LOG_FILTER = CredentialRedactionFilter()


def install_http_logging_filter() -> None:
    """Install the singleton filter on httpx exactly once."""

    logger = logging.getLogger('httpx')
    if not any(existing is _HTTP_LOG_FILTER for existing in logger.filters):
        logger.addFilter(_HTTP_LOG_FILTER)
