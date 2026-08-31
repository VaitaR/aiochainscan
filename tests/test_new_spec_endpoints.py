"""Seam tests for previously-orphan Method endpoints and the get_block fix.

Each convenience-path behavior is driven through the real scanner
(``EtherscanV2`` / ``BlockScoutV2Scanner``) with a fake Network that records
the outgoing request. No live HTTP. The assertions pin the exact wire params
(module/action/param names) the API contract requires.
"""

from __future__ import annotations

from typing import Any

from aiochainscan.core.method import Method
from aiochainscan.core.url_builder import UrlBuilder
from aiochainscan.domain.models import Address
from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner
from aiochainscan.scanners.etherscan_v2 import EtherscanV2


class FakeNetwork:
    """Records every request; replays a canned JSON payload."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response

    async def get(self, **kwargs: Any) -> Any:
        return await self.request(method='GET', **kwargs)

    async def post(self, **kwargs: Any) -> Any:
        return await self.request(method='POST', **kwargs)


def _etherscan(network: FakeNetwork) -> EtherscanV2:
    return EtherscanV2(
        api_key='test_key',
        network='main',
        url_builder=UrlBuilder('test_key', 'eth', 'main'),
        network_client=network,
    )


def _blockscout(network: FakeNetwork) -> BlockScoutV2Scanner:
    return BlockScoutV2Scanner(
        api_key='',
        network='ethereum',
        url_builder=UrlBuilder('', 'eth', 'ethereum'),
        network_client=network,
    )


def _wire_params(fake: FakeNetwork) -> dict[str, Any]:
    assert len(fake.calls) == 1, f'expected one request, saw {fake.calls!r}'
    return dict(fake.calls[0]['params'])


# ---------------------------------------------------------------------------
# get_block: BLOCK_BY_NUMBER must reach Etherscan's proxy tag param
# ---------------------------------------------------------------------------


class TestGetBlockParamContract:
    async def test_etherscan_block_by_number_maps_block_number_to_tag(self) -> None:
        """Regression: get_block used to send an unmapped ``blockno`` param."""
        fake = FakeNetwork({'result': {'number': '0x1'}})
        result = await _etherscan(fake).call(Method.BLOCK_BY_NUMBER, block_number=19_500_000)
        params = _wire_params(fake)
        assert result == {'number': '0x1'}
        assert params['module'] == 'proxy'
        assert params['action'] == 'eth_getBlockByNumber'
        assert params['tag'] == 19_500_000
        assert 'blockno' not in params, 'blockno must be mapped to tag, not passed through'
        assert params['chainid'] == 1

    async def test_blockscout_block_by_number_substitutes_path_param(self) -> None:
        fake = FakeNetwork({'hash': '0xabc', 'height': 19_500_000})
        result = await _blockscout(fake).call(Method.BLOCK_BY_NUMBER, block_number=19_500_000)
        assert len(fake.calls) == 1
        assert fake.calls[0]['url'].endswith('/api/v2/blocks/19500000')
        assert result == {'hash': '0xabc', 'height': 19_500_000}


# ---------------------------------------------------------------------------
# Previously-orphan Methods now have real Etherscan v2 endpoints
# ---------------------------------------------------------------------------


class TestPreviouslyOrphanEtherscanEndpoints:
    async def test_erc721_transfers(self) -> None:
        fake = FakeNetwork({'result': []})
        await _etherscan(fake).call(
            Method.ACCOUNT_ERC721_TRANSFERS,
            address='0xA',
            contract_address='0xB',
            start_block=0,
            end_block=99,
            page=1,
            offset=100,
            sort='asc',
        )
        params = _wire_params(fake)
        assert params['module'] == 'account'
        assert params['action'] == 'tokennfttx'
        assert params['address'] == '0xA'
        assert params['contractaddress'] == '0xB'
        assert params['startblock'] == 0
        assert params['endblock'] == 99
        assert params['page'] == 1
        assert params['offset'] == 100
        assert params['sort'] == 'asc'

    async def test_erc1155_transfers(self) -> None:
        fake = FakeNetwork({'result': []})
        await _etherscan(fake).call(Method.ACCOUNT_ERC1155_TRANSFERS, address='0xA')
        params = _wire_params(fake)
        assert params['module'] == 'account'
        assert params['action'] == 'token1155tx'
        assert params['address'] == '0xA'

    async def test_tx_status_check(self) -> None:
        fake = FakeNetwork({'result': {'isError': '0'}})
        await _etherscan(fake).call(Method.TX_STATUS_CHECK, txhash='0x' + 'ab' * 32)
        params = _wire_params(fake)
        assert params['module'] == 'transaction'
        assert params['action'] == 'getstatus'
        assert params['txhash'] == '0x' + 'ab' * 32

    async def test_block_countdown(self) -> None:
        fake = FakeNetwork({'result': {'EstimateTimeInSec': '120'}})
        await _etherscan(fake).call(Method.BLOCK_COUNTDOWN, block_number=30_000_000)
        params = _wire_params(fake)
        assert params['module'] == 'block'
        assert params['action'] == 'getblockcountdown'
        assert params['blockno'] == 30_000_000

    async def test_block_number_by_timestamp(self) -> None:
        fake = FakeNetwork({'result': '12345'})
        await _etherscan(fake).call(
            Method.BLOCK_NUMBER_BY_TIMESTAMP, timestamp=1_609_459_200, closest='before'
        )
        params = _wire_params(fake)
        assert params['module'] == 'block'
        assert params['action'] == 'getblocknobytime'
        assert params['timestamp'] == 1_609_459_200
        assert params['closest'] == 'before'

    async def test_contract_creation(self) -> None:
        fake = FakeNetwork({'result': []})
        await _etherscan(fake).call(Method.CONTRACT_CREATION, contract_addresses='0xB,0xC')
        params = _wire_params(fake)
        assert params['module'] == 'contract'
        assert params['action'] == 'getcontractcreation'
        assert params['contractaddresses'] == '0xB,0xC'

    async def test_token_info(self) -> None:
        fake = FakeNetwork({'result': []})
        await _etherscan(fake).call(Method.TOKEN_INFO, contract_address='0xB')
        params = _wire_params(fake)
        assert params['module'] == 'token'
        assert params['action'] == 'tokeninfo'
        assert params['contractaddress'] == '0xB'

    async def test_gas_estimate(self) -> None:
        fake = FakeNetwork({'result': '120'})
        await _etherscan(fake).call(Method.GAS_ESTIMATE, gas_price=2_000_000_000)
        params = _wire_params(fake)
        assert params['module'] == 'gastracker'
        assert params['action'] == 'gasestimate'
        assert params['gasprice'] == 2_000_000_000

    async def test_proxy_get_balance(self) -> None:
        fake = FakeNetwork({'result': '0xde0b6b3a7640000'})
        await _etherscan(fake).call(Method.PROXY_GET_BALANCE, address='0xA', tag='latest')
        params = _wire_params(fake)
        assert params['module'] == 'proxy'
        assert params['action'] == 'eth_getBalance'
        assert params['address'] == '0xA'
        assert params['tag'] == 'latest'


# ---------------------------------------------------------------------------
# Client convenience methods drive the new specs end-to-end (still no HTTP)
# ---------------------------------------------------------------------------


def _client_with_fake_network(fake: FakeNetwork) -> Any:
    """Real ChainscanClient whose scanner talks to the fake network."""
    from aiochainscan.core.client import ChainscanClient

    client = ChainscanClient('etherscan', 'v2', 'eth', 'main', 'test_key')
    client._scanner._network_client = fake
    return client


class TestClientConvenienceThroughSeam:
    async def test_get_block_countdown_convenience_uses_blockno_wire_param(self) -> None:
        fake = FakeNetwork({'status': '1', 'result': {'EstimateTimeInSec': '120'}})
        client = _client_with_fake_network(fake)
        result = await client.get_block_countdown(30_000_000)
        assert result == {'EstimateTimeInSec': '120'}
        params = _wire_params(fake)
        assert params['module'] == 'block'
        assert params['action'] == 'getblockcountdown'
        assert params['blockno'] == 30_000_000

    async def test_get_block_convenience_sends_tag_not_blockno(self) -> None:
        fake = FakeNetwork({'result': {'number': '0x1'}})
        client = _client_with_fake_network(fake)
        await client.get_block(19_500_000)
        params = _wire_params(fake)
        assert params['tag'] == 19_500_000
        assert 'blockno' not in params

    async def test_check_transaction_status_convenience(self) -> None:
        fake = FakeNetwork({'result': {'isError': '0', 'errDescription': ''}})
        client = _client_with_fake_network(fake)
        result = await client.check_transaction_status('0x' + 'ab' * 32)
        assert result == {'isError': '0', 'errDescription': ''}
        params = _wire_params(fake)
        assert params['action'] == 'getstatus'

    async def test_get_contract_creation_convenience(self) -> None:
        fake = FakeNetwork(
            {'status': '1', 'result': [{'contractAddress': '0xC', 'txHash': '0xT'}]}
        )
        client = _client_with_fake_network(fake)
        contract = '0xdAC17F958D2ee523a2206208994597C13D831ec7'
        result = await client.get_contract_creation([contract])
        assert result == [{'contractAddress': '0xC', 'txHash': '0xT'}]
        params = _wire_params(fake)
        assert params['contractaddresses'] == str(Address(contract))

    async def test_get_erc721_transfers_convenience(self) -> None:
        fake = FakeNetwork({'status': '1', 'message': 'OK', 'result': [{'tokenID': '42'}]})
        client = _client_with_fake_network(fake)
        result = await client.get_erc721_transfers('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
        assert result == [{'tokenID': '42'}]
        params = _wire_params(fake)
        assert params['action'] == 'tokennfttx'
        assert params['offset'] == 100

    async def test_get_gas_estimate_convenience(self) -> None:
        fake = FakeNetwork({'status': '1', 'result': '120'})
        client = _client_with_fake_network(fake)
        result = await client.get_gas_estimate(2_000_000_000)
        assert result == '120'
        params = _wire_params(fake)
        assert params['gasprice'] == 2_000_000_000

    async def test_eth_get_balance_convenience(self) -> None:
        fake = FakeNetwork({'jsonrpc': '2.0', 'result': '0xde0b6b3a7640000'})
        client = _client_with_fake_network(fake)
        result = await client.eth_get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
        assert result == '0xde0b6b3a7640000'
        params = _wire_params(fake)
        assert params['action'] == 'eth_getBalance'
        assert params['tag'] == 'latest'
