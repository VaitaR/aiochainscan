"""
Coverage tests for the BlockScout V2 declared-Method gaps filled here:
``ACCOUNT_ERC20_TRANSFERS``, ``ACCOUNT_INTERNAL_TXS``, ``CONTRACT_SOURCE``,
``ACCOUNT_NFT_PORTFOLIO``.

``TX_BY_HASH`` was investigated and deliberately NOT declared: see the
comment on ``BlockScoutV2Scanner.SPECS`` (blockscout_v2.py) for why -- its
native transaction envelope carries a colliding top-level ``result`` field
that the shared ``Network._handle_response`` envelope-unwrapping silently
reduces to a bare string.

Fixtures are trimmed captures from the live keyless
``https://eth.blockscout.com/api/v2`` instance (2026-09-02); see the
parser docstrings in ``blockscout_v2.py`` for the full untrimmed shapes
observed.
"""

from __future__ import annotations

from typing import Any

import pytest

from aiochainscan.chain_registry import ScannerTarget
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.url_builder import UrlBuilder
from aiochainscan.domain.method import Method
from aiochainscan.exceptions import BlockRangeNotSupportedError
from aiochainscan.scanners.blockscout_v2 import (
    BlockScoutV2Scanner,
    _parse_internal_transactions,
    _parse_nft_portfolio,
    _parse_raw,
    _parse_token_transfers,
)
from tests.conftest import FakeNetwork

# ============================================================================
# Fixtures: trimmed real payloads (live capture, eth.blockscout.com, 2026-09-02)
# ============================================================================

TOKEN_TRANSFERS_PAGE_1: dict[str, Any] = {
    'items': [
        {
            'block_number': 25888691,
            'from': {'hash': '0x922804717cd4ffFD1cb1Bf81eea7FF06CAf94aA9'},
            'log_index': 51,
            'method': '0x1c7c27c8',
            'timestamp': '2026-09-02T09:23:59.000000Z',
            'to': {'hash': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'},
            'token': {
                'address_hash': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
                'decimals': '6',
                'symbol': 'USDT',
                'type': 'ERC-20',
            },
            'token_type': 'ERC-20',
            'total': {'decimals': '6', 'value': '1500000'},
            'transaction_hash': '0x9c0807a414cef03654ed8fb62234577db919dd25e0378a85abb675db1c07136e',
            'type': 'token_transfer',
        }
    ],
    'next_page_params': {'index': 92, 'block_number': 25818613},
}

TOKEN_TRANSFERS_PAGE_2: dict[str, Any] = {
    'items': [
        {
            'block_number': 25779830,
            'transaction_hash': '0x9c0807a414cef03654ed8fb62234577db919dd25e0378a85abb675db1c07135f',
            'token': {'address_hash': '0xdAC17F958D2ee523a2206206994597C13D831ec7'},
            'total': {'decimals': '6', 'value': '500000'},
        }
    ],
    'next_page_params': None,
}

INTERNAL_TXS_PAGE_1: dict[str, Any] = {
    'items': [
        {
            'block_number': 25891449,
            'created_contract': None,
            'error': None,
            'from': {'hash': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'},
            'gas_limit': '2300',
            'index': 26,
            'success': True,
            'timestamp': '2026-09-02T12:00:00.000000Z',
            'to': {'hash': '0x1111111111111111111111111111111111111111'},
            'transaction_hash': '0xaaa111',
            'transaction_index': 126,
            'type': 'call',
            'value': '0',
        }
    ],
    'next_page_params': {
        'index': 26,
        'block_number': 25891449,
        'transaction_index': 126,
        'items_count': 50,
    },
}

INTERNAL_TXS_PAGE_2: dict[str, Any] = {
    'items': [
        {
            'block_number': 25801000,
            'from': {'hash': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'},
            'index': 1,
            'to': {'hash': '0x2222222222222222222222222222222222222222'},
            'transaction_hash': '0xbbb222',
            'transaction_index': 0,
            'type': 'call',
            'value': '100',
        }
    ],
    'next_page_params': None,
}

CONTRACT_SOURCE_RESPONSE: dict[str, Any] = {
    'name': 'WETH9',
    'compiler_version': '0.4.19+commit.c4cbbb05',
    'optimization_enabled': False,
    'optimization_runs': 200,
    'source_code': '// Copyright (C) 2015, 2016, 2017 Dapphub\n...',
    'abi': [{'type': 'function', 'name': 'balanceOf'}],
    'is_verified': True,
    'license_type': 'none',
    'evm_version': 'default',
    'constructor_args': None,
}

NFT_PORTFOLIO_RESPONSE: dict[str, Any] = {
    'items': [
        {
            'id': '567',
            'token': {
                'address_hash': '0x026debba6a0e1f8b24923363073e99be3e4075a8',
                'type': 'ERC-721',
            },
            'token_type': 'ERC-721',
            'value': '1',
            'owner': None,
            'metadata': {'name': 'Some NFT #567'},
            'image_url': 'https://example.com/567.png',
        }
    ],
    'next_page_params': {
        'token_type': 'ERC-721',
        'token_contract_address_hash': '0x026debba6a0e1f8b24923363073e99be3e4075a8',
        'token_id': '567',
        'items_count': 50,
    },
}


# ============================================================================
# Test scaffolding: fake Network + real scanner/client wiring
# ============================================================================


def _scanner(net: FakeNetwork) -> BlockScoutV2Scanner:
    return BlockScoutV2Scanner(
        api_key='',
        network='ethereum',
        url_builder=UrlBuilder('', 'eth', 'ethereum'),
        network_client=net,  # type: ignore[arg-type]
    )


def _client_shell(scanner: BlockScoutV2Scanner) -> ChainscanClient:
    """A ChainscanClient wired to a real scanner via the constructor seam.

    Mirrors the pattern used by ``tests/test_method_consistency.py`` for the
    direct (single-page) block-range sweep; kept self-contained here rather
    than imported, since that file is off-limits for this change. The
    scanner already carries its own ``FakeNetwork``, so the client's own
    ``_network`` is an unused placeholder.
    """
    target = ScannerTarget(
        scanner_name=scanner.name,
        scanner_version=scanner.version,
        network='ethereum',
        api_kind='eth',
        api_key='',
        chain_id=None,
        url_network='ethereum',
        scanner_network='ethereum',
    )
    return ChainscanClient(target, scanner=scanner, network=FakeNetwork([]))


# ============================================================================
# 1. Endpoint specs: wire path + declared params
# ============================================================================


class TestNewEndpointSpecs:
    def test_account_erc20_transfers_path_and_static_filter(self) -> None:
        spec = BlockScoutV2Scanner.SPECS[Method.ACCOUNT_ERC20_TRANSFERS]
        assert spec.path == '/api/v2/addresses/{address}/token-transfers'
        # Endpoint mixes ERC-20/721/1155 without this static filter (verified
        # live: unfiltered items included token_type 'ERC-721'/'ERC-1155').
        assert spec.query == {'type': 'ERC-20'}
        assert spec.param_map['contract_address'] == 'token'
        assert not spec.requires_api_key

    def test_account_internal_txs_path(self) -> None:
        spec = BlockScoutV2Scanner.SPECS[Method.ACCOUNT_INTERNAL_TXS]
        assert spec.path == '/api/v2/addresses/{address}/internal-transactions'
        assert not spec.requires_api_key

    def test_tx_by_hash_not_declared(self) -> None:
        """Regression pin: TX_BY_HASH was investigated and dropped.

        BlockScout V2's transaction envelope carries a native top-level
        ``result`` field (execution status, e.g. "success") that collides
        with ``Network._handle_response``'s generic Etherscan-envelope
        unwrapping (``if 'result' in response_json: payload =
        response_json['result']``) -- live-verified: the scanner-agnostic
        Network layer reduces the whole tx dict to that bare string before
        any BlockScoutV2Scanner parser runs. A wrong spec that returns a
        string where callers expect a dict is worse than no spec.
        """
        assert Method.TX_BY_HASH not in BlockScoutV2Scanner.SPECS

    def test_contract_source_path_matches_contract_abi_resource(self) -> None:
        source_spec = BlockScoutV2Scanner.SPECS[Method.CONTRACT_SOURCE]
        abi_spec = BlockScoutV2Scanner.SPECS[Method.CONTRACT_ABI]
        assert source_spec.path == abi_spec.path == '/api/v2/smart-contracts/{address}'
        assert source_spec.parser is _parse_raw

    def test_account_nft_portfolio_path(self) -> None:
        spec = BlockScoutV2Scanner.SPECS[Method.ACCOUNT_NFT_PORTFOLIO]
        assert spec.path == '/api/v2/addresses/{address}/nft'

    def test_no_new_spec_declares_a_block_range_param(self) -> None:
        """None of the five endpoints carries a block-range filter on the
        wire (verified live): a bounded from_block/to_block must be refused,
        never silently dropped -- see TestBlockRangeGuard below.
        """
        from aiochainscan.scanners.base import BLOCK_RANGE_PARAM_KEYS

        for method in (
            Method.ACCOUNT_ERC20_TRANSFERS,
            Method.ACCOUNT_INTERNAL_TXS,
            Method.CONTRACT_SOURCE,
            Method.ACCOUNT_NFT_PORTFOLIO,
        ):
            spec = BlockScoutV2Scanner.SPECS[method]
            assert not (BLOCK_RANGE_PARAM_KEYS & spec.param_map.keys()), method


# ============================================================================
# 2. Parsers: parsed item shape from real captured payloads
# ============================================================================


class TestParsers:
    def test_parse_token_transfers_item_shape(self) -> None:
        items = _parse_token_transfers(TOKEN_TRANSFERS_PAGE_1)
        assert len(items) == 1
        item = items[0]
        assert item['token']['address_hash'] == '0xdAC17F958D2ee523a2206206994597C13D831ec7'
        assert item['total']['value'] == '1500000'
        assert item['transaction_hash'].startswith('0x')

    def test_parse_token_transfers_empty(self) -> None:
        assert _parse_token_transfers({'items': None}) == []
        assert _parse_token_transfers({}) == []

    def test_parse_internal_transactions_item_shape(self) -> None:
        items = _parse_internal_transactions(INTERNAL_TXS_PAGE_1)
        assert len(items) == 1
        assert items[0]['type'] == 'call'
        assert items[0]['transaction_hash'] == '0xaaa111'

    def test_parse_internal_transactions_empty(self) -> None:
        assert _parse_internal_transactions({'items': []}) == []

    def test_parse_raw_returns_contract_source_dict_unchanged(self) -> None:
        assert _parse_raw(CONTRACT_SOURCE_RESPONSE) == CONTRACT_SOURCE_RESPONSE

    def test_parse_nft_portfolio_item_shape(self) -> None:
        items = _parse_nft_portfolio(NFT_PORTFOLIO_RESPONSE)
        assert len(items) == 1
        assert items[0]['id'] == '567'
        assert items[0]['token_type'] == 'ERC-721'

    def test_parse_nft_portfolio_empty(self) -> None:
        assert _parse_nft_portfolio({'items': []}) == []


# ============================================================================
# 3. call(): single-page dict/list methods over a fake Network
# ============================================================================


class TestCallMethod:
    @pytest.mark.asyncio
    async def test_contract_source_call(self) -> None:
        net = FakeNetwork([CONTRACT_SOURCE_RESPONSE])
        scanner = _scanner(net)

        result = await scanner.call(
            Method.CONTRACT_SOURCE, address='0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
        )

        assert result == CONTRACT_SOURCE_RESPONSE
        assert result['name'] == 'WETH9'
        assert net.calls[0]['url'].endswith(
            '/api/v2/smart-contracts/0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
        )

    @pytest.mark.asyncio
    async def test_account_erc20_transfers_call_sends_static_type_filter(self) -> None:
        net = FakeNetwork([TOKEN_TRANSFERS_PAGE_1])
        scanner = _scanner(net)

        result = await scanner.call(
            Method.ACCOUNT_ERC20_TRANSFERS, address='0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
        )

        assert result[0]['token']['symbol'] == 'USDT'
        assert net.calls[0]['params']['type'] == 'ERC-20'

    @pytest.mark.asyncio
    async def test_account_erc20_transfers_call_forwards_contract_address_as_token(self) -> None:
        net = FakeNetwork([TOKEN_TRANSFERS_PAGE_1])
        scanner = _scanner(net)

        await scanner.call(
            Method.ACCOUNT_ERC20_TRANSFERS,
            address='0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
            contract_address='0xdAC17F958D2ee523a2206206994597C13D831ec7',
        )

        assert net.calls[0]['params']['token'] == '0xdAC17F958D2ee523a2206206994597C13D831ec7'

    @pytest.mark.asyncio
    async def test_account_nft_portfolio_call(self) -> None:
        net = FakeNetwork([NFT_PORTFOLIO_RESPONSE])
        scanner = _scanner(net)

        result = await scanner.call(
            Method.ACCOUNT_NFT_PORTFOLIO, address='0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
        )

        assert result == NFT_PORTFOLIO_RESPONSE['items']


# ============================================================================
# 4. fetch_page(): cursor threading across two pages
# ============================================================================


class TestFetchPageCursorThreading:
    @pytest.mark.asyncio
    async def test_token_transfers_cursor_threads_across_two_pages(self) -> None:
        net = FakeNetwork([TOKEN_TRANSFERS_PAGE_1, TOKEN_TRANSFERS_PAGE_2])
        scanner = _scanner(net)
        params: dict[str, Any] = {'address': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'}

        items1, cursor1 = await scanner.fetch_page(Method.ACCOUNT_ERC20_TRANSFERS, params)
        assert items1 == TOKEN_TRANSFERS_PAGE_1['items']
        assert cursor1 == {'index': 92, 'block_number': 25818613}

        params2 = {**params, **cursor1}
        items2, cursor2 = await scanner.fetch_page(Method.ACCOUNT_ERC20_TRANSFERS, params2)
        assert items2 == TOKEN_TRANSFERS_PAGE_2['items']
        assert cursor2 is None

        # Second page's wire request actually carried the cursor.
        assert net.calls[1]['params']['index'] == 92
        assert net.calls[1]['params']['block_number'] == 25818613
        # The path address placeholder was never overwritten by cursor keys.
        assert net.calls[1]['url'].endswith(
            '/api/v2/addresses/0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045/token-transfers'
        )

    @pytest.mark.asyncio
    async def test_internal_transactions_cursor_threads_across_two_pages(self) -> None:
        net = FakeNetwork([INTERNAL_TXS_PAGE_1, INTERNAL_TXS_PAGE_2])
        scanner = _scanner(net)
        params: dict[str, Any] = {'address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'}

        items1, cursor1 = await scanner.fetch_page(Method.ACCOUNT_INTERNAL_TXS, params)
        assert items1 == INTERNAL_TXS_PAGE_1['items']
        assert cursor1 == {
            'index': 26,
            'block_number': 25891449,
            'transaction_index': 126,
            'items_count': 50,
        }

        params2 = {**params, **cursor1}
        items2, cursor2 = await scanner.fetch_page(Method.ACCOUNT_INTERNAL_TXS, params2)
        assert items2 == INTERNAL_TXS_PAGE_2['items']
        assert cursor2 is None
        assert net.calls[1]['params']['transaction_index'] == 126


# ============================================================================
# 5. Block-range guard: a bounded range must be refused, never dropped
# ============================================================================


class TestBlockRangeGuard:
    @pytest.mark.asyncio
    async def test_get_token_transfers_bounded_range_raises(self) -> None:
        net = FakeNetwork([])  # a refused call must never reach the wire
        scanner = _scanner(net)
        client = _client_shell(scanner)

        with pytest.raises(BlockRangeNotSupportedError) as excinfo:
            await client.get_token_transfers(
                '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045', start_block=100, end_block=200
            )

        assert 'blockscout' in str(excinfo.value)
        assert not net.calls

    @pytest.mark.asyncio
    async def test_get_internal_transactions_bounded_range_raises(self) -> None:
        net = FakeNetwork([])
        scanner = _scanner(net)
        client = _client_shell(scanner)

        with pytest.raises(BlockRangeNotSupportedError):
            await client.get_internal_transactions(
                '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', start_block=100, end_block=200
            )

        assert not net.calls

    @pytest.mark.asyncio
    async def test_get_token_transfers_unbounded_range_still_served(self) -> None:
        """The guard must only refuse BOUNDED ranges."""
        net = FakeNetwork([TOKEN_TRANSFERS_PAGE_1])
        scanner = _scanner(net)
        client = _client_shell(scanner)

        result = await client.get_token_transfers('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')

        assert result == TOKEN_TRANSFERS_PAGE_1['items']
        assert net.calls

    @pytest.mark.asyncio
    async def test_iter_token_transfers_streaming_bounded_range_raises(self) -> None:
        net = FakeNetwork([])
        scanner = _scanner(net)
        client = _client_shell(scanner)

        with pytest.raises(BlockRangeNotSupportedError):
            async for _batch in client.iter_token_transfers_streaming(
                '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045', from_block=100, to_block=200
            ):
                pass

        assert not net.calls
