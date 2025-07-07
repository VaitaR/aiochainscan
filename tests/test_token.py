from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from aiochainscan import Client


@pytest_asyncio.fixture
async def token():
    c = Client('TestApiKey')
    yield c.token
    await c.close()


@pytest.mark.asyncio
async def test_total_supply(token):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.total_supply('addr')
        mock.assert_called_once_with(
            params={'module': 'stats', 'action': 'tokensupply', 'contractaddress': 'addr'},
            headers={},
        )


@pytest.mark.asyncio
async def test_account_balance(token):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.account_balance('a1', 'c1')
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'tokenbalance',
                'address': 'a1',
                'contractaddress': 'c1',
                'tag': 'latest',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.account_balance('a1', 'c1', 123)
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'tokenbalance',
                'address': 'a1',
                'contractaddress': 'c1',
                'tag': '0x7b',
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_total_supply_by_blockno(token):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.total_supply_by_blockno('c1', 123)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'tokensupplyhistory',
                'contractaddress': 'c1',
                'blockno': 123,
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_account_balance_by_blockno(token):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.account_balance_by_blockno('a1', 'c1', 123)
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'tokenbalancehistory',
                'address': 'a1',
                'contractaddress': 'c1',
                'blockno': 123,
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_token_holder_list(token):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_holder_list('c1')
        mock.assert_called_once_with(
            params={
                'module': 'token',
                'action': 'tokenholderlist',
                'contractaddress': 'c1',
                'page': None,
                'offset': None,
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_holder_list('c1', 1, 10)
        mock.assert_called_once_with(
            params={
                'module': 'token',
                'action': 'tokenholderlist',
                'contractaddress': 'c1',
                'page': 1,
                'offset': 10,
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_token_info(token):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_info('c1')
        mock.assert_called_once_with(
            params={'module': 'token', 'action': 'tokeninfo', 'contractaddress': 'c1'}, headers={}
        )


@pytest.mark.asyncio
async def test_token_holding_erc20(token):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_holding_erc20('a1')
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'addresstokenbalance',
                'address': 'a1',
                'page': None,
                'offset': None,
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_holding_erc20('a1', 1, 10)
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'addresstokenbalance',
                'address': 'a1',
                'page': 1,
                'offset': 10,
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_token_holding_erc721(token):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_holding_erc721('a1')
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'addresstokennftbalance',
                'address': 'a1',
                'page': None,
                'offset': None,
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_holding_erc721('a1', 1, 10)
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'addresstokennftbalance',
                'address': 'a1',
                'page': 1,
                'offset': 10,
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_token_inventory(token):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_inventory('a1', 'c1')
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'addresstokennftinventory',
                'address': 'a1',
                'contractaddress': 'c1',
                'page': None,
                'offset': None,
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_inventory('a1', 'c1', 1, 10)
        mock.assert_called_once_with(
            params={
                'module': 'account',
                'action': 'addresstokennftinventory',
                'address': 'a1',
                'contractaddress': 'c1',
                'page': 1,
                'offset': 10,
            },
            headers={},
        )
