"""Tests for aiochainscan.crypto — keccak-256 and EIP-55 primitives.

Fixed vectors are independent of any reference package; cross-checks against
eth-utils run only when the dev extra (eth-utils) is installed.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from aiochainscan.crypto import (
    is_address,
    keccak256,
    keccak_hex,
    to_checksum_address,
)

# --- Well-known Keccak-256 vectors (independent of eth-*) -------------------

KECCAK_VECTORS = [
    (b'', 'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470'),
    (b'hello', '1c8aff950685c2ed4bc3174f3472287b56d9517b9c948127319a09a7a36deac8'),
    (b'abc', '4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45'),
    # ERC-20 Transfer(address,address,uint256) event topic0
    (
        b'Transfer(address,address,uint256)',
        'ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',
    ),
]

# Multi-block inputs that cross the 136-byte (rate) block boundary, so the
# padding + absorb loop of the pure-Python permutation are actually exercised
# (a suite that only hashes short strings never runs a second block).
MULTI_BLOCK_LENGTHS = [135, 136, 137, 200, 272, 273, 1000]


@pytest.mark.parametrize(('data', 'expected_hex'), KECCAK_VECTORS)
def test_keccak256_known_vectors(data: bytes, expected_hex: str) -> None:
    assert keccak256(data).hex() == expected_hex


def test_keccak_hex_transfer_selector() -> None:
    # First 4 bytes of the transfer(address,uint256) selector: a9059cbb
    assert keccak_hex('transfer(address,uint256)')[:8] == 'a9059cbb'


# --- EIP-55 checksum ---------------------------------------------------------

CHECKSUM_VECTORS = [
    # From EIP-55 spec + models.py docstring
    ('0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed', '0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed'),
    ('0xfb6916095ca1df60bb79ce92ce3ea74c37c5d359', '0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359'),
    ('0xdbf03b407c01e7cd3cbea99509d93f8dddc8c6fb', '0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB'),
    ('0xd1220a0cf47c7b9be7a2e6ba89f429762e7b9adb', '0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb'),
    ('0xd8da6bf26964af9d7eed9e03e53415d37aa96045', '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'),
]


@pytest.mark.parametrize(('raw', 'checksummed'), CHECKSUM_VECTORS)
def test_to_checksum_address_vectors(raw: str, checksummed: str) -> None:
    assert to_checksum_address(raw) == checksummed
    # Idempotent on already-checksummed input
    assert to_checksum_address(checksummed) == checksummed


@pytest.mark.parametrize(('raw', 'checksummed'), CHECKSUM_VECTORS)
def test_is_address_accepts_valid_forms(raw: str, checksummed: str) -> None:
    assert is_address(raw)  # all-lowercase
    assert is_address(checksummed)  # valid EIP-55 mixed case
    assert is_address(raw.upper().replace('0X', '0x', 1))  # all-uppercase body


BAD_ADDRESS_INPUTS = [
    '',
    '0x',
    '0xd8da6bf26964af9d7eed9e03e53415d37aa9604',  # 39 hex digits
    '0xd8da6bf26964af9d7eed9e03e53415d37aa960455',  # 41 hex digits
    '0xd8da6bf26964af9d7eed9e03e53415d37aa960zz',  # non-hex chars
    '0xZ8da6bf26964af9d7eed9e03e53415d37aa9604g',  # non-hex chars (mixed)
    'not-an-address',
]


@pytest.mark.parametrize('bad', BAD_ADDRESS_INPUTS)
def test_is_address_rejects_invalid(bad: str) -> None:
    assert not is_address(bad)


def test_is_address_is_purely_syntactic() -> None:
    """eth-utils semantics: mixed case with an INVALID checksum still passes."""
    # Real-world fixture: USDT contract as commonly displayed (invalid EIP-55
    # casing) — accepted by eth_utils.is_address and therefore by Address.
    mixed_invalid = '0xdAC17F958D2ee523a2206208994597C13D831ec7'
    assert is_address(mixed_invalid)
    assert to_checksum_address(mixed_invalid.lower()) != mixed_invalid


def test_is_address_accepts_unprefixed() -> None:
    """eth-utils leniency: bare 40-hex forms are valid addresses."""
    assert is_address('d8da6bf26964af9d7eed9e03e53415d37aa96045')
    assert to_checksum_address('d8da6bf26964af9d7eed9e03e53415d37aa96045') == (
        '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
    )


def test_to_checksum_address_invalid_input_raises() -> None:
    with pytest.raises(ValueError, match='Invalid EVM address'):
        to_checksum_address('not-an-address')


# --- Cross-check against reference eth-utils (dev extra) --------------------

eth_utils_ref = pytest.importorskip('eth_utils')


@pytest.mark.parametrize(('data', 'expected_hex'), KECCAK_VECTORS)
def test_keccak256_matches_eth_utils(data: bytes, expected_hex: str) -> None:
    assert keccak256(data) == eth_utils_ref.keccak(data)


CROSS_CHECK_ADDRESSES = [raw for raw, _ in CHECKSUM_VECTORS] + [
    '0x0000000000000000000000000000000000000000',
    '0xffffffffffffffffffffffffffffffffffffffff',
    '0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae',
    '0x7a250d5630b4cf539739df2c5dacb4c659f2488d',
    '0xdAC17F958D2ee523a2206208994597C13D831ec7',  # mixed case, invalid checksum
]


@pytest.mark.parametrize('raw', CROSS_CHECK_ADDRESSES)
def test_to_checksum_address_matches_eth_utils(raw: str) -> None:
    assert to_checksum_address(raw) == eth_utils_ref.to_checksum_address(raw)
    assert is_address(raw) == eth_utils_ref.is_address(raw)


# --- Backend degradation -----------------------------------------------------


@pytest.fixture
def reload_crypto():
    """Reload aiochainscan.crypto with manipulated sys.modules; restore after."""
    saved_fastabi = {
        name: sys.modules.get(name)
        for name in ('aiochainscan_fastabi', 'aiochainscan.aiochainscan_fastabi')
    }
    saved_eth_utils = sys.modules.get('eth_utils')
    yield
    for name, module in saved_fastabi.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    if saved_eth_utils is None:
        sys.modules.pop('eth_utils', None)
    else:
        sys.modules['eth_utils'] = saved_eth_utils
    importlib.reload(sys.modules['aiochainscan.crypto'])


def test_crypto_falls_back_to_eth_utils(reload_crypto) -> None:
    """Without fastabi, keccak resolves via eth-utils."""
    import aiochainscan.crypto as crypto_mod

    sys.modules['aiochainscan_fastabi'] = None
    sys.modules['aiochainscan.aiochainscan_fastabi'] = None
    importlib.reload(crypto_mod)

    assert crypto_mod.KECCAK_BACKEND == 'eth-utils'
    assert crypto_mod.keccak256(b'').hex() == KECCAK_VECTORS[0][1]


def test_crypto_falls_back_to_pure_python(reload_crypto) -> None:
    """Without fastabi and without eth-utils, keccak256 still works.

    This is the base-install path (no [fastabi], no [fallback] extra): a
    bare `pip install aiochainscan` must still be able to construct an
    Address, so the chain no longer ends in ChainscanDependencyError.
    """
    import aiochainscan.crypto as crypto_mod

    sys.modules['aiochainscan_fastabi'] = None
    sys.modules['aiochainscan.aiochainscan_fastabi'] = None
    sys.modules['eth_utils'] = None
    importlib.reload(crypto_mod)

    assert crypto_mod.KECCAK_BACKEND == 'python'
    assert crypto_mod.keccak256(b'').hex() == KECCAK_VECTORS[0][1]


def test_crypto_pure_python_address_checksum_roundtrip(reload_crypto) -> None:
    """EIP-55 checksum through domain.models.Address, pure-Python backend forced."""
    import aiochainscan.crypto as crypto_mod

    sys.modules['aiochainscan_fastabi'] = None
    sys.modules['aiochainscan.aiochainscan_fastabi'] = None
    sys.modules['eth_utils'] = None
    importlib.reload(crypto_mod)
    assert crypto_mod.KECCAK_BACKEND == 'python'

    from aiochainscan.domain.models import Address

    raw, checksummed = CHECKSUM_VECTORS[0]
    assert Address(raw).value == checksummed


# --- Pure-Python backend: block-boundary vectors + cross-backend agreement --


@pytest.mark.parametrize('length', MULTI_BLOCK_LENGTHS)
def test_python_keccak_matches_reference_across_block_boundary(length: int) -> None:
    """Exercise the padding + multi-block absorb loop, not just short inputs."""
    from aiochainscan._keccak import keccak256 as python_keccak

    data = (bytes(range(256)) * ((length // 256) + 1))[:length]
    reference = eth_utils_ref.keccak(data)
    assert python_keccak(data) == reference


@pytest.mark.parametrize(('data', 'expected_hex'), KECCAK_VECTORS)
def test_python_keccak_matches_official_vectors(data: bytes, expected_hex: str) -> None:
    from aiochainscan._keccak import keccak256 as python_keccak

    assert python_keccak(data).hex() == expected_hex


def _import_fastabi_if_built():
    """New top-level name first, legacy in-package name second — same
    resolution order as aiochainscan.crypto itself."""
    try:
        import aiochainscan_fastabi as fastabi

        return fastabi
    except ImportError:
        pass
    try:
        from aiochainscan import aiochainscan_fastabi as fastabi

        return fastabi
    except ImportError:
        return None


@pytest.mark.parametrize('length', [0, 1, 20, 32, 64, *MULTI_BLOCK_LENGTHS])
def test_python_keccak_matches_fastabi_when_available(length: int) -> None:
    """Strongest available proof: byte-identical to the Rust backend, when built."""
    fastabi = _import_fastabi_if_built()
    if fastabi is None:
        pytest.skip('fastabi not built in this environment')

    from aiochainscan._keccak import keccak256 as python_keccak

    data = (bytes(range(256)) * ((length // 256) + 1))[:length]
    assert python_keccak(data) == fastabi.keccak256(data)
