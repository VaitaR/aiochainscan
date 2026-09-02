"""BlockScout V1 ``TOKEN_HOLDERS`` (``module=token&action=getTokenHolders``).

Etherscan's action name (``tokenholderlist``) really does answer "Unknown
action" on BlockScout's Etherscan-compat layer, but that is a naming
mismatch, not a missing capability: BlockScout's own action name works and
paginates for real. Verified live 2026-09-02 against ``eth.blockscout.com``
(see the class-level comment on ``BlockScoutV1.SPECS`` /
``RESULT_WINDOW_OVERRIDES`` for the raw probe numbers).

All tests here are offline — no network calls, fake ``Network.request``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from aiochainscan.domain.method import Method
from aiochainscan.scanners.blockscout_v1 import BlockScoutV1


class FakeNetwork:
    """Records requests, replays one canned response."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


def _scanner(network: FakeNetwork) -> BlockScoutV1:
    return BlockScoutV1(
        api_key='',
        network='eth',
        url_builder=MagicMock(),
        network_client=network,
    )


class TestTokenHoldersDeclared:
    async def test_declared_in_specs(self) -> None:
        scanner = _scanner(FakeNetwork([]))
        assert Method.TOKEN_HOLDERS in scanner.SPECS


class TestTokenHoldersNormalization:
    """BlockScout's own action already answers flat ``address``/``value`` —
    unlike Etherscan's nested ``TokenHolderAddress``/``TokenHolderQuantity``
    — but the item still needs EIP-55 checksumming and str-coerced value to
    match the shape ``etherscan_v2``/``blockscout_v2`` produce.
    """

    async def test_checksums_address_and_stringifies_value(self) -> None:
        raw = [
            {'address': '0x0000000000000000000000000000000000000001', 'value': '42'},
        ]
        network = FakeNetwork(raw)
        scanner = _scanner(network)
        result = await scanner.call(
            Method.TOKEN_HOLDERS,
            contract_address='0xAbC0000000000000000000000000000000000d',
            page=1,
            offset=10,
        )
        # Unified shape: exactly {'address', 'value'} (no leftover wire keys),
        # value coerced to str. Checksum non-triviality is covered by
        # test_checksum_changes_mixed_case_address below (this fixture's
        # address happens to be checksum-invariant).
        assert result == [{'address': '0x0000000000000000000000000000000000000001', 'value': '42'}]
        assert set(result[0].keys()) == {'address', 'value'}

    async def test_checksum_changes_mixed_case_address(self) -> None:
        # A real BlockScout holder address that differs from its checksum
        # form once mixed-cased, so the assertion is non-trivial.
        lower = '0x8ba1f109551bd432803012645ac136ddd64dba72'.lower()
        raw = [{'address': lower, 'value': '7'}]
        network = FakeNetwork(raw)
        scanner = _scanner(network)
        result = await scanner.call(
            Method.TOKEN_HOLDERS, contract_address='0xtoken', page=1, offset=10
        )
        assert result[0]['address'] != lower
        assert result[0]['address'].lower() == lower
        assert result[0]['value'] == '7'

    async def test_non_list_response_yields_empty(self) -> None:
        network = FakeNetwork({'unexpected': 'shape'})
        scanner = _scanner(network)
        result = await scanner.call(
            Method.TOKEN_HOLDERS, contract_address='0xtoken', page=1, offset=10
        )
        assert result == []

    async def test_missing_value_defaults_to_zero_string(self) -> None:
        raw = [{'address': '0x0000000000000000000000000000000000000002'}]
        network = FakeNetwork(raw)
        scanner = _scanner(network)
        result = await scanner.call(
            Method.TOKEN_HOLDERS, contract_address='0xtoken', page=1, offset=10
        )
        assert result[0]['value'] == '0'


class TestTokenHoldersWireParams:
    """The SPEC must hit BlockScout's own action name, never Etherscan's."""

    async def test_uses_blockscout_action_name(self) -> None:
        network = FakeNetwork([])
        scanner = _scanner(network)
        await scanner.call(
            Method.TOKEN_HOLDERS,
            contract_address='0xTokenAddr',
            page=2,
            offset=50,
        )
        call = network.calls[0]
        assert call['method'] == 'GET'
        params = call['params']
        assert params['module'] == 'token'
        assert params['action'] == 'getTokenHolders'
        assert params['action'] != 'tokenholderlist'
        assert params['contractaddress'] == '0xTokenAddr'
        assert params['page'] == 2
        assert params['offset'] == 50


class TestTokenHoldersPageSizeClamp:
    """An oversized ``offset`` is clamped by the INHERITED
    ``EtherscanLikeScanner.fetch_page``/``max_page_size`` machinery
    (``BlockScoutV1.max_page_size = API_MAX_OFFSET_ETHERSCAN`` already
    declared before this change) — not by anything new here.
    """

    async def test_oversized_offset_clamped_to_max_page_size(self) -> None:
        # A full max_page_size-sized page proves the clamp actually ran: an
        # unclamped offset=20000 asking for < max_page_size items back would
        # look identical to "short page => no more data".
        from aiochainscan.constants import API_MAX_OFFSET_ETHERSCAN

        raw = [
            {'address': f'0x{i:040x}', 'value': str(i)}
            for i in range(1, API_MAX_OFFSET_ETHERSCAN + 1)
        ]
        network = FakeNetwork(raw)
        scanner = _scanner(network)
        items, next_cursor = await scanner.fetch_page(
            Method.TOKEN_HOLDERS,
            {'contract_address': '0xtoken', 'page': 1, 'offset': 20_000},
        )
        call = network.calls[0]
        assert call['params']['offset'] == API_MAX_OFFSET_ETHERSCAN
        assert len(items) == API_MAX_OFFSET_ETHERSCAN
        # A full page (>= offset asked) still signals "maybe more" via a cursor.
        assert next_cursor == {'page': 2, 'offset': API_MAX_OFFSET_ETHERSCAN}


class TestTokenHoldersResultWindow:
    """``result_window_for`` must report the substantiated conclusion:
    ``None`` (paginates to exhaustion — see the live probe in the
    class-level comment), not the inherited 10_000 account-endpoint window.
    """

    async def test_result_window_is_none(self) -> None:
        scanner = _scanner(FakeNetwork([]))
        assert scanner.result_window_for(Method.TOKEN_HOLDERS) is None

    async def test_other_methods_keep_inherited_window(self) -> None:
        from aiochainscan.constants import API_MAX_OFFSET_ETHERSCAN

        scanner = _scanner(FakeNetwork([]))
        assert scanner.result_window_for(Method.ACCOUNT_TRANSACTIONS) == API_MAX_OFFSET_ETHERSCAN
