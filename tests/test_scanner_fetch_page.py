"""Contract tests for the Scanner pagination seam: ``Scanner.fetch_page``.

Port contract (see ``aiochainscan/scanners/base.py``):
- ``fetch_page(method, params)`` returns ``(items, next_cursor)``.
- ``next_cursor is None`` terminates pagination.
- A dict ``next_cursor`` is opaque; callers merge it into ``params`` for
  the next call.

The contract is proven by a fake adapter driven through
``ChainscanClient.iter_transactions`` plus the two real adapters
(BlockScout V2 cursor, Etherscan-like page/offset).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aiochainscan.constants import API_MAX_OFFSET_ETHERSCAN, API_MAX_OFFSET_LOGS
from aiochainscan.core.client import ChainscanClient
from aiochainscan.domain.method import Method
from aiochainscan.exceptions import ChainscanNetworkError
from aiochainscan.scanners.base import Scanner
from aiochainscan.scanners.blockscout_v1 import BlockScoutV1
from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner
from aiochainscan.scanners.etherscan_v2 import EtherscanV2
from aiochainscan.services.pagination import page_fetcher


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


class FakePaginatedScanner(Scanner):
    """Fake adapter speaking the fetch_page contract (never uses call())."""

    name = 'fake'
    version = 'test'
    supported_networks = {'main'}

    def __init__(self, pages: list[tuple[list[dict[str, Any]], dict[str, Any] | None]]) -> None:
        self.pages = list(pages)
        self.seen_params: list[dict[str, Any]] = []

    async def call(self, method: Method, **params: Any) -> Any:
        raise AssertionError('call() must not be used when fetch_page is the seam')

    async def fetch_page(
        self, method: Method, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        self.seen_params.append(dict(params))
        if not self.pages:
            raise AssertionError('client fetched more pages than the fake provides')
        items, cursor = self.pages.pop(0)
        return items, cursor


class FakeSinglePageScanner(Scanner):
    """Fake adapter relying on the base fetch_page default (routes via call())."""

    name = 'fake'
    version = 'test'
    supported_networks = {'main'}

    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def call(self, method: Method, **params: Any) -> Any:
        self.calls.append(params)
        return self.result


def _bare_client(scanner_name: str, scanner_version: str, scanner: Scanner) -> ChainscanClient:
    """Build a ChainscanClient shell around an injected scanner (no real wiring)."""
    client = ChainscanClient.__new__(ChainscanClient)
    client.scanner_name = scanner_name
    client.scanner_version = scanner_version
    client.api_kind = 'test'
    client.network = 'main'
    client.api_key = ''
    client._scanner = scanner
    return client


def _blockscout_scanner(network_client: FakeNetwork) -> BlockScoutV2Scanner:
    return BlockScoutV2Scanner(
        api_key='',
        network='ethereum',
        url_builder=MagicMock(),
        network_client=network_client,
    )


def _etherscan_scanner(network_client: FakeNetwork) -> EtherscanV2:
    return EtherscanV2(
        api_key='test_key',
        network='main',
        url_builder=MagicMock(),
        network_client=network_client,
    )


# ============================================================================
# Fake adapter: the cursor contract as consumed by ChainscanClient
# ============================================================================


class TestFakeAdapterContract:
    """A port-compliant fake proves the client loop honors the cursor contract."""

    @pytest.mark.asyncio
    async def test_items_flow_and_cursor_merges_into_next_params(self) -> None:
        fake = FakePaginatedScanner(
            [
                ([{'hash': '0x1'}], {'block_number': 5, 'index': 1}),
                ([{'hash': '0x2'}, {'hash': '0x3'}], None),
            ]
        )
        client = _bare_client('blockscout', 'v2', fake)

        txs = [tx async for tx in client.iter_transactions('0xabc')]

        assert [tx['hash'] for tx in txs] == ['0x1', '0x2', '0x3']
        # First page: the uniform public-dialect params every scanner now
        # receives (a real BlockScout V2 scanner filters the keys its
        # endpoint never took — see the real-adapter tests below).
        first = fake.seen_params[0]
        assert first['address'] == '0xabc'
        assert first['start_block'] == 0
        assert first['page'] == 1
        # Second page: the cursor was merged back into params
        second = fake.seen_params[1]
        assert second['address'] == '0xabc'
        assert second['block_number'] == 5
        assert second['index'] == 1
        # None cursor terminated iteration (no over-fetch)
        assert len(fake.seen_params) == 2

    @pytest.mark.asyncio
    async def test_empty_first_page_terminates_immediately(self) -> None:
        fake = FakePaginatedScanner([([], None)])
        client = _bare_client('blockscout', 'v2', fake)

        txs = [tx async for tx in client.iter_transactions('0xabc')]

        assert txs == []
        assert len(fake.seen_params) == 1

    @pytest.mark.asyncio
    async def test_error_from_port_propagates_after_yielding_first_page(self) -> None:
        fake = FakePaginatedScanner([([{'hash': '0x1'}], {'page': 2})])
        client = _bare_client('blockscout', 'v2', fake)

        async def fail_on_second_call(method: Method, params: dict[str, Any]):
            fake.seen_params.append(dict(params))
            if len(fake.seen_params) > 1:
                raise ChainscanNetworkError('All retries exhausted', retryable=True)
            items, _ = fake.pages.pop(0)
            return items, {'page': 2}

        fake.fetch_page = fail_on_second_call

        received: list[dict[str, Any]] = []
        with pytest.raises(ChainscanNetworkError):
            async for tx in client.iter_transactions('0xabc'):
                received.append(tx)

        assert [tx['hash'] for tx in received] == ['0x1']


# ============================================================================
# Base default: single page, cursor always None
# ============================================================================


class TestBaseFetchPageDefault:
    """The base implementation routes through call() and never continues."""

    @pytest.mark.asyncio
    async def test_list_result_yields_items_and_none_cursor(self) -> None:
        scanner = FakeSinglePageScanner([{'hash': '0x1'}])

        items, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc'})

        assert items == [{'hash': '0x1'}]
        assert cursor is None
        assert scanner.calls == [{'address': '0xabc'}]

    @pytest.mark.asyncio
    async def test_dict_result_coerces_items_key(self) -> None:
        scanner = FakeSinglePageScanner({'items': [{'hash': '0x1'}], 'extra': True})

        items, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {})

        assert items == [{'hash': '0x1'}]
        assert cursor is None

    @pytest.mark.asyncio
    async def test_none_items_coerce_to_empty_list(self) -> None:
        scanner = FakeSinglePageScanner({'items': None})

        items, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {})

        assert items == []
        assert cursor is None


# ============================================================================
# Real adapter: BlockScout V2 (next_page_params cursor)
# ============================================================================


class TestBlockScoutV2FetchPage:
    @pytest.mark.asyncio
    async def test_returns_items_and_next_page_params_cursor(self) -> None:
        net = FakeNetwork(
            [{'items': [{'hash': '0x1'}], 'next_page_params': {'block_number': 5, 'index': 0}}]
        )
        scanner = _blockscout_scanner(net)

        items, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc'})

        assert items == [{'hash': '0x1'}]
        assert cursor == {'block_number': 5, 'index': 0}
        # First request: address is a path param, so no query params are sent
        assert net.calls[0]['params'] is None
        assert net.calls[0]['url'].endswith('/api/v2/addresses/0xabc/transactions')
        assert net.calls[0]['method'] == 'GET'

    @pytest.mark.asyncio
    async def test_cursor_none_when_next_page_params_missing_or_falsy(self) -> None:
        for body in (
            {'items': [{'hash': '0x1'}], 'next_page_params': None},
            {'items': [{'hash': '0x1'}]},
            {'items': [{'hash': '0x1'}], 'next_page_params': {}},
        ):
            net = FakeNetwork([body])
            scanner = _blockscout_scanner(net)

            _, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc'})

            assert cursor is None, f'expected None cursor for {body}'

    @pytest.mark.asyncio
    async def test_merged_cursor_reaches_next_request_query_params(self) -> None:
        net = FakeNetwork(
            [
                {
                    'items': [{'hash': '0x1'}],
                    'next_page_params': {'block_number': 5, 'index': 1},
                },
                {'items': [{'hash': '0x2'}], 'next_page_params': None},
            ]
        )
        scanner = _blockscout_scanner(net)

        params: dict[str, Any] = {'address': '0xabc'}
        _, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, params)
        assert cursor is not None
        params = {**params, **cursor}
        items, cursor2 = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, params)

        assert items == [{'hash': '0x2'}]
        assert cursor2 is None
        assert net.calls[1]['params'] == {'block_number': 5, 'index': 1}

    @pytest.mark.asyncio
    async def test_remote_cursor_cannot_replace_path_address(self) -> None:
        net = FakeNetwork(
            [
                {
                    'items': [{'hash': '0x1'}],
                    'next_page_params': {
                        'address': '0xattacker',
                        'block_number': 5,
                        'index': 1,
                    },
                },
                {'items': [{'hash': '0x2'}], 'next_page_params': None},
            ]
        )
        scanner = _blockscout_scanner(net)

        params: dict[str, Any] = {'address': '0xoriginal'}
        _, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, params)

        assert cursor == {'block_number': 5, 'index': 1}
        params = {**params, **cursor}
        await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, params)
        assert net.calls[1]['url'].endswith('/api/v2/addresses/0xoriginal/transactions')

    @pytest.mark.asyncio
    async def test_unsupported_public_params_are_filtered_by_endpoint_spec(self) -> None:
        net = FakeNetwork([{'items': [], 'next_page_params': None}])
        scanner = _blockscout_scanner(net)

        await scanner.fetch_page(
            Method.ACCOUNT_TRANSACTIONS,
            {
                'address': '0xabc',
                'start_block': 1,
                'end_block': 2,
                'page': 1,
                'offset': 10,
                'tag': 'latest',
            },
        )

        assert net.calls[0]['params'] is None

    @pytest.mark.asyncio
    async def test_list_response_fallback_yields_no_cursor(self) -> None:
        net = FakeNetwork([[{'hash': '0x1'}, {'hash': '0x2'}]])
        scanner = _blockscout_scanner(net)

        items, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc'})

        assert items == [{'hash': '0x1'}, {'hash': '0x2'}]
        assert cursor is None

    @pytest.mark.asyncio
    async def test_call_still_returns_parsed_items_without_cursor(self) -> None:
        net = FakeNetwork([{'items': [{'hash': '0x1'}], 'next_page_params': {'block_number': 5}}])
        scanner = _blockscout_scanner(net)

        result = await scanner.call(Method.ACCOUNT_TRANSACTIONS, address='0xabc')

        assert result == [{'hash': '0x1'}]

    @pytest.mark.asyncio
    async def test_unsupported_method_raises_value_error(self) -> None:
        net = FakeNetwork([])
        scanner = _blockscout_scanner(net)

        with pytest.raises(ValueError, match='not supported'):
            await scanner.fetch_page(Method.TX_BY_HASH, {'address': '0xabc'})

    @pytest.mark.asyncio
    async def test_network_error_propagates_unwrapped(self) -> None:
        net = FakeNetwork([ChainscanNetworkError('Connection reset', retryable=True)])
        scanner = _blockscout_scanner(net)

        with pytest.raises(ChainscanNetworkError):
            await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc'})


# ============================================================================
# Real adapter: Etherscan-like (page/offset cursor)
# ============================================================================


class TestEtherscanLikeFetchPage:
    @pytest.mark.asyncio
    async def test_full_page_returns_cursor_to_next_page(self) -> None:
        net = FakeNetwork(
            [{'status': '1', 'message': 'OK', 'result': [{'hash': '0x1'}, {'hash': '0x2'}]}]
        )
        scanner = _etherscan_scanner(net)

        items, cursor = await scanner.fetch_page(
            Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc', 'page': 1, 'offset': 2}
        )

        assert items == [{'hash': '0x1'}, {'hash': '0x2'}]
        assert cursor == {'page': 2, 'offset': 2}
        sent = net.calls[0]['params']
        assert sent['page'] == 1
        assert sent['offset'] == 2
        assert sent['address'] == '0xabc'

    @pytest.mark.asyncio
    async def test_partial_page_terminates(self) -> None:
        net = FakeNetwork([{'status': '1', 'message': 'OK', 'result': [{'hash': '0x1'}]}])
        scanner = _etherscan_scanner(net)

        items, cursor = await scanner.fetch_page(
            Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc', 'page': 1, 'offset': 2}
        )

        assert items == [{'hash': '0x1'}]
        assert cursor is None

    @pytest.mark.asyncio
    async def test_empty_page_terminates(self) -> None:
        net = FakeNetwork([{'status': '1', 'message': 'OK', 'result': []}])
        scanner = _etherscan_scanner(net)

        items, cursor = await scanner.fetch_page(
            Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc', 'page': 1, 'offset': 2}
        )

        assert items == []
        assert cursor is None

    @pytest.mark.asyncio
    async def test_merged_cursor_requests_next_page(self) -> None:
        net = FakeNetwork(
            [
                {'status': '1', 'message': 'OK', 'result': [{'hash': '0x1'}, {'hash': '0x2'}]},
                {'status': '1', 'message': 'OK', 'result': [{'hash': '0x3'}]},
            ]
        )
        scanner = _etherscan_scanner(net)

        params: dict[str, Any] = {'address': '0xabc', 'page': 1, 'offset': 2}
        _, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, params)
        assert cursor is not None
        params = {**params, **cursor}
        _, cursor2 = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, params)

        assert cursor2 is None
        assert net.calls[1]['params']['page'] == 2
        assert net.calls[1]['params']['offset'] == 2

    @pytest.mark.asyncio
    async def test_missing_offset_terminates_after_one_page(self) -> None:
        net = FakeNetwork([{'status': '1', 'message': 'OK', 'result': [{'hash': '0x1'}]}])
        scanner = _etherscan_scanner(net)

        _, cursor = await scanner.fetch_page(Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc'})

        assert cursor is None


# ============================================================================
# Provider caps: per-endpoint result windows and unpaginable specs
# ============================================================================


def _blockscout_v1_scanner(network_client: FakeNetwork) -> BlockScoutV1:
    return BlockScoutV1(
        api_key='',
        network='eth',
        url_builder=MagicMock(),
        network_client=network_client,
    )


class TestUnpaginableSpecStopsAfterOnePage:
    """A spec that maps neither page nor offset has exactly one page.

    BlockScout V1's ``getLogs`` is that spec: the params never reach the wire,
    so a "next page" repeats the first one verbatim (verified live against
    eth.blockscout.com — the same 1000 logs on every page).
    """

    @pytest.mark.asyncio
    async def test_full_log_page_yields_no_cursor(self) -> None:
        net = FakeNetwork([{'status': '1', 'message': 'OK', 'result': [{'logIndex': '0x0'}] * 2}])
        scanner = _blockscout_v1_scanner(net)

        items, cursor = await scanner.fetch_page(
            Method.EVENT_LOGS, {'address': '0xabc', 'page': 1, 'offset': 2}
        )

        assert len(items) == 2
        assert cursor is None

    @pytest.mark.asyncio
    async def test_paginable_spec_still_advances(self) -> None:
        net = FakeNetwork(
            [{'status': '1', 'message': 'OK', 'result': [{'hash': '0x1'}, {'hash': '0x2'}]}]
        )
        scanner = _blockscout_v1_scanner(net)

        _, cursor = await scanner.fetch_page(
            Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc', 'page': 1, 'offset': 2}
        )

        assert cursor == {'page': 2, 'offset': 2}


class TestPerMethodResultWindow:
    def test_blockscout_v1_logs_window_is_the_endpoint_limit(self) -> None:
        scanner = _blockscout_v1_scanner(FakeNetwork([]))

        assert scanner.result_window_for(Method.EVENT_LOGS) == API_MAX_OFFSET_LOGS
        assert scanner.result_window_for(Method.ACCOUNT_TRANSACTIONS) == API_MAX_OFFSET_ETHERSCAN

    def test_etherscan_keeps_one_window_for_every_method(self) -> None:
        scanner = _etherscan_scanner(FakeNetwork([]))

        assert scanner.result_window_for(Method.EVENT_LOGS) == API_MAX_OFFSET_ETHERSCAN
        assert scanner.result_window_for(Method.ACCOUNT_TRANSACTIONS) == API_MAX_OFFSET_ETHERSCAN

    def test_cursor_provider_declares_no_window(self) -> None:
        scanner = _blockscout_scanner(FakeNetwork([]))

        assert scanner.result_window_for(Method.ACCOUNT_TRANSACTIONS) is None

    def test_binding_carries_the_per_method_window(self) -> None:
        scanner = _blockscout_v1_scanner(FakeNetwork([]))

        logs = page_fetcher(scanner, Method.EVENT_LOGS)
        txs = page_fetcher(scanner, Method.ACCOUNT_TRANSACTIONS)

        assert logs.result_window == API_MAX_OFFSET_LOGS
        assert txs.result_window == API_MAX_OFFSET_ETHERSCAN


# ============================================================================
# Client loop over the real adapters (same HTTP sequence as before)
# ============================================================================


class TestClientIterTransactionsOverPort:
    @pytest.mark.asyncio
    async def test_blockscout_streaming_continues_after_short_cursor_page(self) -> None:
        net = FakeNetwork(
            [
                {
                    'items': [{'hash': '0x1'}],
                    'next_page_params': {'block_number': 5, 'index': 1},
                },
                {'items': [{'hash': '0x2'}], 'next_page_params': None},
            ]
        )
        scanner = _blockscout_scanner(net)
        client = _bare_client('blockscout', 'v2', scanner)
        client._network = net

        batches = [
            batch async for batch in client.iter_transactions_streaming('0xabc', batch_size=10)
        ]

        assert batches == [[{'hash': '0x1'}], [{'hash': '0x2'}]]
        assert len(net.calls) == 2
        assert net.calls[1]['params']['block_number'] == 5
        assert net.calls[1]['params']['index'] == 1

    @pytest.mark.asyncio
    async def test_blockscout_pagination_via_fetch_page(self) -> None:
        net = FakeNetwork(
            [
                {
                    'items': [{'hash': '0x1'}, {'hash': '0x2'}],
                    'next_page_params': {'block_number': 5, 'index': 1},
                },
                {'items': [{'hash': '0x3'}], 'next_page_params': None},
            ]
        )
        scanner = _blockscout_scanner(net)
        client = _bare_client('blockscout', 'v2', scanner)
        client._network = net

        txs = [tx async for tx in client.iter_transactions('0xabc')]

        assert [tx['hash'] for tx in txs] == ['0x1', '0x2', '0x3']
        assert len(net.calls) == 2
        assert net.calls[1]['params'] == {'block_number': 5, 'index': 1}

    @pytest.mark.asyncio
    async def test_blockscout_network_error_propagates_mid_iteration(self) -> None:
        net = FakeNetwork(
            [
                {'items': [{'hash': '0x1'}], 'next_page_params': {'block_number': 5}},
                ChainscanNetworkError('All retries exhausted', retryable=True),
            ]
        )
        scanner = _blockscout_scanner(net)
        client = _bare_client('blockscout', 'v2', scanner)
        client._network = net

        received: list[dict[str, Any]] = []
        with pytest.raises(ChainscanNetworkError):
            async for tx in client.iter_transactions('0xabc'):
                received.append(tx)

        assert [tx['hash'] for tx in received] == ['0x1']

    @pytest.mark.asyncio
    async def test_etherscan_stops_on_partial_page(self) -> None:
        net = FakeNetwork(
            [
                {'status': '1', 'message': 'OK', 'result': [{'hash': '0x1'}, {'hash': '0x2'}]},
                {'status': '1', 'message': 'OK', 'result': [{'hash': '0x3'}]},
            ]
        )
        scanner = _etherscan_scanner(net)
        client = _bare_client('etherscan', 'v2', scanner)
        client._network = net

        txs = [tx async for tx in client.iter_transactions('0xabc', batch_size=2)]

        assert [tx['hash'] for tx in txs] == ['0x1', '0x2', '0x3']
        assert len(net.calls) == 2
        assert net.calls[0]['params']['page'] == 1
        assert net.calls[1]['params']['page'] == 2

    @pytest.mark.asyncio
    async def test_blockscout_v1_uses_etherscan_pagination(self) -> None:
        net = FakeNetwork(
            [
                {
                    'status': '1',
                    'message': 'OK',
                    'result': [{'hash': '0x1'}, {'hash': '0x2'}],
                },
                {'status': '1', 'message': 'OK', 'result': [{'hash': '0x3'}]},
            ]
        )
        scanner = _etherscan_scanner(net)
        client = _bare_client('blockscout', 'v1', scanner)
        client._network = net

        txs = [tx async for tx in client.iter_transactions('0xabc', batch_size=2)]

        assert [tx['hash'] for tx in txs] == ['0x1', '0x2', '0x3']
        assert len(net.calls) == 2
        assert net.calls[0]['params']['page'] == 1
        assert net.calls[0]['params']['offset'] == 2
        assert net.calls[1]['params']['page'] == 2
