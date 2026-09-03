"""Token holders endpoints (P0.3): list / top / count + streaming aggregation.

Covers the three ``Method`` values (``TOKEN_HOLDERS``, ``TOKEN_TOP_HOLDERS``,
``TOKEN_HOLDER_COUNT``), their scanner specs, response normalization to the
unified ``{'address', 'value'}`` item shape, pagination/streaming, and the
honest ``ValueError`` surface for scanners that do not declare the methods:

- ``etherscan`` v2: ``module=token`` ``tokenholderlist`` / ``topholders`` /
  ``tokenholdercount`` (verified against docs.etherscan.io).
- ``blockscout`` v2: native ``/api/v2/tokens/{addr}/holders`` plus the token
  info endpoint's ``holders_count``; top holders are NOT declared because the
  holders endpoint ordering is not a contract.
- ``blockscout`` v1 (Etherscan-compat REST): verified live to answer
  "Unknown action" for the token module holder actions → not declared.
- ``nodereal`` v1: ``nr_getTokenHoldings`` is *address* holdings (which tokens
  a wallet owns), not token holders → not declared.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.core.client import ChainscanClient
from aiochainscan.domain.method import Method
from aiochainscan.scanners._etherscan_like import EtherscanLikeScanner
from aiochainscan.scanners.base import holder_item
from aiochainscan.scanners.blockscout_v1 import BlockScoutV1
from aiochainscan.scanners.blockscout_v1 import _parse_token_holders as _parse_bs1_holders
from aiochainscan.scanners.blockscout_v2 import (
    BlockScoutV2Scanner,
    _parse_token_holder_count,
    _parse_token_holders,
)
from aiochainscan.scanners.etherscan_v2 import EtherscanV2
from aiochainscan.scanners.etherscan_v2 import _parse_token_holders as _parse_eth_holders
from aiochainscan.scanners.nodereal import NodeRealScanner
from aiochainscan.scanners.nodereal import _parse_token_holders as _parse_nr_holders

TOKEN_CONTRACT = '0xDaC17f958D2ee523A2206208994597c13d831EC7'  # USDT (true EIP-55)
HOLDER_ONE = '0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed'
HOLDER_ONE_LOWER = HOLDER_ONE.lower()
HOLDER_TWO = '0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359'
HOLDER_TWO_LOWER = HOLDER_TWO.lower()

HOLDER_METHODS = (Method.TOKEN_HOLDERS, Method.TOKEN_TOP_HOLDERS, Method.TOKEN_HOLDER_COUNT)


class FakeNetwork:
    """Minimal Network stand-in: records requests, replays canned responses."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def get(self, **kwargs: Any) -> Any:
        return await self.request(method='GET', **kwargs)

    async def post(self, **kwargs: Any) -> Any:
        return await self.request(method='POST', **kwargs)


def _etherscan(network: FakeNetwork) -> EtherscanV2:
    return EtherscanV2(
        api_key='test_key',
        network='main',
        url_builder=MagicMock(),
        network_client=network,
    )


def _blockscout(network: FakeNetwork) -> BlockScoutV2Scanner:
    return BlockScoutV2Scanner(
        api_key='',
        network='ethereum',
        url_builder=MagicMock(),
        network_client=network,
    )


def _nodereal(network: FakeNetwork) -> NodeRealScanner:
    return NodeRealScanner(
        api_key='test_key',
        network='bsc',
        url_builder=MagicMock(),
        network_client=network,
    )


def _bare_client(scanner_name: str, scanner_version: str, scanner: Any) -> ChainscanClient:
    """Build a ChainscanClient shell around an injected scanner (no real wiring)."""
    client = ChainscanClient.__new__(ChainscanClient)
    client.scanner_name = scanner_name
    client.scanner_version = scanner_version
    client.api_kind = 'test'
    client.network = 'main'
    client.api_key = ''
    client._scanner = scanner
    return client


def _etherscan_holder_page(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    """Payload the real Network seam delivers for a holders page.

    ``Network._handle_response`` extracts the Etherscan envelope's ``result``
    BEFORE ``spec.parse_response`` runs, so scanners and their parsers see the
    bare item list — fakes must sit on that seam, not replay full envelopes.
    """
    return entries


# ============================================================================
# The shared holder-item factory
# ============================================================================


class TestHolderItemFactory:
    """``base.holder_item`` is the ONE builder of the unified holder item
    shape (``{'address': EIP-55 str, 'value': str}``); the four scanner
    parsers keep only their provider-specific field extraction."""

    def test_checksums_address_and_stringifies_value(self) -> None:
        assert holder_item(HOLDER_ONE_LOWER, 1000) == {'address': HOLDER_ONE, 'value': '1000'}
        assert holder_item(HOLDER_ONE, '42') == {'address': HOLDER_ONE, 'value': '42'}

    def test_none_value_becomes_zero(self) -> None:
        assert holder_item(HOLDER_ONE, None) == {'address': HOLDER_ONE, 'value': '0'}

    def test_other_falsy_values_become_zero(self) -> None:
        assert holder_item(HOLDER_ONE, '') == {'address': HOLDER_ONE, 'value': '0'}
        assert holder_item(HOLDER_ONE, 0) == {'address': HOLDER_ONE, 'value': '0'}

    def test_undigestable_address_passes_through(self) -> None:
        assert holder_item('not-an-address', '1') == {'address': 'not-an-address', 'value': '1'}

    @pytest.mark.parametrize(
        ('parser', 'payload'),
        [
            (
                _parse_eth_holders,
                [{'TokenHolderAddress': HOLDER_ONE_LOWER, 'TokenHolderQuantity': '5'}],
            ),
            (_parse_bs1_holders, [{'address': HOLDER_ONE_LOWER, 'value': '5'}]),
            (
                _parse_token_holders,
                {'items': [{'address': {'hash': HOLDER_ONE_LOWER}, 'value': '5'}]},
            ),
            (
                _parse_nr_holders,
                {'details': [{'accountAddress': HOLDER_ONE_LOWER, 'tokenBalance': '0x5'}]},
            ),
        ],
        ids=['etherscan-v2', 'blockscout-v1', 'blockscout-v2', 'nodereal'],
    )
    def test_parsed_items_carry_exactly_the_unified_keys(self, parser: Any, payload: Any) -> None:
        items = parser(payload)
        assert items == [{'address': HOLDER_ONE, 'value': '5'}]
        assert set(items[0].keys()) == {'address', 'value'}


# ============================================================================
# Method enum
# ============================================================================


class TestMethodEnum:
    def test_token_holders_methods_exist(self) -> None:
        for name in ('TOKEN_HOLDERS', 'TOKEN_TOP_HOLDERS', 'TOKEN_HOLDER_COUNT'):
            assert hasattr(Method, name)
            assert isinstance(getattr(Method, name), Method)

    def test_method_str_representation(self) -> None:
        assert str(Method.TOKEN_HOLDERS) == 'Token Holders'
        assert str(Method.TOKEN_TOP_HOLDERS) == 'Token Top Holders'
        assert str(Method.TOKEN_HOLDER_COUNT) == 'Token Holder Count'


# ============================================================================
# Etherscan v2: specs and normalization
# ============================================================================


class TestEtherscanV2Specs:
    def test_token_holders_spec(self) -> None:
        spec = EtherscanV2.SPECS[Method.TOKEN_HOLDERS]
        assert spec.http_method == 'GET'
        assert spec.path == '/api'
        assert spec.query['module'] == 'token'
        assert spec.query['action'] == 'tokenholderlist'
        assert spec.query['chainid'] == '{chain_id}'
        assert spec.param_map == {
            'contract_address': 'contractaddress',
            'page': 'page',
            'offset': 'offset',
        }

    def test_top_holders_spec(self) -> None:
        spec = EtherscanV2.SPECS[Method.TOKEN_TOP_HOLDERS]
        assert spec.http_method == 'GET'
        assert spec.query['module'] == 'token'
        assert spec.query['action'] == 'topholders'
        assert spec.query['chainid'] == '{chain_id}'
        # topholders has no page param: offset is the result limit (max 1000).
        assert spec.param_map == {'contract_address': 'contractaddress', 'offset': 'offset'}

    def test_holder_count_spec(self) -> None:
        spec = EtherscanV2.SPECS[Method.TOKEN_HOLDER_COUNT]
        assert spec.http_method == 'GET'
        assert spec.query['module'] == 'token'
        assert spec.query['action'] == 'tokenholdercount'
        assert spec.query['chainid'] == '{chain_id}'
        assert spec.param_map == {'contract_address': 'contractaddress'}

    def test_param_mapping(self) -> None:
        spec = EtherscanV2.SPECS[Method.TOKEN_HOLDERS]
        params = spec.map_params(contract_address=TOKEN_CONTRACT, page=2, offset=50)
        assert params['module'] == 'token'
        assert params['action'] == 'tokenholderlist'
        assert params['chainid'] == '{chain_id}'
        assert params['contractaddress'] == TOKEN_CONTRACT
        assert params['page'] == 2
        assert params['offset'] == 50


class TestEtherscanV2Normalization:
    def test_parser_sees_post_unwrap_payload(self) -> None:
        """Regression: the parser runs AFTER Network._handle_response has
        extracted the envelope's ``result`` — its primary input is the bare
        holder-item list, never ``{'result': [...]}``."""
        payload = [
            {'TokenHolderAddress': HOLDER_ONE, 'TokenHolderQuantity': '1000'},
            {'TokenHolderAddress': HOLDER_TWO_LOWER, 'TokenHolderQuantity': '2000'},
        ]
        assert _parse_eth_holders(payload) == [
            {'address': HOLDER_ONE, 'value': '1000'},
            {'address': HOLDER_TWO, 'value': '2000'},
        ]

    def test_parser_tolerates_full_envelope(self) -> None:
        """A ``{'result': [...]}`` envelope still parses (defensive path)."""
        envelope = {
            'status': '1',
            'message': 'OK',
            'result': [{'TokenHolderAddress': HOLDER_ONE, 'TokenHolderQuantity': '7'}],
        }
        assert _parse_eth_holders(envelope) == [{'address': HOLDER_ONE, 'value': '7'}]

    def test_parser_normalizes_pascal_case_fields(self) -> None:
        page = _etherscan_holder_page(
            [
                {'TokenHolderAddress': HOLDER_ONE, 'TokenHolderQuantity': '1000'},
                {'TokenHolderAddress': HOLDER_TWO_LOWER, 'TokenHolderQuantity': '2000'},
            ]
        )
        items = _parse_eth_holders(page)
        assert items == [
            {'address': HOLDER_ONE, 'value': '1000'},
            {'address': HOLDER_TWO, 'value': '2000'},
        ]

    def test_parser_checksums_lowercase_addresses(self) -> None:
        page = _etherscan_holder_page(
            [{'TokenHolderAddress': HOLDER_ONE_LOWER, 'TokenHolderQuantity': '42'}]
        )
        assert _parse_eth_holders(page) == [{'address': HOLDER_ONE, 'value': '42'}]

    def test_parser_preserves_top_holder_address_type(self) -> None:
        page = _etherscan_holder_page(
            [
                {
                    'TokenHolderAddress': HOLDER_ONE,
                    'TokenHolderQuantity': '1000',
                    'TokenHolderAddressType': 'C',
                }
            ]
        )
        items = _parse_eth_holders(page)
        assert items[0]['TokenHolderAddressType'] == 'C'
        assert items[0]['address'] == HOLDER_ONE

    def test_parser_non_list_result_returns_empty(self) -> None:
        assert _parse_eth_holders({'status': '0', 'message': 'No data', 'result': None}) == []
        assert _parse_eth_holders({'status': '1', 'message': 'OK', 'result': '30506'}) == []


class TestEtherscanV2Requests:
    async def test_call_holders_query_params(self) -> None:
        network = FakeNetwork([_etherscan_holder_page([])])
        scanner = _etherscan(network)
        await scanner.call(
            Method.TOKEN_HOLDERS, contract_address=TOKEN_CONTRACT, page=1, offset=100
        )
        assert len(network.calls) == 1
        params = network.calls[0]['params']
        assert params['module'] == 'token'
        assert params['action'] == 'tokenholderlist'
        assert params['chainid'] == scanner.chain_id
        assert params['contractaddress'] == TOKEN_CONTRACT
        assert params['page'] == 1
        assert params['offset'] == 100
        assert params['apikey'] == 'test_key'

    async def test_call_parses_post_unwrap_network_payload(self) -> None:
        """Regression (envelope seam): a Network that already unwrapped the
        Etherscan ``result`` (the real transport behavior) must yield parsed
        holders, not a silently empty list."""
        network = FakeNetwork(
            [
                _etherscan_holder_page(
                    [{'TokenHolderAddress': HOLDER_ONE, 'TokenHolderQuantity': '5'}]
                )
            ]
        )
        scanner = _etherscan(network)
        items = await scanner.call(Method.TOKEN_HOLDERS, contract_address=TOKEN_CONTRACT)
        assert items == [{'address': HOLDER_ONE, 'value': '5'}]

    async def test_call_top_holders_uses_offset_limit(self) -> None:
        network = FakeNetwork([_etherscan_holder_page([])])
        scanner = _etherscan(network)
        await scanner.call(Method.TOKEN_TOP_HOLDERS, contract_address=TOKEN_CONTRACT, offset=25)
        params = network.calls[0]['params']
        assert params['action'] == 'topholders'
        assert params['offset'] == 25
        assert 'page' not in params

    async def test_call_holder_count_scalar(self) -> None:
        # Post-unwrap payload: the real Network delivers the bare scalar.
        network = FakeNetwork(['30506'])
        scanner = _etherscan(network)
        result = await scanner.call(Method.TOKEN_HOLDER_COUNT, contract_address=TOKEN_CONTRACT)
        assert result == '30506'
        params = network.calls[0]['params']
        assert params['action'] == 'tokenholdercount'
        assert params['contractaddress'] == TOKEN_CONTRACT


class TestEtherscanV2FetchPage:
    async def test_full_page_returns_next_page_cursor(self) -> None:
        entries = [
            {'TokenHolderAddress': HOLDER_ONE, 'TokenHolderQuantity': str(i)} for i in range(3)
        ]
        network = FakeNetwork([_etherscan_holder_page(entries)])
        scanner = _etherscan(network)
        items, cursor = await scanner.fetch_page(
            Method.TOKEN_HOLDERS,
            {'contract_address': TOKEN_CONTRACT, 'page': 1, 'offset': 3},
        )
        assert len(items) == 3
        assert items[0] == {'address': HOLDER_ONE, 'value': '0'}
        assert cursor == {'page': 2, 'offset': 3}

    async def test_partial_page_terminates(self) -> None:
        entries = [{'TokenHolderAddress': HOLDER_ONE, 'TokenHolderQuantity': '1'}]
        network = FakeNetwork([_etherscan_holder_page(entries)])
        scanner = _etherscan(network)
        _, cursor = await scanner.fetch_page(
            Method.TOKEN_HOLDERS,
            {'contract_address': TOKEN_CONTRACT, 'page': 1, 'offset': 3},
        )
        assert cursor is None

    async def test_empty_page_terminates(self) -> None:
        network = FakeNetwork([_etherscan_holder_page([])])
        scanner = _etherscan(network)
        items, cursor = await scanner.fetch_page(
            Method.TOKEN_HOLDERS,
            {'contract_address': TOKEN_CONTRACT, 'page': 9, 'offset': 3},
        )
        assert items == []
        assert cursor is None


# ============================================================================
# Etherscan v2: client-level pagination and streaming
# ============================================================================


class TestEtherscanClientStreaming:
    async def test_get_all_token_holders_walks_pages(self) -> None:
        def entry(addr: str, qty: str) -> dict[str, str]:
            return {'TokenHolderAddress': addr, 'TokenHolderQuantity': qty}

        # get_all_token_holders aggregates with batch_size=1000: two full
        # pages then a partial one exercise the page/offset cursor walk.
        full_page = _etherscan_holder_page(
            [entry(HOLDER_ONE, str(i)) for i in range(1000)] + [entry(HOLDER_TWO, '2')]
        )
        partial_page = _etherscan_holder_page([entry(HOLDER_ONE, '3')])
        network = FakeNetwork([full_page, full_page, partial_page])
        client = _bare_client('etherscan', 'v2', _etherscan(network))

        holders = await client.get_all_token_holders(TOKEN_CONTRACT)

        assert len(holders) == 2003  # 1001 + 1001 + partial page of 1
        assert holders[0] == {'address': HOLDER_ONE, 'value': '0'}
        assert holders[999] == {'address': HOLDER_ONE, 'value': '999'}
        assert holders[1000] == {'address': HOLDER_TWO, 'value': '2'}
        assert holders[1001] == {'address': HOLDER_ONE, 'value': '0'}  # page 2 restart
        assert holders[-1] == {'address': HOLDER_ONE, 'value': '3'}
        # Three page fetches: page=1, page=2, then the terminating partial page.
        pages = [call['params']['page'] for call in network.calls]
        assert pages == [1, 2, 3]

    async def test_iter_token_holders_streaming_yields_batches(self) -> None:
        page_one = _etherscan_holder_page(
            [{'TokenHolderAddress': HOLDER_ONE, 'TokenHolderQuantity': str(i)} for i in range(2)]
        )
        page_two = _etherscan_holder_page(
            [{'TokenHolderAddress': HOLDER_TWO, 'TokenHolderQuantity': str(i)} for i in range(1)]
        )
        network = FakeNetwork([page_one, page_two])
        client = _bare_client('etherscan', 'v2', _etherscan(network))

        batches = [
            batch
            async for batch in client.iter_token_holders_streaming(TOKEN_CONTRACT, batch_size=2)
        ]

        assert [len(batch) for batch in batches] == [2, 1]
        assert batches[0][0]['address'] == HOLDER_ONE
        assert batches[1][0]['address'] == HOLDER_TWO

    async def test_streaming_reports_progress(self) -> None:
        page_one = _etherscan_holder_page(
            [{'TokenHolderAddress': HOLDER_ONE, 'TokenHolderQuantity': '1'}] * 2
        )
        partial = _etherscan_holder_page(
            [{'TokenHolderAddress': HOLDER_TWO, 'TokenHolderQuantity': '2'}]
        )
        network = FakeNetwork([page_one, partial])
        client = _bare_client('etherscan', 'v2', _etherscan(network))

        events: list[dict[str, Any]] = []

        async def on_progress(**kwargs: Any) -> None:
            events.append(kwargs)

        async for _ in client.iter_token_holders_streaming(
            TOKEN_CONTRACT, batch_size=2, on_progress=on_progress
        ):
            pass

        assert events == [
            {
                'fetched': 2,
                'total_expected': None,
                'current_page': 1,
                'operation': 'token_holders',
            },
            {
                'fetched': 3,
                'total_expected': None,
                'current_page': 2,
                'operation': 'token_holders',
            },
        ]

    async def test_non_positive_batch_size_rejected_before_fetch(self) -> None:
        network = FakeNetwork([])
        client = _bare_client('etherscan', 'v2', _etherscan(network))
        with pytest.raises(ValueError, match='batch_size must be at least 1'):
            async for _ in client.iter_token_holders_streaming(TOKEN_CONTRACT, batch_size=0):
                pass
        assert network.calls == []


# ============================================================================
# BlockScout v2: specs and normalization
# ============================================================================


class TestBlockScoutV2Specs:
    def test_token_holders_spec(self) -> None:
        spec = BlockScoutV2Scanner.SPECS[Method.TOKEN_HOLDERS]
        assert spec.http_method == 'GET'
        assert spec.path == '/api/v2/tokens/{contract_address}/holders'
        assert spec.requires_api_key is False
        assert 'contract_address' in spec.param_map
        # next_page_params cursor keys must be declared to reach the query.
        for cursor_key in ('value', 'address_hash', 'items_count'):
            assert cursor_key in spec.param_map

    def test_holder_count_spec(self) -> None:
        spec = BlockScoutV2Scanner.SPECS[Method.TOKEN_HOLDER_COUNT]
        assert spec.http_method == 'GET'
        assert spec.path == '/api/v2/tokens/{contract_address}'
        assert spec.requires_api_key is False
        assert spec.parser is _parse_token_holder_count

    def test_top_holders_not_declared(self) -> None:
        """No top-holder endpoint exists; holders ordering is not a contract."""
        assert Method.TOKEN_TOP_HOLDERS not in BlockScoutV2Scanner.SPECS
        assert not BlockScoutV2Scanner(
            api_key='', network='ethereum', url_builder=MagicMock()
        ).supports_method(Method.TOKEN_TOP_HOLDERS)


class TestBlockScoutV2Normalization:
    def test_parse_holders_flattens_nested_address(self) -> None:
        response = {
            'items': [
                {
                    'address': {
                        'hash': HOLDER_ONE_LOWER,
                        'ens_domain_name': None,
                        'is_contract': True,
                    },
                    'token_id': None,
                    'value': '824331597828298768884482',
                },
                {'address': {'hash': HOLDER_TWO}, 'token_id': None, 'value': 15},
            ],
            'next_page_params': {
                'value': '1',
                'address_hash': HOLDER_ONE_LOWER,
                'items_count': 50,
            },
        }
        items = _parse_token_holders(response)
        assert items == [
            {'address': HOLDER_ONE, 'value': '824331597828298768884482'},
            {'address': HOLDER_TWO, 'value': '15'},
        ]

    def test_parse_holders_missing_items(self) -> None:
        assert _parse_token_holders({}) == []
        assert _parse_token_holders({'next_page_params': {}}) == []

    def test_parse_holder_count_prefers_holders_count(self) -> None:
        assert _parse_token_holder_count({'holders_count': 12345, 'name': 'GNO'}) == 12345

    def test_parse_holder_count_accepts_legacy_holders_key(self) -> None:
        assert _parse_token_holder_count({'holders': 7}) == 7

    def test_parse_holder_count_missing_returns_zero(self) -> None:
        assert _parse_token_holder_count({'name': 'GNO'}) == 0
        assert _parse_token_holder_count({}) == 0


class TestBlockScoutV2Requests:
    async def test_call_holders_builds_path_and_parses(self) -> None:
        network = FakeNetwork(
            [
                {
                    'items': [{'address': {'hash': HOLDER_ONE}, 'value': '10'}],
                    'next_page_params': None,
                }
            ]
        )
        scanner = _blockscout(network)
        items = await scanner.call(Method.TOKEN_HOLDERS, contract_address=TOKEN_CONTRACT)
        assert items == [{'address': HOLDER_ONE, 'value': '10'}]
        call = network.calls[0]
        assert call['method'] == 'GET'
        assert call['url'] == (
            f'https://eth.blockscout.com/api/v2/tokens/{TOKEN_CONTRACT}/holders'
        )
        assert not call.get('params')

    async def test_call_holder_count(self) -> None:
        network = FakeNetwork([{'holders_count': 30506, 'symbol': 'USDT'}])
        scanner = _blockscout(network)
        result = await scanner.call(Method.TOKEN_HOLDER_COUNT, contract_address=TOKEN_CONTRACT)
        assert result == 30506
        assert (
            network.calls[0]['url'] == f'https://eth.blockscout.com/api/v2/tokens/{TOKEN_CONTRACT}'
        )

    async def test_top_holders_raises_value_error(self) -> None:
        scanner = _blockscout(FakeNetwork([]))
        with pytest.raises(ValueError, match='not supported'):
            await scanner.call(
                Method.TOKEN_TOP_HOLDERS, contract_address=TOKEN_CONTRACT, offset=10
            )


class TestBlockScoutV2FetchPage:
    async def test_fetch_page_normalizes_items_and_keeps_cursor(self) -> None:
        response = {
            'items': [
                {'address': {'hash': HOLDER_ONE_LOWER}, 'value': '5'},
                {'address': {'hash': HOLDER_TWO}, 'value': '6'},
            ],
            'next_page_params': {
                'value': '6',
                'address_hash': HOLDER_TWO_LOWER,
                'items_count': 50,
            },
        }
        network = FakeNetwork([response])
        scanner = _blockscout(network)
        items, cursor = await scanner.fetch_page(
            Method.TOKEN_HOLDERS, {'contract_address': TOKEN_CONTRACT}
        )
        assert items == [
            {'address': HOLDER_ONE, 'value': '5'},
            {'address': HOLDER_TWO, 'value': '6'},
        ]
        assert cursor == {'value': '6', 'address_hash': HOLDER_TWO_LOWER, 'items_count': 50}

    async def test_merged_cursor_reaches_next_query(self) -> None:
        cursor = {'value': '6', 'address_hash': HOLDER_TWO_LOWER, 'items_count': 50}
        page_two = {'items': [], 'next_page_params': None}
        network = FakeNetwork([page_two])
        scanner = _blockscout(network)
        await scanner.fetch_page(
            Method.TOKEN_HOLDERS, {'contract_address': TOKEN_CONTRACT, **cursor}
        )
        query = network.calls[0]['params']
        assert query == cursor

    async def test_remote_cursor_cannot_replace_path_contract(self) -> None:
        """The holders cursor must not rewrite the requested token contract."""
        response = {
            'items': [{'address': {'hash': HOLDER_ONE}, 'value': '5'}],
            'next_page_params': {
                'value': '5',
                'address_hash': HOLDER_ONE_LOWER,
                'items_count': 50,
                'contract_address': '0x0000000000000000000000000000000000000001',
            },
        }
        network = FakeNetwork([response])
        scanner = _blockscout(network)
        _, cursor = await scanner.fetch_page(
            Method.TOKEN_HOLDERS, {'contract_address': TOKEN_CONTRACT}
        )
        assert 'contract_address' not in (cursor or {})

    async def test_client_streaming_walks_cursor_pages(self) -> None:
        page_one = {
            'items': [{'address': {'hash': HOLDER_ONE}, 'value': '5'}],
            'next_page_params': {
                'value': '5',
                'address_hash': HOLDER_ONE_LOWER,
                'items_count': 50,
            },
        }
        page_two = {
            'items': [{'address': {'hash': HOLDER_TWO}, 'value': '6'}],
            'next_page_params': None,
        }
        network = FakeNetwork([page_one, page_two])
        client = _bare_client('blockscout', 'v2', _blockscout(network))

        batches = [
            batch
            async for batch in client.iter_token_holders_streaming(TOKEN_CONTRACT, batch_size=50)
        ]

        assert batches == [
            [{'address': HOLDER_ONE, 'value': '5'}],
            [{'address': HOLDER_TWO, 'value': '6'}],
        ]
        assert len(network.calls) == 2

    async def test_client_get_all_token_holders(self) -> None:
        page_one = {
            'items': [{'address': {'hash': HOLDER_ONE}, 'value': '5'}],
            'next_page_params': {
                'value': '5',
                'address_hash': HOLDER_ONE_LOWER,
                'items_count': 50,
            },
        }
        page_two = {
            'items': [{'address': {'hash': HOLDER_TWO}, 'value': '6'}],
            'next_page_params': None,
        }
        network = FakeNetwork([page_one, page_two])
        client = _bare_client('blockscout', 'v2', _blockscout(network))

        holders = await client.get_all_token_holders(TOKEN_CONTRACT)

        assert holders == [
            {'address': HOLDER_ONE, 'value': '5'},
            {'address': HOLDER_TWO, 'value': '6'},
        ]


# ============================================================================
# Honest ValueError surface: nodereal + blockscout v1
# ============================================================================


class TestNoderealHolderMethodsUseTheHoldersEndpoint:
    """The trap this guards: ``nr_getTokenHoldings`` is *address* holdings.

    It answers "what does this address hold", not "who holds this token", so
    wiring a holder method onto it would return a plausible-looking list of
    the wrong thing. The holder methods must ride ``nr_getTokenHolders``.
    """

    def test_specs_declared(self) -> None:
        for method in HOLDER_METHODS:
            assert method in NodeRealScanner.SPECS

    def test_holder_methods_do_not_ride_the_holdings_endpoint(self) -> None:
        def wire(method: Method) -> str | None:
            return NodeRealScanner.SPECS[method].wire_method

        assert wire(Method.TOKEN_HOLDERS) == 'nr_getTokenHolders'
        assert wire(Method.TOKEN_TOP_HOLDERS) == 'nr_getTokenHolders'
        assert wire(Method.TOKEN_HOLDER_COUNT) == 'nr_getTokenHolderCount'
        # The endpoint they must NOT be confused with, still serving portfolios.
        assert wire(Method.ACCOUNT_TOKEN_PORTFOLIO) == 'nr_getTokenHoldings'


class TestBlockScoutV1HolderMethodCoverage:
    """Live-verified 2026-09-02 against ``eth.blockscout.com``.

    BlockScout implements a holder list under its OWN action name
    (``token/getTokenHolders``); only *Etherscan's* action names
    (``tokenholderlist``/``tokenholdercount``) answer "Unknown action" there,
    which is why the shared Etherscan-like base must not declare them.
    """

    def test_specs_absent_from_etherscan_like_base(self) -> None:
        for method in HOLDER_METHODS:
            assert method not in EtherscanLikeScanner.SPECS

    def test_blockscout_v1_declares_only_the_holder_list(self) -> None:
        assert Method.TOKEN_HOLDERS in BlockScoutV1.SPECS
        # Probed under three action-name spellings, all "Unknown action":
        # getTokenHolderCount, tokenholdercount, getTokenHoldersCount.
        assert Method.TOKEN_HOLDER_COUNT not in BlockScoutV1.SPECS
        # No ordering guarantee is documented for getTokenHolders.
        assert Method.TOKEN_TOP_HOLDERS not in BlockScoutV1.SPECS


# ============================================================================
# Convenience methods (mocked call)
# ============================================================================


def _mocked_client() -> tuple[ChainscanClient, AsyncMock]:
    with MagicMock():
        client = ChainscanClient.__new__(ChainscanClient)
    mock_call = AsyncMock()
    client.call = mock_call  # type: ignore[method-assign]
    return client, mock_call


class TestConvenienceMethods:
    async def test_get_token_holders_delegates(self) -> None:
        client, mock_call = _mocked_client()
        mock_call.return_value = [{'address': HOLDER_ONE, 'value': '1'}]
        result = await client.get_token_holders(TOKEN_CONTRACT, page=2, offset=50)
        mock_call.assert_awaited_once_with(
            Method.TOKEN_HOLDERS,
            contract_address=TOKEN_CONTRACT,
            page=2,
            offset=50,
        )
        assert result == [{'address': HOLDER_ONE, 'value': '1'}]

    async def test_get_token_holders_defaults(self) -> None:
        client, mock_call = _mocked_client()
        mock_call.return_value = []
        await client.get_token_holders(TOKEN_CONTRACT.lower())
        mock_call.assert_awaited_once_with(
            Method.TOKEN_HOLDERS,
            contract_address=TOKEN_CONTRACT,  # checksummed via Address
            page=1,
            offset=100,
        )

    async def test_get_token_holders_non_list_returns_empty(self) -> None:
        client, mock_call = _mocked_client()
        mock_call.return_value = {'status': '0'}
        assert await client.get_token_holders(TOKEN_CONTRACT) == []

    async def test_get_top_token_holders_maps_limit_to_offset(self) -> None:
        client, mock_call = _mocked_client()
        mock_call.return_value = [{'address': HOLDER_ONE, 'value': '1'}]
        result = await client.get_top_token_holders(TOKEN_CONTRACT, limit=25)
        mock_call.assert_awaited_once_with(
            Method.TOKEN_TOP_HOLDERS,
            contract_address=TOKEN_CONTRACT,
            offset=25,
        )
        assert result == [{'address': HOLDER_ONE, 'value': '1'}]

    async def test_get_top_token_holders_rejects_non_positive_limit(self) -> None:
        client, mock_call = _mocked_client()
        with pytest.raises(ValueError, match='limit must be at least 1'):
            await client.get_top_token_holders(TOKEN_CONTRACT, limit=0)
        mock_call.assert_not_awaited()

    async def test_get_token_holder_count_converts_string(self) -> None:
        client, mock_call = _mocked_client()
        mock_call.return_value = '30506'
        result = await client.get_token_holder_count(TOKEN_CONTRACT)
        mock_call.assert_awaited_once_with(
            Method.TOKEN_HOLDER_COUNT, contract_address=TOKEN_CONTRACT
        )
        assert result == 30506
        assert isinstance(result, int)

    async def test_get_token_holder_count_passthrough_int(self) -> None:
        client, mock_call = _mocked_client()
        mock_call.return_value = 30506
        assert await client.get_token_holder_count(TOKEN_CONTRACT) == 30506

    async def test_invalid_contract_address_rejected(self) -> None:
        client, _ = _mocked_client()
        with pytest.raises(ValueError, match='Invalid EVM address'):
            await client.get_token_holders('0xnotanaddress')
