from unittest.mock import AsyncMock, Mock, call, patch

import pytest
import pytest_asyncio

from aiochainscan import Client


@pytest_asyncio.fixture
async def proxy():
    c = Client('TestApiKey')
    yield c.proxy
    await c.close()


@pytest.mark.asyncio
async def test_balance(proxy):
    """Test balance method using account module first."""
    with patch.object(proxy._client.account, 'balance', new=AsyncMock(return_value='1000000000000000000')) as account_mock:
        result = await proxy.balance('0x123')
        account_mock.assert_called_once_with('0x123', 'latest')
        assert result == 1000000000000000000

    # Test with custom tag
    with patch.object(proxy._client.account, 'balance', new=AsyncMock(return_value='2000000000000000000')) as account_mock:
        result = await proxy.balance('0x456', 'earliest')
        account_mock.assert_called_once_with('0x456', 'earliest')
        assert result == 2000000000000000000


@pytest.mark.asyncio
async def test_balance_fallback_to_proxy(proxy):
    """Test balance method fallback to proxy endpoint when account fails."""
    # Mock account.balance to raise exception
    with (
        patch.object(proxy._client.account, 'balance', side_effect=Exception('Account API failed')),
        patch('aiochainscan.network.Network.get', new=AsyncMock(return_value='0xde0b6b3a7640000')) as mock_get,
    ):
        result = await proxy.balance('0x123')
        mock_get.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_getBalance',
                'address': '0x123',
                'tag': 'latest',
            },
            headers={},
        )
        assert result == 1000000000000000000  # 0xde0b6b3a7640000 in decimal


@pytest.mark.asyncio
async def test_balance_fallback_with_custom_tag(proxy):
    """Test balance method fallback with custom tag."""
    with (
        patch.object(proxy._client.account, 'balance', side_effect=Exception('Account API failed')),
        patch('aiochainscan.network.Network.get', new=AsyncMock(return_value='0x1bc16d674ec80000')) as mock_get,
        patch('aiochainscan.modules.proxy.check_tag', new=Mock(return_value='0x123')) as tag_mock,
    ):
        result = await proxy.balance('0x456', 'pending')
        tag_mock.assert_called_once_with('pending')
        mock_get.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_getBalance',
                'address': '0x456',
                'tag': '0x123',
            },
            headers={},
        )
        assert result == 2000000000000000000  # 0x1bc16d674ec80000 in decimal


@pytest.mark.asyncio
async def test_balance_fallback_non_hex_response(proxy):
    """Test balance method fallback with non-hex response."""
    with (
        patch.object(proxy._client.account, 'balance', side_effect=Exception('Account API failed')),
        patch('aiochainscan.network.Network.get', new=AsyncMock(return_value='1000000000000000000')) as mock_get,
    ):
        result = await proxy.balance('0x123')
        mock_get.assert_called_once()
        assert result == 1000000000000000000


@pytest.mark.asyncio
async def test_balance_both_methods_fail(proxy):
    """Test balance method when both account and proxy endpoints fail."""
    with (
        patch.object(proxy._client.account, 'balance', side_effect=Exception('Account API failed')),
        patch('aiochainscan.network.Network.get', side_effect=Exception('Proxy API failed')),
    ):
        # Should re-raise the account error after both fail
        with pytest.raises(Exception, match='Account API failed'):
            await proxy.balance('0x123')


@pytest.mark.asyncio
async def test_get_balance(proxy):
    """Test get_balance legacy alias."""
    with patch.object(proxy, 'balance', new=AsyncMock(return_value=5000000000000000000)) as balance_mock:
        result = await proxy.get_balance('0x789')
        balance_mock.assert_called_once_with('0x789', 'latest')
        assert result == 5000000000000000000

    # Test with custom tag
    with patch.object(proxy, 'balance', new=AsyncMock(return_value=3000000000000000000)) as balance_mock:
        result = await proxy.get_balance('0xabc', 'pending')
        balance_mock.assert_called_once_with('0xabc', 'pending')
        assert result == 3000000000000000000


@pytest.mark.asyncio
async def test_block_number(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.block_number()
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_blockNumber',
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_block_by_number(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.block_by_number(True)
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_getBlockByNumber',
                'boolean': True,
                'tag': 'latest',
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_tag', new=Mock()) as tag_mock,
    ):
        await proxy.block_by_number(True)
        tag_mock.assert_called_once_with('latest')
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_uncle_block_by_number_and_index(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.uncle_block_by_number_and_index(123)
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_getUncleByBlockNumberAndIndex',
                'index': '0x7b',
                'tag': 'latest',
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_hex', new=Mock()) as hex_mock,
        patch('aiochainscan.modules.proxy.check_tag', new=Mock()) as tag_mock,
    ):
        await proxy.uncle_block_by_number_and_index(123)
        hex_mock.assert_called_once_with(123)
        tag_mock.assert_called_once_with('latest')
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_block_tx_count_by_number(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.block_tx_count_by_number()
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_getBlockTransactionCountByNumber',
                'tag': 'latest',
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_tag', new=Mock()) as tag_mock,
    ):
        await proxy.block_tx_count_by_number(123)
        tag_mock.assert_called_once_with(123)
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_tx_by_hash(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.tx_by_hash('0x123')
        mock.assert_called_once_with(
            params={'module': 'proxy', 'action': 'eth_getTransactionByHash', 'txhash': '0x123'},
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_hex', new=Mock()) as hex_mock,
    ):
        await proxy.tx_by_hash(123)
        hex_mock.assert_called_once_with(123)
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_tx_by_number_and_index(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.tx_by_number_and_index(123)
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_getTransactionByBlockNumberAndIndex',
                'index': '0x7b',
                'tag': 'latest',
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_hex', new=Mock()) as hex_mock,
        patch('aiochainscan.modules.proxy.check_tag', new=Mock()) as tag_mock,
    ):
        await proxy.tx_by_number_and_index(123, 456)
        hex_mock.assert_called_once_with(123)
        tag_mock.assert_called_once_with(456)
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_tx_count(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.tx_count('addr')
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_getTransactionCount',
                'address': 'addr',
                'tag': 'latest',
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_tag', new=Mock()) as tag_mock,
    ):
        await proxy.tx_count('addr', 123)
        tag_mock.assert_called_once_with(123)
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_send_raw_tx(proxy):
    with patch('aiochainscan.network.Network.post', new=AsyncMock()) as mock:
        await proxy.send_raw_tx('somehex')
        mock.assert_called_once_with(
            data={
                'module': 'proxy',
                'action': 'eth_sendRawTransaction',
                'hex': 'somehex',
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_tx_receipt(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.tx_receipt('0x123')
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_getTransactionReceipt',
                'txhash': '0x123',
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_hex', new=Mock()) as hex_mock,
    ):
        await proxy.tx_receipt('0x123')
        hex_mock.assert_called_once_with('0x123')
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_call(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.call('0x123', '0x456')
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_call',
                'to': '0x123',
                'data': '0x456',
                'tag': 'latest',
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_hex', new=Mock()) as hex_mock,
        patch('aiochainscan.modules.proxy.check_tag', new=Mock()) as tag_mock,
    ):
        await proxy.call('0x123', '0x456', '0x789')
        hex_mock.assert_has_calls([call('0x123'), call('0x456')])
        tag_mock.assert_called_once_with('0x789')
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_code(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.code('addr')
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_getCode',
                'address': 'addr',
                'tag': 'latest',
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_tag', new=Mock()) as tag_mock,
    ):
        await proxy.code('addr', 123)
        tag_mock.assert_called_once_with(123)
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_storage_at(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.storage_at('addr', 'pos')
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_getStorageAt',
                'address': 'addr',
                'position': 'pos',
                'tag': 'latest',
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_tag', new=Mock()) as tag_mock,
    ):
        await proxy.storage_at('addr', 'pos', 123)
        tag_mock.assert_called_once_with(123)
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_gas_price(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.gas_price()
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_gasPrice',
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_estimate_gas(proxy):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await proxy.estimate_gas(to='0x123', value='val', gas_price='123', gas='456')
        mock.assert_called_once_with(
            params={
                'module': 'proxy',
                'action': 'eth_estimateGas',
                'to': '0x123',
                'value': 'val',
                'gasPrice': '123',
                'gas': '456',
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.proxy.check_hex', new=Mock()) as hex_mock,
    ):
        await proxy.estimate_gas(to='0x123', value='val', gas_price='123', gas='456')
        hex_mock.assert_called_once_with('0x123')
        mock.assert_called_once()
