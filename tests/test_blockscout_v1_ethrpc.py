"""BlockScout V1 JSON-RPC proxy fallback (``POST /api/eth-rpc``).

The BlockScout compatibility REST answers ``"Unknown module"`` for
``module=proxy``, so ``TX_BY_HASH`` / ``PROXY_ETH_CALL`` /
``PROXY_GET_BALANCE`` route through the instance's JSON-RPC endpoint — the
same keyless transport the chain-info probe uses. Verified live against
``eth.blockscout.com`` (2026-09): ``module=proxy`` → 400 ``"Unknown
module"``, ``POST /api/eth-rpc`` → JSON-RPC result.

The fakes below replay transport-level payloads: ``Network`` unwraps the
JSON-RPC envelope (``result`` returned directly) and raises
``ChainscanClientProxyError`` for JSON-RPC errors before the scanner sees
the response.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aiochainscan.domain.method import Method
from aiochainscan.exceptions import ChainscanClientProxyError
from aiochainscan.scanners.blockscout_v1 import BlockScoutV1


class FakeNetwork:
    """Records requests, replays canned responses."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _scanner(network: FakeNetwork) -> BlockScoutV1:
    return BlockScoutV1(
        api_key='',
        network='eth',
        url_builder=MagicMock(),
        network_client=network,
    )


class TestEthRpcRouting:
    async def test_eth_call_routes_to_eth_rpc(self) -> None:
        network = FakeNetwork('0x' + 'ff' * 32)
        scanner = _scanner(network)
        result = await scanner.call(
            Method.PROXY_ETH_CALL, to='0xabc', data='0x70a08231', tag='latest'
        )
        assert result == '0x' + 'ff' * 32
        call = network.calls[0]
        assert call['method'] == 'POST'
        assert call['url'] == 'https://eth.blockscout.com/api/eth-rpc'
        assert call['json_data'] == {
            'jsonrpc': '2.0',
            'method': 'eth_call',
            'params': [{'to': '0xabc', 'data': '0x70a08231'}, 'latest'],
            'id': 1,
        }

    async def test_eth_get_balance_routes_to_eth_rpc(self) -> None:
        network = FakeNetwork('0x1')
        scanner = _scanner(network)
        result = await scanner.call(Method.PROXY_GET_BALANCE, address='0xabc', tag='latest')
        assert result == '0x1'
        assert network.calls[0]['json_data']['method'] == 'eth_getBalance'
        assert network.calls[0]['json_data']['params'] == ['0xabc', 'latest']

    async def test_tx_by_hash_routes_to_eth_rpc(self) -> None:
        tx = {'hash': '0x' + 'ab' * 32, 'blockNumber': '0x1'}
        network = FakeNetwork(tx)
        scanner = _scanner(network)
        result = await scanner.call(Method.TX_BY_HASH, txhash='0x' + 'ab' * 32)
        assert result == tx
        assert network.calls[0]['json_data']['method'] == 'eth_getTransactionByHash'
        assert network.calls[0]['json_data']['params'] == ['0x' + 'ab' * 32]

    async def test_block_by_number_routes_to_eth_rpc(self) -> None:
        """Regression: ``module=proxy&action=eth_getBlockByNumber`` is dead on
        live BlockScout (``{"message": "Unknown module"}``) — the block must
        be served through ``/api/eth-rpc``. The JSON-RPC result (hex-quantity
        block dict, full transactions) is passed through unchanged, matching
        what the Etherscan proxy module returns for the same method."""
        block = {
            'number': '0x1b4',
            'hash': '0x' + 'cd' * 32,
            'parentHash': '0x' + 'ce' * 32,
            'timestamp': '0x5beca34',
            'transactions': [{'hash': '0x' + 'ab' * 32}],
        }
        network = FakeNetwork(block)
        scanner = _scanner(network)
        result = await scanner.call(Method.BLOCK_BY_NUMBER, block_number=436)
        assert result == block
        call = network.calls[0]
        assert call['method'] == 'POST'
        assert call['url'] == 'https://eth.blockscout.com/api/eth-rpc'
        assert call['json_data'] == {
            'jsonrpc': '2.0',
            'method': 'eth_getBlockByNumber',
            'params': ['0x1b4', True],
            'id': 1,
        }

    async def test_block_by_number_latest_tag_passthrough(self) -> None:
        network = FakeNetwork({'number': '0x2'})
        scanner = _scanner(network)
        await scanner.call(Method.BLOCK_BY_NUMBER, block_number='latest')
        assert network.calls[0]['json_data']['params'] == ['latest', True]

    async def test_block_by_number_decimal_string_becomes_hex_tag(self) -> None:
        network = FakeNetwork({'number': '0x1298be0'})
        scanner = _scanner(network)
        await scanner.call(Method.BLOCK_BY_NUMBER, block_number='19500000')
        assert network.calls[0]['json_data']['params'] == ['0x1298be0', True]

    async def test_custom_base_url_uses_own_root(self) -> None:
        network = FakeNetwork('0x1')
        scanner = BlockScoutV1(
            api_key='',
            network='custom',
            url_builder=MagicMock(),
            network_client=network,
            base_url='https://my-blockscout.internal',
        )
        await scanner.call(Method.PROXY_ETH_CALL, to='0xabc', data='0x')
        assert network.calls[0]['url'] == 'https://my-blockscout.internal/api/eth-rpc'


class TestEthRpcResults:
    async def test_null_result_returns_none(self) -> None:
        network = FakeNetwork(None)
        scanner = _scanner(network)
        assert await scanner.call(Method.TX_BY_HASH, txhash='0x' + 'ab' * 32) is None

    async def test_rpc_error_propagates_from_transport(self) -> None:
        network = FakeNetwork(ChainscanClientProxyError(3, 'execution reverted: nope'))
        scanner = _scanner(network)
        with pytest.raises(ChainscanClientProxyError, match='execution reverted'):
            await scanner.call(Method.PROXY_ETH_CALL, to='0xabc', data='0x')


class TestNonProxyMethodsUnchanged:
    async def test_balance_still_uses_compat_rest(self) -> None:
        network = FakeNetwork({'status': '1', 'message': 'OK', 'result': '42'})
        scanner = _scanner(network)
        result = await scanner.call(Method.ACCOUNT_BALANCE, address='0xabc', tag='latest')
        assert result == '42'
        call = network.calls[0]
        assert call['method'] == 'GET'
        assert call['url'].endswith('/api')
        assert call['params']['module'] == 'account'
