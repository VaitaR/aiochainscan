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

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.constants import MAX_BLOCK_NUMBER
from aiochainscan.core.pool import classify_failure
from aiochainscan.domain.method import Method
from aiochainscan.exceptions import (
    ChainscanClientProxyError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
    FailureKind,
    MethodNotDeclaredError,
    ScannerArgumentError,
)
from aiochainscan.scanners import (
    SCANNER_REGISTRY,
    get_scanner_class,
    scanners_serving_completely,
)
from aiochainscan.scanners.base import BLOCK_RANGE_PARAM_KEYS, spec_declares_block_range
from aiochainscan.scanners.nodereal import (
    _NODEREAL_DIALECT,
    NodeRealScanner,
    _declared_sources,
    _filter_transfer_items,
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
        # Subset of the 33 Method values; exact count guards accidental drift.
        assert len(NodeRealScanner.SPECS) == 25


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
        assert 'contractAddresses' not in filter_

    def test_transfer_contract_address_filter_accepts_streaming_wire_name(self) -> None:
        scanner = _make_scanner()
        params = {
            'address': ADDRESS,
            'contractaddress': CONTRACT,
            '__nr_window': [0, 999],
            '__nr_tip': 1000,
        }
        filter_ = scanner._build_rpc_params(Method.ACCOUNT_ERC20_TRANSFERS, params)[0]
        assert 'contractAddresses' not in filter_

    def test_transfer_requires_address(self) -> None:
        scanner = _make_scanner()
        with pytest.raises(ScannerArgumentError, match='address is required'):
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
        with pytest.raises(ScannerArgumentError, match='closest'):
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
        with pytest.raises(ScannerArgumentError, match='one contract address'):
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

    def test_logs_filter_accepts_streaming_block_names(self) -> None:
        scanner = _make_scanner()
        filter_ = scanner._build_log_filter({'fromBlock': 100, 'toBlock': 200})
        assert filter_ == {'fromBlock': '0x64', 'toBlock': '0xc8'}

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
    async def test_transfer_call_applies_contract_filter_client_side(self) -> None:
        scanner = _make_scanner()
        other_contract = '0x0000000000000000000000000000000000000001'
        network = _mock_network(
            scanner,
            [
                {
                    'transfers': [
                        {'hash': '0x1', 'blockNum': '0x1', 'contractAddress': CONTRACT},
                        {'hash': '0x2', 'blockNum': '0x2', 'contractAddress': other_contract},
                    ]
                }
            ],
        )

        items = await scanner.call(
            Method.ACCOUNT_ERC20_TRANSFERS,
            address=ADDRESS,
            contract_address=CONTRACT.upper(),
            start_block=0,
            end_block=500,
        )

        assert [item['hash'] for item in items] == ['0x1']
        wire_filter = network.request.await_args.kwargs['json_data']['params'][0]
        assert 'contractAddresses' not in wire_filter

    @pytest.mark.parametrize('end_block', [1000, '1000', '0x3e8'])
    @pytest.mark.asyncio
    async def test_string_end_block_bounds_the_walk(self, end_block: object) -> None:
        """Every spelling the library accepts must bound the window walk.

        A string end read as "unbounded" resolved the live tip instead and
        walked past the block the caller asked to stop at, returning records
        outside the requested range — there is no client-side block filter
        behind this.
        """
        scanner = _make_scanner()
        network = _mock_network(scanner, [{'transfers': []}])

        await scanner.call(
            Method.ACCOUNT_TRANSACTIONS,
            address=ADDRESS,
            start_block=500,
            end_block=end_block,
        )

        # The tip was never probed: no eth_blockNumber request was issued.
        assert [c.kwargs['json_data']['method'] for c in network.request.await_args_list] == [
            'nr_getTransactionByAddress'
        ]
        wire_filter = network.request.await_args.kwargs['json_data']['params'][0]
        assert wire_filter['toBlock'] == hex(1000)

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
    async def test_usage_limit_is_classified_inside_the_retry_boundary(self) -> None:
        """-32005 becomes a rate limit in the DIALECT, not after ``_send`` returns.

        Translating around the call site produced a retryable class the
        retried function never saw: the transport made one attempt where an
        Etherscan-style rate limit was retried five times.
        """
        scanner = _make_scanner()
        _mock_network(scanner, [{'result': '0x1'}])

        await scanner.call(Method.ACCOUNT_BALANCE, address=ADDRESS)

        dialect = scanner._network_client.request.await_args.kwargs['dialect']
        with pytest.raises(ChainscanRateLimitError):
            dialect.raise_if_error(
                {
                    'jsonrpc': '2.0',
                    'id': 1,
                    'error': {
                        'code': -32005,
                        'message': 'You have reached the maximum API usage limit',
                    },
                }
            )

    def test_result_size_limit_stays_fatal(self) -> None:
        """ "logs count exceeds the limit" rides the same code and is NOT throttling.

        Measured live 2026-09-05 on bsc-mainnet: a 2000-block ``eth_getLogs``
        window answers -32005 "logs count exceeds the limit 50000". Retrying
        that is deterministic waste, and in a pool it cools a healthy provider.
        """
        scanner = _make_scanner()
        _mock_network(scanner, [{'result': '0x1'}])
        dialect = _NODEREAL_DIALECT

        with pytest.raises(ChainscanClientProxyError):
            dialect.raise_if_error(
                {
                    'jsonrpc': '2.0',
                    'id': 1,
                    'error': {'code': -32005, 'message': 'logs count exceeds the limit 50000'},
                }
            )

    def test_event_logs_declares_the_measured_result_window(self) -> None:
        """A single-shot ``eth_getLogs`` is not a provider that runs to exhaustion."""
        assert NodeRealScanner.result_window_for(Method.EVENT_LOGS) == 50_000
        assert 'nodereal/v1' not in scanners_serving_completely(Method.EVENT_LOGS)

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
    async def test_contract_filter_is_applied_client_side(self) -> None:
        scanner = _make_scanner()
        other_contract = '0x0000000000000000000000000000000000000001'
        network = _mock_network(
            scanner,
            [
                {
                    'pageKey': '',
                    'transfers': [
                        {'hash': '0x1', 'blockNum': '0x1', 'contractAddress': CONTRACT},
                        {'hash': '0x2', 'blockNum': '0x2', 'contractAddress': other_contract},
                    ],
                }
            ],
        )

        items, cursor = await scanner.fetch_page(
            Method.ACCOUNT_ERC20_TRANSFERS,
            {
                'address': ADDRESS,
                'contractaddress': CONTRACT.upper(),
                'startblock': 0,
                'endblock': 500,
            },
        )

        assert [item['hash'] for item in items] == ['0x1']
        assert cursor is None
        wire_filter = network.request.await_args.kwargs['json_data']['params'][0]
        assert 'contractAddresses' not in wire_filter

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


# ============================================================================
# Topic operators
# ============================================================================


class TestTopicOperators:
    """``eth_getLogs`` ANDs its topic positions and cannot express an OR
    between two of them, so the operator must be refused, not dropped."""

    @pytest.mark.parametrize('operator', ['or', 'OR'])
    @pytest.mark.asyncio
    async def test_or_between_topics_is_refused(self, operator: str) -> None:
        scanner = _make_scanner()
        network = _mock_network(scanner, [{'logs': []}])

        with pytest.raises(MethodNotDeclaredError, match='cannot express'):
            await scanner.call(
                Method.EVENT_LOGS,
                address=ADDRESS,
                topic0='0x' + 'aa' * 32,
                topic1='0x' + 'bb' * 32,
                topic0_1_opr=operator,
            )

        network.request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_and_is_what_the_wire_already_does(self) -> None:
        scanner = _make_scanner()
        network = _mock_network(scanner, [[]])

        await scanner.call(
            Method.EVENT_LOGS,
            address=ADDRESS,
            topic0='0x' + 'aa' * 32,
            topic1='0x' + 'bb' * 32,
            topic0_1_opr='and',
        )

        wire_filter = network.request.await_args.kwargs['json_data']['params'][0]
        assert wire_filter['topics'] == ['0x' + 'aa' * 32, '0x' + 'bb' * 32]


# ============================================================================
# Declaration ↔ execution agreement (block-range capability)
# ============================================================================


class TestBlockRangeDeclarations:
    """``supports_block_range`` must read the declarations that execute.

    The pre-refactor state had SPECS ``param_map``\\ s that nothing ran —
    capability was derived from declarations while the builders hardcoded
    their own param sources. The builders now read ``param_map`` too; these
    tests pin that the two readers can never describe different realities.
    """

    def test_capability_matches_executed_range_consumption(self) -> None:
        """Exactly the methods whose executed path consumes block bounds claim one.

        Transfer methods consume them in ``_resolve_window``; EVENT_LOGS in
        ``_build_log_filter``; every other NodeReal method has no range
        parameter on its wire and must not claim one.
        """
        scanner = _make_scanner()
        for method in NodeRealScanner.SPECS:
            executed = method in scanner._TRANSFER_METHODS or method == Method.EVENT_LOGS
            assert scanner.supports_block_range(method) is executed, method

    def test_window_aliases_live_in_the_declaration(self) -> None:
        """The tolerated input spellings ARE the declared sources — one fact, one place.

        ``_resolve_window`` and ``_build_transfer_filter`` accept both the
        pythonic and Etherscan-style names because both are declared in the
        spec's ``param_map`` (first declared wins), not because a helper
        hardcodes a second copy of the alias list.
        """
        for method in sorted(NodeRealScanner._TRANSFER_METHODS, key=str):
            spec = NodeRealScanner.SPECS[method]
            assert _declared_sources(spec, 'fromBlock') == ('start_block', 'startblock'), method
            assert _declared_sources(spec, 'toBlock') == ('end_block', 'endblock'), method
        log_spec = NodeRealScanner.SPECS[Method.EVENT_LOGS]
        assert _declared_sources(log_spec, 'fromBlock') == ('from_block', 'fromBlock')
        assert _declared_sources(log_spec, 'toBlock') == ('to_block', 'toBlock')

    def test_capability_is_declaration_pure(self) -> None:
        """Stripping the range keys from the map strips the capability.

        Nothing scanner-specific hides behind the declaration: the answer is
        a pure function of ``param_map``.
        """
        spec = NodeRealScanner.SPECS[Method.ACCOUNT_TRANSACTIONS]
        bare = replace(
            spec,
            param_map={
                public: wire
                for public, wire in spec.param_map.items()
                if public not in BLOCK_RANGE_PARAM_KEYS
            },
        )
        assert spec_declares_block_range(spec)
        assert not spec_declares_block_range(bare)

    def test_client_side_contract_filter_reads_declaration(self) -> None:
        """The token filter's accepted spellings come from the spec, not a literal.

        Both the pythonic name and the Etherscan-style alias filter items;
        a method whose spec declares no ``contract_address`` source (plain
        transactions) filters nothing.
        """
        erc20_spec = NodeRealScanner.SPECS[Method.ACCOUNT_ERC20_TRANSFERS]
        matching = {'contractAddress': CONTRACT.upper()}  # case-insensitive compare
        foreign = {'contractAddress': '0x' + '01' * 20}
        assert _filter_transfer_items(
            erc20_spec,
            [matching, foreign],
            {'address': ADDRESS, 'contractaddress': CONTRACT},
        ) == [matching]
        assert _filter_transfer_items(
            erc20_spec,
            [matching, foreign],
            {'address': ADDRESS, 'contract_address': CONTRACT},
        ) == [matching]
        # No declared source on the transactions spec: nothing to filter by.
        tx_spec = NodeRealScanner.SPECS[Method.ACCOUNT_TRANSACTIONS]
        assert _filter_transfer_items(tx_spec, [foreign], {'contractaddress': CONTRACT}) == [
            foreign
        ]


# ============================================================================
# Base-seam contract: one exception identity, laddered fetch_page, declared
# wire methods
# ============================================================================


class TestSeamContract:
    """The scanner stays inside the base seams: no ``call()`` override, the
    ladder on ``fetch_page``, and argument errors that keep one identity on
    every path.

    Before this contract held, the same caller mistake raised different
    types per seam: the ``call()`` ladder masked the bare ``ValueError`` into
    a TRANSIENT ``ChainscanNetworkError`` (which a provider pool reads as a
    provider fault — failover plus a cooldown on a healthy provider over a
    caller bug), while the ``fetch_page`` transfer path let the raw
    ``ValueError`` escape.
    """

    @pytest.mark.asyncio
    async def test_invalid_closest_same_type_from_call_and_fetch_page(self) -> None:
        scanner = _make_scanner()
        _mock_network(scanner, [])
        with pytest.raises(ScannerArgumentError) as from_call:
            await scanner.call(Method.BLOCK_NUMBER_BY_TIMESTAMP, timestamp=1, closest='nearest')
        with pytest.raises(ScannerArgumentError) as from_fetch_page:
            await scanner.fetch_page(
                Method.BLOCK_NUMBER_BY_TIMESTAMP, {'timestamp': 1, 'closest': 'nearest'}
            )
        # Exactly the argument type on BOTH seams — not one path masked into a
        # ChainscanNetworkError while the other escapes raw, the pre-fix split.
        assert type(from_call.value) is ScannerArgumentError
        assert type(from_fetch_page.value) is ScannerArgumentError

    @pytest.mark.asyncio
    async def test_missing_address_same_type_on_both_transfer_paths(self) -> None:
        # The sharper half: ``fetch_page`` does NOT route transfers through
        # call() (the window walk bypasses it), so the two assertions below
        # pin the identity on genuinely distinct code paths.
        call_scanner = _make_scanner()
        _mock_network(call_scanner, ['0x64'])  # eth_blockNumber tip
        with pytest.raises(ScannerArgumentError, match='address is required'):
            await call_scanner.call(Method.ACCOUNT_TRANSACTIONS)

        fetch_scanner = _make_scanner()
        _mock_network(fetch_scanner, ['0x64'])  # eth_blockNumber tip
        with pytest.raises(ScannerArgumentError, match='address is required'):
            await fetch_scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {})

    def test_argument_errors_classify_fatal_for_the_pool(self) -> None:
        assert classify_failure(ScannerArgumentError('address is required')) is FailureKind.FATAL

    @pytest.mark.asyncio
    async def test_fetch_page_applies_the_error_ladder(self) -> None:
        # An unexpected parser failure (a non-dict transfers item) from the
        # fetch_page seam is masked into a non-retryable ChainscanNetworkError
        # — the ladder contract of Scanner.fetch_page — not a raw TypeError.
        scanner = _make_scanner()
        _mock_network(scanner, ['0x64', {'pageKey': '', 'transfers': [5]}])
        with pytest.raises(ChainscanNetworkError) as excinfo:
            await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {'address': ADDRESS})
        assert excinfo.value.retryable is False

    @pytest.mark.asyncio
    async def test_fetch_page_keeps_chainscan_errors_unchanged(self) -> None:
        # The ladder must NOT rewrite provider-dialect translations: the
        # -32005 rate-limit translation the dialect raised inside the
        # transport stays a retryable rate-limit error out here.
        scanner = _make_scanner()
        _mock_network(
            scanner,
            [
                ChainscanRateLimitError(
                    'You have reached the maximum API usage limit', 'usage limit'
                )
            ],
        )
        with pytest.raises(ChainscanRateLimitError):
            await scanner.fetch_page(Method.TOKEN_HOLDER_COUNT, {'contract_address': CONTRACT})

    def test_every_rpc_dialect_spec_declares_a_wire_method(self) -> None:
        for method, spec in NodeRealScanner.SPECS.items():
            if spec.param_style in ('rpc-positional', 'rpc-object'):
                assert isinstance(spec.wire_method, str) and spec.wire_method, method
            else:
                # Query-style contract-REST specs: no JSON-RPC wire method.
                assert spec.wire_method is None, method
                assert method in NodeRealScanner._REST_METHODS, method

    @pytest.mark.asyncio
    async def test_call_filters_transfer_items_exactly_once(self) -> None:
        # The deleted call() override used to post-filter; the filter now
        # lives in _perform_request and must still apply exactly once.
        scanner = _make_scanner()
        other_contract = '0x0000000000000000000000000000000000000001'
        _mock_network(
            scanner,
            [
                {
                    'pageKey': '',
                    'transfers': [
                        {'hash': '0x1', 'blockNum': '0x1', 'contractAddress': CONTRACT},
                        {'hash': '0x2', 'blockNum': '0x2', 'contractAddress': other_contract},
                    ],
                }
            ],
        )

        items = await scanner.fetch_page(
            Method.ACCOUNT_ERC20_TRANSFERS,
            {'address': ADDRESS, 'contract_address': CONTRACT, 'end_block': 500},
        )

        assert isinstance(items, tuple)
        returned, cursor = items
        assert [item['hash'] for item in returned] == ['0x1']
        assert cursor is None  # window [0, 500] consumed: no phantom second pass
