from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from aiochainscan import Client
from aiochainscan.exceptions import FeatureNotSupportedError


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
                'action': 'tokenbalancehistory',
                'address': 'a1',
                'contractaddress': 'c1',
                'blockno': 123,
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


@pytest.mark.asyncio
async def test_token_supply_new_method(token):
    """Test the new token_supply method with optional block_no parameter."""
    # Test without block_no (current supply)
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_supply('c1')
        mock.assert_called_once_with(
            params={'module': 'stats', 'action': 'tokensupply', 'contractaddress': 'c1'},
            headers={},
        )

    # Test with block_no (historical supply)
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_supply('c1', 123)
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
async def test_token_balance_new_method(token):
    """Test the new token_balance method with optional block_no parameter."""
    # Test without block_no (current balance)
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_balance('c1', 'a1')
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

    # Test with block_no (historical balance)
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await token.token_balance('c1', 'a1', 123)
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
async def test_token_supply_feature_not_supported():
    """Test that FeatureNotSupportedError is raised for unsupported scanners."""
    with patch('aiochainscan.config.config_manager.get_scanner_config') as mock_config:
        mock_config.return_value.name = 'Unsupported Scanner'

        c = Client('TestApiKey')
        c._url_builder._api_kind = 'unsupported_scanner'

        try:
            # Should work without block_no
            with patch('aiochainscan.network.Network.get', new=AsyncMock()):
                await c.token.token_supply('c1')

            # Should raise with block_no
            with pytest.raises(FeatureNotSupportedError) as exc_info:
                await c.token.token_supply('c1', 123)

            assert 'token_supply_by_block' in str(exc_info.value)
        finally:
            await c.close()


@pytest.mark.asyncio
async def test_token_balance_feature_not_supported():
    """Test that FeatureNotSupportedError is raised for unsupported scanners."""
    with patch('aiochainscan.config.config_manager.get_scanner_config') as mock_config:
        mock_config.return_value.name = 'Unsupported Scanner'

        c = Client('TestApiKey')
        c._url_builder._api_kind = 'unsupported_scanner'

        try:
            # Should work without block_no
            with patch('aiochainscan.network.Network.get', new=AsyncMock()):
                await c.token.token_balance('c1', 'a1')

            # Should raise with block_no
            with pytest.raises(FeatureNotSupportedError) as exc_info:
                await c.token.token_balance('c1', 'a1', 123)

            assert 'token_balance_by_block' in str(exc_info.value)
        finally:
            await c.close()
