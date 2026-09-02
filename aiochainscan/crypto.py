"""Keccak-256 hashing and EIP-55 address primitives.

Single source of truth for the Ethereum hash/address helpers used across
layers (decoding selectors/topics, address validation, ENS namehash).

Backend resolution at import time:
1. fastabi Rust extension — the ``aiochainscan[fastabi]`` extra
2. eth-utils — pure-Python, via the ``fallback`` extra
3. ``aiochainscan._keccak`` — pure Python, stdlib only, always present. The
   correctness floor: this is what a bare ``pip install aiochainscan`` (no
   extras) runs on, so address construction never raises
   ``ChainscanDependencyError``.

Cross-checked byte-for-byte across all three backends against official
Keccak-256 test vectors in ``tests/test_crypto.py``.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from aiochainscan.exceptions import ChainscanDependencyError

__all__ = [
    'KECCAK_BACKEND',
    'is_address',
    'keccak256',
    'keccak_hex',
    'to_checksum_address',
]

_KeccakFn = Callable[[bytes], bytes]

_KECCAK: _KeccakFn | None = None
KECCAK_BACKEND = 'none'

try:
    try:
        from aiochainscan_fastabi import keccak256 as _fastabi_keccak
    except ImportError:
        from aiochainscan.aiochainscan_fastabi import keccak256 as _fastabi_keccak

    _KECCAK = _fastabi_keccak
    KECCAK_BACKEND = 'fastabi'
except ImportError:  # pragma: no cover - exercised only without a Rust build
    try:
        from eth_utils import keccak as _eth_utils_keccak  # type: ignore[attr-defined]

        _KECCAK = _eth_utils_keccak
        KECCAK_BACKEND = 'eth-utils'
    except ImportError:
        from aiochainscan._keccak import keccak256 as _python_keccak

        _KECCAK = _python_keccak
        KECCAK_BACKEND = 'python'

_HEX_ADDRESS_RE = re.compile(r'\A(?:0x)?[0-9a-fA-F]{40}\Z')


def keccak256(data: bytes) -> bytes:
    """Return the Keccak-256 (Ethereum flavor) digest of ``data``.

    Distinct from NIST SHA3-256: uses the original Keccak padding.
    """
    if _KECCAK is None:  # pragma: no cover - the pure-Python backend never leaves this None
        raise ChainscanDependencyError(
            'keccak256 has no available backend (fastabi, eth-utils, and the '
            'built-in pure-Python implementation all failed to load).'
        )
    return _KECCAK(data)


def keccak_hex(text: str) -> str:
    """Hex Keccak-256 digest of UTF-8 ``text`` (source of selectors/topics)."""
    return keccak256(text.encode('utf-8')).hex()


def to_checksum_address(value: str) -> str:
    """Normalize a hex address to its EIP-55 mixed-case checksum form.

    Mirrors eth-utils leniency: accepts 40 hex digits with or without the
    ``0x`` prefix and any digit casing; the output casing is derived from the
    Keccak-256 hash of the lowercase body (EIP-55) and is always prefixed.
    """
    if not isinstance(value, str) or not _HEX_ADDRESS_RE.match(value):
        raise ValueError(f'Invalid EVM address: {value!r}')
    hex_addr = value.removeprefix('0x').lower()
    digest = keccak256(hex_addr.encode('ascii')).hex()
    return '0x' + ''.join(
        char.upper() if int(digest[i], 16) >= 8 else char for i, char in enumerate(hex_addr)
    )


def is_address(value: str) -> bool:
    """True for 40 hex digits (``0x`` optional) — any casing accepted.

    Mirrors eth-utils ``is_address`` semantics, which are purely syntactic:
    a mixed-case form is accepted even when its EIP-55 checksum is invalid.
    Checksum *validity* is a separate question — compare against
    :func:`to_checksum_address` output.
    """
    return isinstance(value, str) and _HEX_ADDRESS_RE.match(value) is not None
