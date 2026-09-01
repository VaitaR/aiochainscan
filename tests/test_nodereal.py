"""Tests for the NodeReal MegaNode BSC scanner.

Covers:
- Scanner registration and attributes
- Endpoint specs and wire-parameter builders (JSON-RPC shapes)
- Response parsers (hex → decimal Wei normalization)
- call() envelope construction against a mocked Network
- fetch_page cursor semantics: pageKey continuation, 1000-block window
  walking, holdings page/totalCount paging
- Rate-limit translation (JSON-RPC -32005 → ChainscanRateLimitError)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.constants import MAX_BLOCK_NUMBER
from aiochainscan.core.method import Method
from aiochainscan.exceptions import ChainscanClientProxyError, ChainscanRateLimitError
from aiochainscan.scanners import SCANNER_REGISTRY, get_scanner_class
from aiochainscan.scanners.nodereal import (
    NodeRealScanner,
    _hex_qty_to_decimal_str,
    _parse_contract_abi,
    _parse_contract_creation,
    _parse_holdings,
    _parse_status_check,
    _parse_token_meta,
    _parse_transfer_items,
)

ADDRESS = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
CONTRACT = '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56'
TX_HASH = '0x' + 'ab' * 32


def _make_scanner(network: str = 'bsc', api_key: str = 'test-key') -> NodeRealScanner:
    return NodeRealScanner(
        api_key=api_key,
        network=network,
        url_builder=MagicMock(),
    )


def _mock_network(scanner: NodeRealScanner, responses: list[dict]) -> AsyncMock:
    """Attach a Network double that pops canned results in order.

    Responses are the *unwrapped* JSON-RPC ``result`` payloads (what
    ``Network.request`` returns after ``_handle_response`` unwrapping).
    """
    network = MagicMock()
    network.request = AsyncMock(side_effect=list(responses))
    scanner._network_client = network
    return network


# ============================================================================
# Registration & attributes
# ============================================================================


class TestScannerRegistration:
    def test_scanner_registered(self) -> None:
        assert ('nodereal', 'v1') in SCANNER_REGISTRY

    def test_get_scanner_class(self) -> None:
        assert get_scanner_class('nodereal', 'v1') is NodeRealScanner


class TestScannerAttributes:
    def test_name_and_version(self) -> None:
        assert NodeRealScanner.name == 'nodereal'
        assert NodeRealScanner.version == 'v1'

    def test_supported_networks(self) -> None:
        assert NodeRealScanner.supported_networks == {'bsc', 'bnb', 'binance', 'bsc-testnet'}

    def test_rpc_base_urls_cover_networks(self) -> None:
        for network in NodeRealScanner.supported_networks:
            assert network in NodeRealScanner.RPC_BASE_URLS

    def test_declared_method_count(self) -> None:
        # Subset of the 30 Method values; exact count guards accidental drift.
        assert len(NodeRealScanner.SPECS) == 22


# ============================================================================
# Parsers
# ============================================================================


class TestParsers:
    def test_hex_qty_to_decimal_str(self) -> None:
        assert _hex_qty_to_decimal_str('0x2a') == '42'
        assert _hex_qty_to_decimal_str('0x0') == '0'
        assert _hex_qty_to_decimal_str(17) == 17
        assert _hex_qty_to_decimal_str('plain') == 'plain'
        assert _hex_qty_to_decimal_str(None) is None

    def test_parse_balance_hex_wei(self) -> None:
        from aiochainscan.scanners.nodereal import _parse_balance

        assert _parse_balance('0x7328edad9ab10b7d710') == str(int('7328edad9ab10b7d710', 16))
        assert _parse_balance('0x0') == '0'

    def test_parse_transfers_normalizes_core_fields(self) -> None:
        raw = {
            'pageKey': '',
            'transfers': [
                {
                    'category': 'external',
                    'blockNum': '0x6c92dd',
                    'from': '0xaaa',
                    'to': '0xbbb',
                    'value': '0x2a520017d28dc000',
                    'asset': 'BNB',
                    'hash': TX_HASH,
                    'blockTimeStamp': 1620089457,
                }
            ],
        }
        items = _parse_transfer_items(raw)
        assert len(items) == 1
        item = items[0]
        assert item['block_number'] == 7115485
        assert item['value'] == str(int('2a520017d28dc000', 16))
        assert item['hash'] == TX_HASH
        # provider fields preserved
        assert item['blockNum'] == '0x6c92dd'

    def test_parse_transfers_empty(self) -> None:
        assert _parse_transfer_items({}) == []
        assert _parse_transfer_items({'transfers': []}) == []

    def test_parse_holdings_extracts_details(self) -> None:
        raw = {
            'totalCount': '0x2',
            'details': [
                {'tokenAddress': CONTRACT, 'tokenSymbol': 'BUSD'},
            ],
        }
        items = _parse_holdings(raw)
        assert items == [{'tokenAddress': CONTRACT, 'tokenSymbol': 'BUSD'}]
        assert _parse_holdings({}) == []

    def test_parse_token_meta_accepts_decimails_typo(self) -> None:
        assert (
            _parse_token_meta({'name': 'BUSD', 'symbol': 'BUSD', 'decimals': 18})['decimals'] == 18
        )
        fixed = _parse_token_meta({'name': 'X', 'symbol': 'X', 'decimails': '0x12'})
        assert fixed['decimals'] == '0x12'

    def test_parse_contract_creation_maps_creator(self) -> None:
        raw = {
            'hash': TX_HASH,
            'from': '0xcreator',
            'contractAddress': CONTRACT,
            'blockNumber': 124241,
            'timestamp': 1599044503,
        }
        listing = _parse_contract_creation(raw)
        assert listing == [
            {
                'contractAddress': CONTRACT,
                'contractCreator': '0xcreator',
                'txHash': TX_HASH,
                'blockNumber': 124241,
                'timestamp': 1599044503,
            }
        ]

    def test_parse_contract_abi_from_open_platform_envelope(self) -> None:
        abi = [{'type': 'function', 'name': 'transfer'}]
        assert _parse_contract_abi({'abi': abi}) == '[{"type":"function","name":"transfer"}]'

    def test_parse_contract_abi_passthrough_string(self) -> None:
        assert _parse_contract_abi('[{"type":"fallback"}]') == '[{"type":"fallback"}]'

    def test_parse_status_check(self) -> None:
        assert _parse_status_check({'status': '0x1'}) == {
            'status': '1',
            'message': 'OK',
            'result': '1',
        }
        assert _parse_status_check({'status': '0x0'})['result'] == '0'
        assert _parse_status_check(None)['status'] == '0'
        assert _parse_status_check({})['message'] == 'Transaction not found'


# ============================================================================
# Initialization
# ============================================================================


class TestInitialization:
    def test_mainnet_endpoints(self) -> None:
        for network in ('bsc', 'bnb', 'binance'):
            scanner = _make_scanner(network=network)
            assert scanner.rpc_base_url == 'https://bsc-mainnet.nodereal.io/v1'
            assert scanner.contract_path == 'bsc-mainnet'

    def test_testnet_endpoints(self) -> None:
        scanner = _make_scanner(network='bsc-testnet')
        assert scanner.rpc_base_url == 'https://bsc-testnet.nodereal.io/v1'
        assert scanner.contract_path == 'bsc-testnet'

    def test_unsupported_network_raises(self) -> None:
        with pytest.raises(ValueError, match='not supported'):
            _make_scanner(network='ethereum')


# ============================================================================
# Wire parameter builders
# ============================================================================


class TestWireBuilders:
    def test_balance_params(self) -> None:
        scanner = _make_scanner()
        assert scanner._build_rpc_params(Method.ACCOUNT_BALANCE, {'address': ADDRESS}) == [
            ADDRESS,
            'latest',
        ]

    def test_transfer_filter_full(self) -> None:
        scanner = _make_scanner()
        params = {
            'address': ADDRESS,
            'startblock': 0,
            'endblock': 2500,
        }
        rpc_params = scanner._build_rpc_params(
            Method.ACCOUNT_TRANSACTIONS,
            {
                **params,
                **{
                    '__nr_window': [0, 999],
                    '__nr_tip': 2500,
                },
            },
        )
        assert len(rpc_params) == 1
        filter_ = rpc_params[0]
        assert filter_['category'] == ['external']
        assert filter_['address'] == ADDRESS
        assert filter_['fromBlock'] == '0x0'
        assert filter_['toBlock'] == '0x3e7'
        assert filter_['order'] == 'desc'
        assert 'pageKey' not in filter_

    def test_transfer_categories(self) -> None:
        scanner = _make_scanner()
        expected = {
            Method.ACCOUNT_INTERNAL_TXS: ['internal'],
            Method.ACCOUNT_ERC20_TRANSFERS: ['20'],
            Method.ACCOUNT_ERC721_TRANSFERS: ['721'],
            Method.ACCOUNT_ERC1155_TRANSFERS: ['1155'],
        }
        for method, category in expected.items():
            params = {
                'address': ADDRESS,
                '__nr_window': [0, 999],
                '__nr_tip': 1000,
            }
            assert scanner._build_rpc_params(method, params)[0]['category'] == category

    def test_transfer_contract_address_filter(self) -> None:
        scanner = _make_scanner()
        params = {
            'address': ADDRESS,
            'contract_address': CONTRACT,
            '__nr_window': [0, 999],
            '__nr_tip': 1000,
        }
        filter_ = scanner._build_rpc_params(Method.ACCOUNT_ERC20_TRANSFERS, params)[0]
        assert filter_['contractAddresses'] == [CONTRACT]

    def test_transfer_requires_address(self) -> None:
        scanner = _make_scanner()
        with pytest.raises(ValueError, match='address is required'):
            scanner._build_rpc_params(
                Method.ACCOUNT_TRANSACTIONS, {'__nr_window': [0, 999], '__nr_tip': 1000}
            )

    def test_holdings_params_hex_page(self) -> None:
        scanner = _make_scanner()
        params = {'address': ADDRESS, 'page': 2, 'page_size': 50}
        assert scanner._build_rpc_params(Method.ACCOUNT_TOKEN_PORTFOLIO, params) == [
            ADDRESS,
            '0x2',
            '0x32',
        ]

    def test_nft_holdings_params(self) -> None:
        scanner = _make_scanner()
        params = {'address': ADDRESS}
        assert scanner._build_rpc_params(Method.ACCOUNT_NFT_PORTFOLIO, params) == [
            ADDRESS,
            'erc721',
            '0x1',
            '0x64',
        ]

    def test_block_by_number_params(self) -> None:
        scanner = _make_scanner()
        assert scanner._build_rpc_params(Method.BLOCK_BY_NUMBER, {'block_number': 123}) == [
            '0x7b',
            False,
        ]
        assert scanner._build_rpc_params(Method.BLOCK_BY_NUMBER, {'block_number': 'latest'}) == [
            'latest',
            False,
        ]

    def test_block_by_timestamp_params(self) -> None:
        scanner = _make_scanner()
        assert scanner._build_rpc_params(
            Method.BLOCK_NUMBER_BY_TIMESTAMP, {'timestamp': 1600000000, 'closest': 'before'}
        ) == [1600000000, 'BEFORE']

    def test_block_by_timestamp_invalid_closest(self) -> None:
        scanner = _make_scanner()
        with pytest.raises(ValueError, match='closest'):
            scanner._build_rpc_params(
                Method.BLOCK_NUMBER_BY_TIMESTAMP, {'timestamp': 1, 'closest': 'nearest'}
            )

    def test_contract_creation_single_address(self) -> None:
        scanner = _make_scanner()
        assert scanner._build_rpc_params(
            Method.CONTRACT_CREATION, {'contract_addresses': CONTRACT}
        ) == [CONTRACT]

    def test_contract_creation_rejects_multiple(self) -> None:
        scanner = _make_scanner()
        with pytest.raises(ValueError, match='one contract address'):
            scanner._build_rpc_params(
                Method.CONTRACT_CREATION,
                {'contract_addresses': f'{CONTRACT},{CONTRACT}'},
            )

    def test_logs_filter_topics(self) -> None:
        scanner = _make_scanner()
        topic0 = '0xddf252ad'
        filter_ = scanner._build_log_filter(
            {'address': CONTRACT, 'from_block': 0, 'to_block': 'latest', 'topic0': topic0}
        )
        assert filter_ == {
            'fromBlock': '0x0',
            'toBlock': 'latest',
            'address': CONTRACT,
            'topics': [topic0],
        }

    def test_proxy_call_params(self) -> None:
        scanner = _make_scanner()
        assert scanner._build_rpc_params(
            Method.PROXY_ETH_CALL, {'to': CONTRACT, 'data': '0x70a08231'}
        ) == [{'to': CONTRACT, 'data': '0x70a08231'}, 'latest']


# ============================================================================
# call() with mocked network
# ============================================================================


class TestCall:
    @pytest.mark.asyncio
    async def test_call_unsupported_method_raises(self) -> None:
        scanner = _make_scanner()
        with pytest.raises(ValueError, match='not supported'):
            await scanner.call(Method.ETH_PRICE)

    @pytest.mark.asyncio
    async def test_call_requires_network_client(self) -> None:
        scanner = _make_scanner()
        with pytest.raises(RuntimeError, match='network_client is required'):
            await scanner.call(Method.ACCOUNT_BALANCE, address=ADDRESS)

    @pytest.mark.asyncio
    async def test_call_requires_api_key(self) -> None:
        scanner = _make_scanner(api_key='')
        scanner._network_client = MagicMock()
        with pytest.raises(Exception, match='API key'):
            await scanner.call(Method.ACCOUNT_BALANCE, address=ADDRESS)

    @pytest.mark.asyncio
    async def test_balance_envelope_and_parsing(self) -> None:
        scanner = _make_scanner()
        network = _mock_network(scanner, ['0x2a'])

        result = await scanner.call(Method.ACCOUNT_BALANCE, address=ADDRESS)

        assert result == '42'
        network.request.assert_awaited_once()
        kwargs = network.request.await_args.kwargs
        assert kwargs['method'] == 'POST'
        assert kwargs['url'] == 'https://bsc-mainnet.nodereal.io/v1/test-key'
        envelope = kwargs['json_data']
        assert envelope['jsonrpc'] == '2.0'
        assert envelope['method'] == 'eth_getBalance'
        assert envelope['params'] == [ADDRESS, 'latest']

    @pytest.mark.asyncio
    async def test_transactions_recent_window_when_unbounded(self) -> None:
        scanner = _make_scanner()
        tip_hex = '0x1000'  # 4096
        network = _mock_network(
            scanner,
            [
                tip_hex,  # eth_blockNumber
                {'pageKey': '', 'transfers': []},  # nr_getTransactionByAddress
            ],
        )

        await scanner.call(Method.ACCOUNT_TRANSACTIONS, address=ADDRESS)

        transfer_call = network.request.await_args_list[1].kwargs
        filter_ = transfer_call['json_data']['params'][0]
        assert filter_['fromBlock'] == '0xc19'  # 4096 - 1000 + 1 = 3097
        assert filter_['toBlock'] == '0x1000'

    @pytest.mark.asyncio
    async def test_rate_limit_code_translated(self) -> None:
        scanner = _make_scanner()
        _mock_network(
            scanner,
            [ChainscanClientProxyError(-32005, 'You have reached the maximum API usage limit')],
        )
        with pytest.raises(ChainscanRateLimitError):
            await scanner.call(Method.ACCOUNT_BALANCE, address=ADDRESS)

    @pytest.mark.asyncio
    async def test_contract_abi_via_rest(self) -> None:
        scanner = _make_scanner()
        abi = [{'type': 'function', 'name': 'transfer'}]
        network = MagicMock()
        network.request = AsyncMock(return_value={'abi': abi})
        scanner._network_client = network

        result = await scanner.call(Method.CONTRACT_ABI, address=CONTRACT)

        assert result == '[{"type":"function","name":"transfer"}]'
        kwargs = network.request.await_args.kwargs
        assert kwargs['method'] == 'GET'
        assert kwargs['url'] == 'https://open-platform.nodereal.io/test-key/bsc-mainnet/contract/'
        assert kwargs['params'] == {'action': 'getabi', 'address': CONTRACT}


# ============================================================================
# fetch_page cursor semantics
# ============================================================================


class TestFetchPageTransfers:
    @pytest.mark.asyncio
    async def test_page_key_continuation_within_window(self) -> None:
        scanner = _make_scanner()
        page_one = {'pageKey': 'cursor-uuid', 'transfers': [{'hash': '0x1', 'blockNum': '0x1'}]}
        page_two = {'pageKey': '', 'transfers': [{'hash': '0x2', 'blockNum': '0x2'}]}
        _mock_network(scanner, [page_one, page_two])

        params = {'address': ADDRESS, 'startblock': 0, 'endblock': 500}
        items, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, params)

        assert [i['hash'] for i in items] == ['0x1']
        assert cursor is not None
        assert cursor['pageKey'] == 'cursor-uuid'
        assert cursor['__nr_window'] == [0, 500]  # min(start+999, tip=500)

        items_two, cursor_two = await scanner.fetch_page(
            Method.ACCOUNT_TRANSACTIONS, {**params, **cursor}
        )
        assert [i['hash'] for i in items_two] == ['0x2']
        # window exhausted (500 < 1000) and no pageKey → pagination ends
        assert cursor_two is None

    @pytest.mark.asyncio
    async def test_window_walking_spans_full_range(self) -> None:
        """Range [0, 2500] inclusive must be covered by windows [0,999],
        [1000,1999], [2000,2500] and then terminate."""
        scanner = _make_scanner()
        empty = {'pageKey': '', 'transfers': []}
        network = _mock_network(scanner, [empty, empty, empty])

        params = {'address': ADDRESS, 'startblock': 0, 'endblock': 2500}
        current: dict = dict(params)
        windows: list[tuple[str, str]] = []
        for _ in range(10):
            _, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, current)
            call = network.request.await_args_list[-1].kwargs
            filter_ = call['json_data']['params'][0]
            windows.append((filter_['fromBlock'], filter_['toBlock']))
            if cursor is None:
                break
            current = {**current, **cursor}
        else:  # pragma: no cover
            pytest.fail('pagination did not terminate')

        assert windows == [('0x0', '0x3e7'), ('0x3e8', '0x7cf'), ('0x7d0', '0x9c4')]
        assert network.request.await_count == 3

    @pytest.mark.asyncio
    async def test_window_cursor_stale_page_key_dropped(self) -> None:
        """An advancing window must not replay the previous window's pageKey."""
        scanner = _make_scanner()
        empty = {'pageKey': '', 'transfers': []}
        network = _mock_network(scanner, [empty, empty])

        params = {'address': ADDRESS, 'startblock': 0, 'endblock': 1500}
        _, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, params)
        # Simulate accumulated params: stale pageKey plus the new window
        merged = {**params, 'pageKey': 'stale-uuid', **cursor}
        await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, merged)

        second_filter = network.request.await_args_list[1].kwargs['json_data']['params'][0]
        assert second_filter['fromBlock'] == '0x3e8'  # window advanced to [1000, 1499]
        assert 'pageKey' not in second_filter

    @pytest.mark.asyncio
    async def test_unbounded_end_resolves_chain_tip(self) -> None:
        scanner = _make_scanner()
        empty = {'pageKey': '', 'transfers': []}
        network = _mock_network(
            scanner,
            [
                '0x3e7',  # eth_blockNumber → tip = 999
                empty,
            ],
        )

        params = {'address': ADDRESS, 'startblock': 0, 'endblock': MAX_BLOCK_NUMBER}
        items, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, params)

        assert items == []
        # Single window covers [0, 999] → done
        assert cursor is None
        first_filter = network.request.await_args_list[1].kwargs['json_data']['params'][0]
        assert first_filter['toBlock'] == '0x3e7'


class TestFetchPageHoldings:
    @pytest.mark.asyncio
    async def test_holdings_paging_until_total(self) -> None:
        scanner = _make_scanner()
        page_one = {'totalCount': '0xc8', 'details': [{'tokenAddress': '0x1'}]}
        page_two = {'totalCount': '0xc8', 'details': [{'tokenAddress': '0x2'}]}
        _mock_network(scanner, [page_one, page_two])

        params = {'address': ADDRESS}
        items, cursor = await scanner.fetch_page(Method.ACCOUNT_TOKEN_PORTFOLIO, params)
        assert len(items) == 1
        assert cursor == {'page': 2, 'page_size': 100}

        items_two, cursor_two = await scanner.fetch_page(
            Method.ACCOUNT_TOKEN_PORTFOLIO, {**params, **cursor}
        )
        assert len(items_two) == 1
        assert cursor_two is None  # 2 * 100 >= 200

    @pytest.mark.asyncio
    async def test_holdings_single_page_total(self) -> None:
        scanner = _make_scanner()
        _mock_network(scanner, [{'totalCount': '0x5', 'details': []}])
        _, cursor = await scanner.fetch_page(Method.ACCOUNT_TOKEN_PORTFOLIO, {'address': ADDRESS})
        assert cursor is None

    @pytest.mark.asyncio
    async def test_single_page_methods_terminate(self) -> None:
        scanner = _make_scanner()
        raw_receipt = {
            'hash': TX_HASH,
            'from': '0xcreator',
            'contractAddress': CONTRACT,
            'blockNumber': 124241,
            'timestamp': 1599044503,
        }
        _mock_network(scanner, [{'hash': TX_HASH}, raw_receipt])
        # Dict-shaped single results (TX_BY_HASH) coerce to no items, matching
        # the base Scanner contract (dicts expose items only via 'items' key).
        tx_items, tx_cursor = await scanner.fetch_page(Method.TX_BY_HASH, {'txhash': TX_HASH})
        assert tx_items == []
        assert tx_cursor is None

        creation_items, creation_cursor = await scanner.fetch_page(
            Method.CONTRACT_CREATION, {'contract_addresses': CONTRACT}
        )
        assert creation_items == [
            {
                'contractAddress': CONTRACT,
                'contractCreator': '0xcreator',
                'txHash': TX_HASH,
                'blockNumber': 124241,
                'timestamp': 1599044503,
            }
        ]
        assert creation_cursor is None


# ============================================================================
# Method support
# ============================================================================


class TestMethodSupport:
    def test_key_unsupported_methods(self) -> None:
        scanner = _make_scanner()
        for unsupported in (
            Method.CONTRACT_VERIFY,
            Method.CONTRACT_VERIFY_STATUS,
            Method.GAS_ORACLE,
            Method.GAS_ESTIMATE,
            Method.ETH_PRICE,
            Method.ETH_SUPPLY,
            Method.BLOCK_REWARD,
            Method.BLOCK_COUNTDOWN,
        ):
            assert not scanner.supports_method(unsupported), unsupported

    def test_supported_surface(self) -> None:
        scanner = _make_scanner()
        methods = scanner.get_supported_methods()
        for expected in (
            Method.ACCOUNT_BALANCE,
            Method.ACCOUNT_TRANSACTIONS,
            Method.ACCOUNT_INTERNAL_TXS,
            Method.ACCOUNT_TOKEN_PORTFOLIO,
            Method.ACCOUNT_NFT_PORTFOLIO,
            Method.TX_BY_HASH,
            Method.TX_STATUS_CHECK,
            Method.BLOCK_BY_NUMBER,
            Method.BLOCK_NUMBER_BY_TIMESTAMP,
            Method.CONTRACT_ABI,
            Method.CONTRACT_SOURCE,
            Method.CONTRACT_CREATION,
            Method.TOKEN_BALANCE,
            Method.TOKEN_SUPPLY,
            Method.TOKEN_INFO,
            Method.EVENT_LOGS,
            Method.PROXY_ETH_CALL,
            Method.PROXY_GET_BALANCE,
        ):
            assert expected in methods, expected
