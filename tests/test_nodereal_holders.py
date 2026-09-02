"""Tests for NodeReal's ``nr_getTokenHolders`` / ``nr_getTokenHolderCount``.

The shapes here were derived from documentation and then checked against the
live API on 2026-09-02 (``bsc-mainnet``, BSC-USD and CAKE). The holder list,
its ``pageKey`` round-trip and the ``topN`` ordering matched; the holder
*count* did not — see
``test_parse_token_holder_count_reads_the_live_nested_envelope``. Documented
shapes are still pinned alongside the live one, because the docs are what the
provider promises. Sources:

- https://docs.nodereal.io/reference/nr_gettokenholders
  (params: ``Contract Address``, hex ``PageSize`` <= 100, ``PageKey``
  empty-for-first-page, optional hex ``topN``; response: ``pageKey`` +
  ``details: [{'accountAddress', 'tokenBalance'}]``)
- https://docs.nodereal.io/reference/nr_gettokenholdercount
  (response: hex-encoded ``count`` scalar, e.g. ``{"result": "0x123"}``)

Covers: the request envelope incl. hex PageSize encoding, the <=100 clamp,
PageKey cursor threading across pages, the normalized ``{'address', 'value'}``
item shape incl. checksumming, holder-count int coercion, and that the three
methods no longer raise ``MethodNotDeclaredError``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.domain.method import Method
from aiochainscan.exceptions import ChainscanDataError
from aiochainscan.scanners.nodereal import (
    NodeRealScanner,
    _parse_token_holder_count,
    _parse_token_holders,
)

CONTRACT = '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56'
# Lowercase on purpose: the parser must checksum it, not just pass it through.
HOLDER_LOWER = '0xd8da6bf26964af9d7eed9e03e53415d37aa96045'
HOLDER_CHECKSUMMED = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'


def _make_scanner(network: str = 'bsc', api_key: str = 'test-key') -> NodeRealScanner:
    return NodeRealScanner(
        api_key=api_key,
        network=network,
        url_builder=MagicMock(),
    )


def _mock_network(scanner: NodeRealScanner, responses: list[object]) -> AsyncMock:
    """Attach a Network double that pops canned *unwrapped* results in order."""
    network = MagicMock()
    network.request = AsyncMock(side_effect=list(responses))
    scanner._network_client = network
    return network


# ============================================================================
# Request envelope: hex PageSize, PageKey positioning, the <=100 clamp
# ============================================================================


class TestRequestEnvelope:
    def test_token_holders_default_page_size_is_hex_encoded(self) -> None:
        scanner = _make_scanner()
        rpc_params = scanner._build_rpc_params(
            Method.TOKEN_HOLDERS, {'contract_address': CONTRACT}
        )
        # [contract, hex PageSize, PageKey] — doc example:
        # ["0xcea5...", "0x14", ""]
        assert rpc_params[0] == CONTRACT
        assert rpc_params[1] == '0x64'  # 100 decimal, hex-encoded
        assert rpc_params[2] == ''

    def test_token_holders_pagekey_carried_through(self) -> None:
        scanner = _make_scanner()
        rpc_params = scanner._build_rpc_params(
            Method.TOKEN_HOLDERS,
            {'contract_address': CONTRACT, 'pageKey': 'opaque-cursor-1'},
        )
        assert rpc_params[2] == 'opaque-cursor-1'

    def test_page_size_above_100_is_clamped(self) -> None:
        # Doc: "pageSize is hex encoded and should be less equal than 100".
        scanner = _make_scanner()
        rpc_params = scanner._build_rpc_params(
            Method.TOKEN_HOLDERS, {'contract_address': CONTRACT, 'offset': 500}
        )
        assert rpc_params[1] == '0x64'  # clamped to 100, not hex(500) == '0x1f4'

    def test_page_size_below_100_is_respected(self) -> None:
        scanner = _make_scanner()
        rpc_params = scanner._build_rpc_params(
            Method.TOKEN_HOLDERS, {'contract_address': CONTRACT, 'offset': 20}
        )
        assert rpc_params[1] == '0x14'

    def test_top_holders_appends_topn_and_clamps_page_size(self) -> None:
        # Doc: topN is a 4th positional param; PageSize itself still caps at
        # 100, so get_top_token_holders() (a single non-paginated call) is
        # honestly bounded by what one page can carry.
        scanner = _make_scanner()
        rpc_params = scanner._build_rpc_params(
            Method.TOKEN_TOP_HOLDERS, {'contract_address': CONTRACT, 'offset': 250}
        )
        assert rpc_params == [CONTRACT, '0x64', '', '0x64']

    def test_top_holders_topn_follows_the_requested_limit(self) -> None:
        # A value BELOW the cap: the clamp test above cannot tell "clamped to
        # 100" from "ignored and defaulted to 100", because the clamp's answer
        # equals the default. topN riding the default while PageSize followed
        # the limit is exactly the bug this pins — the wire answered 100
        # holders for limit=5, and a full page reads as a valid answer.
        scanner = _make_scanner()
        rpc_params = scanner._build_rpc_params(
            Method.TOKEN_TOP_HOLDERS, {'contract_address': CONTRACT, 'offset': 5}
        )
        assert rpc_params == [CONTRACT, '0x5', '', '0x5']

    def test_holder_count_request_is_bare_contract_address(self) -> None:
        scanner = _make_scanner()
        rpc_params = scanner._build_rpc_params(
            Method.TOKEN_HOLDER_COUNT, {'contract_address': CONTRACT}
        )
        assert rpc_params == [CONTRACT]

    def test_wire_method_names(self) -> None:
        assert NodeRealScanner._WIRE_METHODS[Method.TOKEN_HOLDERS] == 'nr_getTokenHolders'
        assert NodeRealScanner._WIRE_METHODS[Method.TOKEN_TOP_HOLDERS] == 'nr_getTokenHolders'
        assert NodeRealScanner._WIRE_METHODS[Method.TOKEN_HOLDER_COUNT] == 'nr_getTokenHolderCount'


# ============================================================================
# Normalized item shape (checksum + Wei-like string value)
# ============================================================================


class TestParsers:
    def test_parse_token_holders_normalizes_shape_and_checksums(self) -> None:
        raw = {
            'pageKey': '',
            'details': [
                {'accountAddress': HOLDER_LOWER, 'tokenBalance': '0x2a520017d28dc000'},
            ],
        }
        items = _parse_token_holders(raw)
        assert items == [
            {
                'address': HOLDER_CHECKSUMMED,
                'value': str(int('2a520017d28dc000', 16)),
            }
        ]

    def test_parse_token_holders_non_dict_is_empty(self) -> None:
        assert _parse_token_holders(None) == []
        assert _parse_token_holders([1, 2, 3]) == []

    def test_parse_token_holders_skips_non_dict_entries(self) -> None:
        raw = {'pageKey': '', 'details': ['not-a-dict', {'accountAddress': HOLDER_LOWER}]}
        items = _parse_token_holders(raw)
        assert len(items) == 1
        assert items[0]['address'] == HOLDER_CHECKSUMMED
        # Missing tokenBalance defaults through _parse_hex_int's default=0.
        assert items[0]['value'] == '0'

    def test_parse_token_holder_count_hex_to_decimal_string(self) -> None:
        assert _parse_token_holder_count('0x123') == str(int('123', 16))
        assert _parse_token_holder_count('0x0') == '0'

    def test_parse_token_holder_count_coerces_to_int_cleanly(self) -> None:
        # Mirrors the mixin's `int(result or 0)` contract.
        assert int(_parse_token_holder_count('0x7b')) == 123

    def test_parse_token_holder_count_reads_the_live_nested_envelope(self) -> None:
        """The live API nests the count the docs describe as a bare scalar.

        Measured 2026-09-02 on ``bsc-mainnet``: BSC-USD answered
        ``{"result": {"result": "0x46b3f99"}}``. Read as the documented scalar
        this yielded 0 holders — a wrong answer indistinguishable from a token
        nobody holds.
        """
        assert _parse_token_holder_count({'result': '0x46b3f99'}) == '74137497'

    def test_parse_token_holder_count_refuses_an_unreadable_shape(self) -> None:
        with pytest.raises(ChainscanDataError):
            _parse_token_holder_count({'holders': 5})
        with pytest.raises(ChainscanDataError):
            _parse_token_holder_count(None)


# ============================================================================
# fetch_page: PageKey cursor threading
# ============================================================================


class TestFetchPageCursor:
    @pytest.mark.asyncio
    async def test_first_page_no_pagekey_sent(self) -> None:
        scanner = _make_scanner()
        network = _mock_network(
            scanner,
            [
                {
                    'pageKey': '',
                    'details': [{'accountAddress': HOLDER_LOWER, 'tokenBalance': '0x1'}],
                }
            ],
        )
        items, cursor = await scanner.fetch_page(
            Method.TOKEN_HOLDERS, {'contract_address': CONTRACT}
        )
        assert items == [{'address': HOLDER_CHECKSUMMED, 'value': '1'}]
        assert cursor is None  # empty response pageKey ends pagination
        sent_params = network.request.call_args.kwargs['json_data']['params']
        assert sent_params == [CONTRACT, '0x64', '']

    @pytest.mark.asyncio
    async def test_non_empty_pagekey_yields_continuation_cursor(self) -> None:
        scanner = _make_scanner()
        _mock_network(
            scanner,
            [
                {
                    'pageKey': 'next-cursor-abc',
                    'details': [{'accountAddress': HOLDER_LOWER, 'tokenBalance': '0x1'}],
                }
            ],
        )
        items, cursor = await scanner.fetch_page(
            Method.TOKEN_HOLDERS, {'contract_address': CONTRACT}
        )
        assert items
        assert cursor == {'pageKey': 'next-cursor-abc'}

    @pytest.mark.asyncio
    async def test_cursor_is_threaded_into_the_next_wire_call(self) -> None:
        scanner = _make_scanner()
        network = _mock_network(
            scanner,
            [
                {
                    'pageKey': 'cursor-1',
                    'details': [{'accountAddress': HOLDER_LOWER, 'tokenBalance': '0x1'}],
                },
                {
                    'pageKey': '',
                    'details': [{'accountAddress': CONTRACT, 'tokenBalance': '0x2'}],
                },
            ],
        )
        params = {'contract_address': CONTRACT}
        items_one, cursor_one = await scanner.fetch_page(Method.TOKEN_HOLDERS, params)
        assert cursor_one == {'pageKey': 'cursor-1'}

        merged = {**params, **cursor_one}
        items_two, cursor_two = await scanner.fetch_page(Method.TOKEN_HOLDERS, merged)
        assert cursor_two is None
        assert items_one != items_two

        second_call_params = network.request.call_args.kwargs['json_data']['params']
        assert second_call_params == [CONTRACT, '0x64', 'cursor-1']

    @pytest.mark.asyncio
    async def test_non_dict_response_ends_pagination_cleanly(self) -> None:
        scanner = _make_scanner()
        _mock_network(scanner, [None])
        items, cursor = await scanner.fetch_page(
            Method.TOKEN_HOLDERS, {'contract_address': CONTRACT}
        )
        assert items == []
        assert cursor is None


# ============================================================================
# The three methods no longer raise (used to be among the 11 refused ones)
# ============================================================================


class TestMethodsNoLongerRefused:
    def test_all_three_methods_are_declared(self) -> None:
        assert Method.TOKEN_HOLDERS in NodeRealScanner.SPECS
        assert Method.TOKEN_TOP_HOLDERS in NodeRealScanner.SPECS
        assert Method.TOKEN_HOLDER_COUNT in NodeRealScanner.SPECS

    @pytest.mark.asyncio
    async def test_call_token_holders_does_not_raise(self) -> None:
        scanner = _make_scanner()
        _mock_network(scanner, [{'pageKey': '', 'details': []}])
        result = await scanner.call(Method.TOKEN_HOLDERS, contract_address=CONTRACT)
        assert result == []

    @pytest.mark.asyncio
    async def test_call_top_token_holders_does_not_raise(self) -> None:
        scanner = _make_scanner()
        _mock_network(scanner, [{'pageKey': '', 'details': []}])
        result = await scanner.call(Method.TOKEN_TOP_HOLDERS, contract_address=CONTRACT, offset=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_call_token_holder_count_does_not_raise(self) -> None:
        scanner = _make_scanner()
        _mock_network(scanner, ['0x2a'])
        result = await scanner.call(Method.TOKEN_HOLDER_COUNT, contract_address=CONTRACT)
        assert int(result) == 42
