from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from aiochainscan import Client
from aiochainscan.exceptions import FeatureNotSupportedError


@pytest_asyncio.fixture
async def account():
    c = Client('TestApiKey')
    yield c.account
    await c.close()


@pytest.mark.asyncio
async def test_balance(account):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.balance('addr')
        mock.assert_called_once_with(
            params={'module': 'account', 'action': 'balance', 'address': 'addr', 'tag': 'latest'},
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.balance('addr', 123)
        mock.assert_called_once_with(
            params={'module': 'account', 'action': 'balance', 'address': 'addr', 'tag': '0x7b'},
            headers={},
        )


@pytest.mark.asyncio
async def test_balances(account):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.balances(['a1', 'a2'])
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'balancemulti',
                'address': 'a1,a2',
                'tag': 'latest',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.balances(['a1', 'a2'], 123)
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'balancemulti',
                'address': 'a1,a2',
                'tag': '0x7b',
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_normal_txs(account):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.normal_txs('addr')
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'txlist',
                'address': 'addr',
                'startblock': None,
                'endblock': None,
                'sort': None,
                'page': None,
                'offset': None,
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.normal_txs(
            address='addr', start_block=1, end_block=2, sort='asc', page=3, offset=4
        )
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'txlist',
                'address': 'addr',
                'startblock': 1,
                'endblock': 2,
                'sort': 'asc',
                'page': 3,
                'offset': 4,
            },
            headers={},
        )
    with pytest.raises(ValueError):
        await account.normal_txs(
            address='addr',
            sort='wrong',
        )


@pytest.mark.asyncio
async def test_internal_txs(account):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.internal_txs('addr')
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'txlistinternal',
                'address': 'addr',
                'startblock': None,
                'endblock': None,
                'sort': None,
                'page': None,
                'offset': None,
                'txhash': None,
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.internal_txs(
            address='addr',
            start_block=1,
            end_block=2,
            sort='asc',
            page=3,
            offset=4,
            txhash='0x123',
        )
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'txlistinternal',
                'address': 'addr',
                'startblock': 1,
                'endblock': 2,
                'sort': 'asc',
                'page': 3,
                'offset': 4,
                'txhash': '0x123',
            },
            headers={},
        )
    with pytest.raises(ValueError):
        await account.internal_txs(
            address='addr',
            sort='wrong',
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'token_standard,expected_action',
    [
        ('erc20', 'tokentx'),
        ('erc721', 'tokennfttx'),
        ('erc1155', 'token1155tx'),
    ],
)
async def test_token_transfers(account, token_standard, expected_action):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.token_transfers('addr')
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'tokentx',
                'address': 'addr',
                'startblock': None,
                'endblock': None,
                'sort': None,
                'page': None,
                'offset': None,
                'contractaddress': None,
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.token_transfers(
            address='addr',
            start_block=1,
            end_block=2,
            sort='asc',
            page=3,
            offset=4,
            contract_address='0x123',
        )
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'tokentx',
                'address': 'addr',
                'startblock': 1,
                'endblock': 2,
                'sort': 'asc',
                'page': 3,
                'offset': 4,
                'contractaddress': '0x123',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.token_transfers(
            address='addr',
            start_block=1,
            end_block=2,
            sort='asc',
            page=3,
            offset=4,
            contract_address='0x123',
            token_standard=token_standard,
        )
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': expected_action,
                'address': 'addr',
                'startblock': 1,
                'endblock': 2,
                'sort': 'asc',
                'page': 3,
                'offset': 4,
                'contractaddress': '0x123',
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await account.token_transfers(
            address='addr',
            sort='wrong',
        )
    with pytest.raises(ValueError):
        await account.token_transfers(start_block=123)


@pytest.mark.asyncio
async def test_mined_blocks(account):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.mined_blocks('addr')
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'getminedblocks',
                'address': 'addr',
                'blocktype': 'blocks',
                'page': None,
                'offset': None,
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.mined_blocks(address='addr', blocktype='uncles', page=1, offset=2)
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'getminedblocks',
                'address': 'addr',
                'blocktype': 'uncles',
                'page': 1,
                'offset': 2,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await account.mined_blocks(
            address='addr',
            blocktype='wrong',
        )


@pytest.mark.asyncio
async def test_beacon_chain_withdrawals(account):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.beacon_chain_withdrawals('addr')
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'txsBeaconWithdrawal',
                'address': 'addr',
                'startblock': None,
                'endblock': None,
                'sort': None,
                'page': None,
                'offset': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await account.beacon_chain_withdrawals(
            address='addr',
            sort='wrong',
        )


@pytest.mark.asyncio
async def test_account_balance_by_blockno(account):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.account_balance_by_blockno('a1', 123)
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'balancehistory',
                'address': 'a1',
                'blockno': 123,
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_erc20_transfers(account):
    # Test default parameters
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.erc20_transfers('addr')
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'tokentx',
                'address': 'addr',
                'startblock': 0,
                'endblock': 99999999,
                'page': 1,
                'offset': 100,
            },
            headers={},
        )

    # Test custom parameters
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await account.erc20_transfers('addr', startblock=1000, endblock=2000, page=2, offset=50)
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'tokentx',
                'address': 'addr',
                'startblock': 1000,
                'endblock': 2000,
                'page': 2,
                'offset': 50,
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_erc20_transfers_feature_not_supported():
    """Test that FeatureNotSupportedError is raised for unsupported scanners."""
    # Create a client with an unsupported scanner
    from aiochainscan.config import config_manager

    with patch.object(config_manager, 'get_scanner_config') as mock_config:
        mock_config.return_value.name = 'Unsupported Scanner'

        # Create client with URL builder that has unsupported scanner
        c = Client('TestApiKey')
        c._url_builder._api_kind = 'unsupported_scanner'

        try:
            with pytest.raises(FeatureNotSupportedError) as exc_info:
                await c.account.erc20_transfers('addr')

            assert 'erc20_transfers' in str(exc_info.value)
            assert 'Unsupported Scanner' in str(exc_info.value)
        finally:
            await c.close()
