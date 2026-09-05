"""Validation and normalization of custom scanner base URLs.

Enables self-hosted / private explorer instances::

    ChainscanClient.from_config('blockscout_v2', 'https://my-blockscout.internal')

Heuristic (see :func:`is_url_like`): a string carrying a ``scheme://`` prefix
is treated as a base URL, anything else as a chain name/alias. Chain aliases
never contain ``://``, so the split is deterministic and backward compatible.

Security defaults (fail closed):

- ``https`` only; cleartext ``http`` requires an explicit ``allow_http=True``
  (a warning is emitted when an API key would travel over cleartext).
- credentials in the URL (``user:pass@host``) are rejected.
- query strings and fragments are rejected (they would corrupt request URLs).
- ``..`` path segments are rejected (path traversal).
- no whitespace or control characters anywhere in the URL.

The returned URL is normalized: lowercased scheme/host, trailing slash
stripped, optional base path kept (reverse-proxy mounts such as
``https://example.com/explorer`` are supported).
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit, urlunsplit

__all__ = ['is_url_like', 'validate_base_url']

# scheme:// prefix — per RFC 3986 scheme = ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )
_URL_LIKE_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://')

_FORBIDDEN_CHARS_RE = re.compile(r'[\s\x00-\x1f\x7f]')

# Legal hostname characters: letters, digits, dots and hyphens (RFC 1123 —
# punycode spell an IDN through this charset). Everything else — backslashes,
# percent escapes, underscores, unicode — is refused at validation time
# instead of surfacing as a late DNS/request error.
_HOSTNAME_RE = re.compile(r'^[A-Za-z0-9.\-]+$')

# Bracketed IPv6 literal: hex digits, colons (and the IPv4-embedded dot form).
_IPV6_LITERAL_RE = re.compile(r'^\[[0-9A-Fa-f:.]+\]$')


def is_url_like(value: str) -> bool:
    """Return True when *value* looks like ``scheme://…`` (a base URL).

    This is the URL-vs-alias heuristic behind ``from_config``: network aliases
    (``ethereum``, ``base``, ``sepolia``…) never contain ``://``.
    """
    return bool(_URL_LIKE_RE.match(value))


def _validate_netloc(url: str, netloc: str) -> None:
    """Validate the hostname charset and port range BEFORE any request.

    ``urlsplit`` accepts things no DNS resolver or HTTP client will ever
    reach: ``https://example.com\\..\\etc`` keeps the backslashes inside the
    netloc, ``https://host:99999`` parses a port that cannot exist, and a
    percent- or underscore-spelled host only dies at connection time.
    Refusing them here turns a late DNS/request error into a
    construction-time ``ValueError``.
    """
    # Credentials were already refused, so everything after the last '@' (an
    # '@' cannot start a hostname) is the host[:port] part.
    host_part = netloc.rsplit('@', 1)[-1]
    port: str | None = None

    if host_part.startswith('['):
        close = host_part.find(']')
        if close == -1:
            raise ValueError(f'base URL has a malformed bracketed host: {url!r}')
        host_literal = host_part[: close + 1]
        remainder = host_part[close + 1 :]
        if remainder and not remainder.startswith(':'):
            raise ValueError(f'base URL has a malformed host[:port]: {url!r}')
        if not _IPV6_LITERAL_RE.match(host_literal):
            raise ValueError(
                f'base URL host has invalid characters for an IPv6 literal: {host_literal!r}'
            )
        port = remainder[1:] if remainder else None
    else:
        host, port_separator, port_value = host_part.partition(':')
        if port_separator and not port_value:
            raise ValueError(f'base URL has an empty port: {url!r}')
        if not _HOSTNAME_RE.match(host):
            raise ValueError(
                f'base URL host must contain only letters, digits, dots and hyphens '
                f'(spell an IDN in punycode; use a bracketed IPv6 literal), got {host!r}'
            )
        port = port_value if port_separator else None

    if port is not None and (not port.isdigit() or not 1 <= int(port) <= 65535):
        raise ValueError(f'base URL port must be an integer in 1..65535, got {port!r}')


def validate_base_url(url: str, *, allow_http: bool = False) -> str:
    """Validate and normalize a custom scanner base URL.

    Args:
        url: Candidate base URL (must carry an ``https://`` scheme by default).
        allow_http: Explicitly permit cleartext ``http://`` (e.g. for
            air-gapped LAN deployments). Off by default.

    Returns:
        Normalized URL: lowercased scheme/host, trailing slash stripped,
        optional base path preserved.

    Raises:
        ValueError: On any rule violation (see module docstring).
    """
    if not url or not url.strip():
        raise ValueError('base URL must not be empty')

    if _FORBIDDEN_CHARS_RE.search(url):
        raise ValueError(f'base URL must not contain whitespace or control characters: {url!r}')

    if not is_url_like(url):
        raise ValueError(
            f'base URL must carry a scheme (https://…), got {url!r}. '
            'Bare hostnames are not accepted; chain names/aliases never contain "://".'
        )

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()

    if scheme not in ('https', 'http'):
        raise ValueError(
            f'unsupported base URL scheme {parts.scheme!r}: use https:// '
            '(http only with allow_http=True)'
        )
    if scheme == 'http' and not allow_http:
        raise ValueError(
            'cleartext http base URL refused: pass allow_http=True to explicitly opt in'
        )

    if not parts.hostname:
        raise ValueError(f'base URL is missing a host: {url!r}')
    if parts.username is not None or parts.password is not None:
        raise ValueError('base URL must not contain credentials (user:pass@host)')

    _validate_netloc(url, parts.netloc)

    if parts.query:
        raise ValueError(f'base URL must not contain a query string: {parts.query!r}')
    if parts.fragment:
        raise ValueError(f'base URL must not contain a fragment: {parts.fragment!r}')

    path = parts.path.rstrip('/')
    # Percent-decode before the dot-segment check: '%2e%2e' and '..%2f' are the
    # same traversal to any server that decodes the path, and this check is
    # defense in depth precisely against a path the caller did not read.
    if '..' in unquote(path).replace('\\', '/').split('/'):
        raise ValueError(f'base URL path must not contain ".." segments: {path!r}')

    # Normalize: lowercase scheme + netloc (host[:port]); keep the base path.
    netloc = parts.netloc.lower()
    return urlunsplit((scheme, netloc, path, '', ''))
