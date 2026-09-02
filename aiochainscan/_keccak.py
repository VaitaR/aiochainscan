"""Pure-Python Keccak-256 (Ethereum flavor: ``0x01`` padding, distinct from the
NIST SHA3-256 ``0x06`` padding).

This is the correctness floor, not the fast path — the last link in
``crypto.py``'s backend chain (fastabi -> eth-utils -> this module), used only
when neither is importable. It exists so a bare ``pip install aiochainscan``
(no ``[fastabi]``, no ``[fallback]``) can still construct an
:class:`~aiochainscan.domain.models.Address` and stays stdlib-only, adding no
runtime dependency.

Keccak-f[1600] is a fully specified permutation with official test vectors
(see ``tests/test_crypto.py``), so this implementation's correctness is
provable by assertion — cross-checked byte-for-byte against fastabi and
eth-utils in the test suite — unlike hand-rolled policy code (retry, rate
limiting) which has no oracle to test against. It is not optimized: EIP-55
only ever hashes a 20-byte address, so simplicity and obvious correctness
matter more than speed here.
"""

from __future__ import annotations

_MASK64 = (1 << 64) - 1

_RATE_BYTES = 136  # Keccak-256 rate: 1088 bits (capacity 512 bits)
_OUTPUT_BYTES = 32  # 256-bit digest

_ROUND_CONSTANTS: tuple[int, ...] = (
    0x0000000000000001,
    0x0000000000008082,
    0x800000000000808A,
    0x8000000080008000,
    0x000000000000808B,
    0x0000000080000001,
    0x8000000080008081,
    0x8000000000008009,
    0x000000000000008A,
    0x0000000000000088,
    0x0000000080008009,
    0x000000008000000A,
    0x000000008000808B,
    0x800000000000008B,
    0x8000000000008089,
    0x8000000000008003,
    0x8000000000008002,
    0x8000000000000080,
    0x000000000000800A,
    0x800000008000000A,
    0x8000000080008081,
    0x8000000000008080,
    0x0000000080000001,
    0x8000000080008008,
)

# Rotation offsets indexed [x][y] (lane at position x + 5*y).
_ROTATION_OFFSETS: tuple[tuple[int, ...], ...] = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _rotate_left(value: int, shift: int) -> int:
    shift %= 64
    if shift == 0:
        return value
    return ((value << shift) | (value >> (64 - shift))) & _MASK64


def _keccak_f1600(state: list[int]) -> None:
    """Apply the 24-round Keccak-f[1600] permutation in place.

    ``state`` is 25 64-bit lanes, flattened as ``state[x + 5*y]``.
    """
    for round_constant in _ROUND_CONSTANTS:
        # theta
        column_parity = [
            state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20]
            for x in range(5)
        ]
        theta_d = [
            column_parity[(x - 1) % 5] ^ _rotate_left(column_parity[(x + 1) % 5], 1)
            for x in range(5)
        ]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= theta_d[x]

        # rho + pi
        rotated = [0] * 25
        for x in range(5):
            for y in range(5):
                rotated[y + 5 * ((2 * x + 3 * y) % 5)] = _rotate_left(
                    state[x + 5 * y], _ROTATION_OFFSETS[x][y]
                )

        # chi
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = rotated[x + 5 * y] ^ (
                    (~rotated[(x + 1) % 5 + 5 * y]) & rotated[(x + 2) % 5 + 5 * y]
                )

        # iota
        state[0] ^= round_constant


def keccak256(data: bytes) -> bytes:
    """Keccak-256 digest of ``data`` (Ethereum's original-padding flavor)."""
    state = [0] * 25

    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % _RATE_BYTES != 0:
        padded.append(0x00)
    padded[-1] ^= 0x80

    for offset in range(0, len(padded), _RATE_BYTES):
        block = padded[offset : offset + _RATE_BYTES]
        for i in range(0, _RATE_BYTES, 8):
            state[i // 8] ^= int.from_bytes(block[i : i + 8], 'little')
        _keccak_f1600(state)

    digest = bytearray()
    for lane_index in range(_OUTPUT_BYTES // 8):
        digest += state[lane_index].to_bytes(8, 'little')
    return bytes(digest)
