"""Unit tests for the shared Scanner base plumbing in ``scanners/base.py``.

Covers the helpers hoisted out of the concrete scanners:

- ``Scanner._spec_for`` — SPECS lookup or the standard MethodNotDeclaredError.
- ``Scanner._require_network_client`` — injected Network or the standard
  RuntimeError.
- ``translate_unexpected_errors`` — the error-translation ladder (library
  exceptions pass through unchanged — including every class NodeReal used to
  enumerate individually — anything else is masked as a non-retryable
  network error).
- ``hex_block_tag`` — the shared int/decimal→hex block-tag coercion.
- ``checksummed_holder_address`` — the shared EIP-55 holder-address passlist.
- ``coerce_response_items`` — the canonical response→items coercion shared
  by ``Scanner._coerce_items`` and ``services.pagination.normalize_items``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aiochainscan.core.endpoint import coerce_response_items
from aiochainscan.domain.method import Method
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
    MethodNotDeclaredError,
)
from aiochainscan.scanners.base import (
    Scanner,
    checksummed_holder_address,
    hex_block_tag,
    translate_unexpected_errors,
)
from aiochainscan.scanners.blockscout_v1 import BlockScoutV1
from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner
from aiochainscan.scanners.etherscan_v2 import EtherscanV2
from aiochainscan.scanners.nodereal import NodeRealScanner
from aiochainscan.services.pagination import normalize_items

CHECKSUM_ADDRESS = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'


def _scanner(network_client: Any = None) -> BlockScoutV2Scanner:
    return BlockScoutV2Scanner(
        api_key='',
        network='ethereum',
        url_builder=MagicMock(),
        network_client=network_client,
    )


# ============================================================================
# Scanner._spec_for
# ============================================================================


class TestSpecFor:
    def test_declared_method_returns_its_spec(self) -> None:
        scanner = _scanner()

        spec = scanner._spec_for(Method.ACCOUNT_BALANCE)

        assert spec is scanner.SPECS[Method.ACCOUNT_BALANCE]

    def test_undeclared_method_raises_with_scanner_and_available_list(self) -> None:
        scanner = _scanner()

        with pytest.raises(MethodNotDeclaredError) as excinfo:
            scanner._spec_for(Method.ETH_PRICE)

        message = str(excinfo.value)
        # Message format: method, scanner name + version, available list.
        assert str(Method.ETH_PRICE) in message
        assert 'blockscout vv2' in message
        for declared in scanner.SPECS:
            assert str(declared) in message

    def test_undeclared_method_is_a_value_error(self) -> None:
        """The historical ``Scanner.call`` contract: ValueError subclass."""
        scanner = _scanner()

        with pytest.raises(ValueError):
            scanner._spec_for(Method.ETH_PRICE)


# ============================================================================
# Scanner._require_network_client
# ============================================================================


class TestRequireNetworkClient:
    def test_returns_injected_client(self) -> None:
        network = MagicMock()
        scanner = _scanner(network_client=network)

        assert scanner._require_network_client() is network

    def test_missing_client_raises_runtime_error(self) -> None:
        scanner = _scanner(network_client=None)

        with pytest.raises(RuntimeError, match='network_client is required') as excinfo:
            scanner._require_network_client()

        assert 'blockscout vv2' in str(excinfo.value)
        assert 'from_config' in str(excinfo.value)


# ============================================================================
# translate_unexpected_errors
# ============================================================================


class TestTranslateUnexpectedErrors:
    @pytest.mark.parametrize(
        'library_error',
        [
            ChainscanClientError('base'),
            ChainscanClientApiError('NOTOK', 'rate limited'),
            ChainscanNetworkError('Connection reset', retryable=True),
            ChainscanClientProxyError(-32601, 'method not found'),
            ChainscanRateLimitError('Max rate limit reached'),
        ],
        ids=['client-base', 'api', 'network', 'proxy', 'rate-limit'],
    )
    def test_library_exceptions_pass_through_unchanged(
        self, library_error: ChainscanClientError
    ) -> None:
        """Every class NodeReal's ladder used to enumerate individually (plus
        the base class the other scanners caught) keeps its identity."""
        with (
            pytest.raises(type(library_error)) as excinfo,
            translate_unexpected_errors('Scanner unexpected error'),
        ):
            raise library_error

        assert excinfo.value is library_error

    def test_unexpected_exception_masked_as_non_retryable_network_error(self) -> None:
        boom = KeyError('envelope')

        with (
            pytest.raises(ChainscanNetworkError) as excinfo,
            translate_unexpected_errors('Scanner unexpected error for host'),
        ):
            raise boom

        error = excinfo.value
        assert str(error) == f'Scanner unexpected error for host: {boom}'
        assert error.retryable is False
        assert error.__cause__ is boom

    def test_no_error_is_noop(self) -> None:
        with translate_unexpected_errors('never seen'):
            pass

    def test_method_not_declared_passes_through_unmasked(self) -> None:
        """Capability errors are routed on by the provider pool — the ladder
        must never mask them into network failures."""
        err = MethodNotDeclaredError('not declared')

        with (
            pytest.raises(MethodNotDeclaredError) as excinfo,
            translate_unexpected_errors('Scanner unexpected error'),
        ):
            raise err

        assert excinfo.value is err


# ============================================================================
# The ladder at the scanner seams — one translated envelope per scanner
# ============================================================================


class ExplodingNetwork:
    """Network stand-in whose every transport entry point fails unexpectedly.

    ``RuntimeError`` is deliberately NOT a library error: it simulates an
    unexpected network-level failure (the class of bug the ladder exists for).
    """

    async def request(self, **kwargs: Any) -> Any:
        raise RuntimeError('boom')

    async def get(self, **kwargs: Any) -> Any:
        raise RuntimeError('boom')

    async def post(self, **kwargs: Any) -> Any:
        raise RuntimeError('boom')


def _etherscan_v2(network: Any) -> EtherscanV2:
    return EtherscanV2(
        api_key='test_key', network='main', url_builder=MagicMock(), network_client=network
    )


def _blockscout_v1(network: Any) -> BlockScoutV1:
    return BlockScoutV1(api_key='', network='eth', url_builder=MagicMock(), network_client=network)


def _nodereal(network: Any) -> NodeRealScanner:
    return NodeRealScanner(
        api_key='test_key', network='bsc', url_builder=MagicMock(), network_client=network
    )


class TestLadderAtTheSeams:
    """``Scanner.call`` (and every ``fetch_page`` path) applies the shared
    error ladder exactly once: an unexpected transport failure surfaces as a
    non-retryable :class:`ChainscanNetworkError` for every scanner."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'factory',
        [
            _etherscan_v2,
            _blockscout_v1,
            lambda net: _scanner(net),
            _nodereal,
        ],
        ids=['etherscan-v2', 'blockscout-v1', 'blockscout-v2', 'nodereal'],
    )
    async def test_unexpected_transport_error_is_translated(self, factory: Any) -> None:
        scanner = factory(ExplodingNetwork())

        with pytest.raises(ChainscanNetworkError) as excinfo:
            await scanner.call(Method.ACCOUNT_BALANCE, address=CHECKSUM_ADDRESS)

        error = excinfo.value
        assert error.retryable is False
        assert 'boom' in str(error)

    @pytest.mark.asyncio
    async def test_blockscout_v2_fetch_page_translates_unexpected_errors(self) -> None:
        """The cursor pagination path is laddered too (was the only unwrapped
        paginated path before the base owned the seam)."""
        scanner = _scanner(ExplodingNetwork())

        with pytest.raises(ChainscanNetworkError) as excinfo:
            await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {'address': CHECKSUM_ADDRESS})

        error = excinfo.value
        assert error.retryable is False
        assert 'boom' in str(error)

    @pytest.mark.asyncio
    async def test_etherscan_like_fetch_page_translates_unexpected_errors(self) -> None:
        """Etherscan-like page/offset pagination routes through ``call``, so
        the base ladder covers it."""
        scanner = _etherscan_v2(ExplodingNetwork())

        with pytest.raises(ChainscanNetworkError) as excinfo:
            await scanner.fetch_page(
                Method.ACCOUNT_TRANSACTIONS, {'address': CHECKSUM_ADDRESS, 'page': 1, 'offset': 10}
            )

        error = excinfo.value
        assert error.retryable is False
        assert 'boom' in str(error)


# ============================================================================
# hex_block_tag
# ============================================================================


class TestHexBlockTag:
    def test_int_and_decimal_string_become_hex_tags(self) -> None:
        assert hex_block_tag(123) == '0x7b'
        assert hex_block_tag('123') == '0x7b'
        assert hex_block_tag(0) == '0x0'

    def test_tags_and_non_numerics_pass_through(self) -> None:
        assert hex_block_tag('latest') == 'latest'
        assert hex_block_tag('0x7b') == '0x7b'
        assert hex_block_tag('earliest') == 'earliest'
        assert hex_block_tag(None) is None


# ============================================================================
# checksummed_holder_address
# ============================================================================


class TestChecksummedHolderAddress:
    def test_lowercase_address_is_checksummed(self) -> None:
        lower = '0xd8da6bf26964af9d7eed9e03e53415d37aa96045'

        assert checksummed_holder_address(lower) == '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    def test_values_eip55_cannot_digest_pass_through(self) -> None:
        assert checksummed_holder_address('not-an-address') == 'not-an-address'
        assert checksummed_holder_address(None) is None
        assert checksummed_holder_address(12345) == 12345


# ============================================================================
# coerce_response_items — the canonical response→items coercion
# ============================================================================


class TestCanonicalItemsCoercion:
    @pytest.mark.parametrize(
        'response',
        [
            [{'hash': '0x1'}],
            {'items': [{'hash': '0x1'}], 'next_page_params': None},
            {'items': None},
            {'status': '0'},
            'No records found',
            None,
        ],
        ids=['list', 'items-envelope', 'items-none', 'dict-no-items', 'string', 'none'],
    )
    def test_scanner_and_pagination_share_one_coercion(self, response: Any) -> None:
        expected = (
            list(response)
            if isinstance(response, list)
            else (
                [{'hash': '0x1'}] if isinstance(response, dict) and response.get('items') else []
            )
        )

        assert Scanner._coerce_items(response) == expected
        assert normalize_items(response) == expected
        assert coerce_response_items(response) == expected

    def test_list_coercion_makes_a_defensive_copy(self) -> None:
        original = [{'hash': '0x1'}]

        assert Scanner._coerce_items(original) == original
        assert Scanner._coerce_items(original) is not original
        assert normalize_items(original) is not original
