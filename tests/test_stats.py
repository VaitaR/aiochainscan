from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from aiochainscan import Client


@pytest_asyncio.fixture
async def stats():
    c = Client('TestApiKey')
    yield c.stats
    await c.close()


@pytest.mark.asyncio
async def test_eth_supply(stats):
    with patch(
        'aiochainscan.network.Network.get', new=AsyncMock(return_value={'result': '1'})
    ) as mock:
        value = await stats.eth_supply()
        assert isinstance(value, str)
        assert mock.await_count == 1


@pytest.mark.asyncio
async def test_eth2_supply(stats):
    with patch(
        'aiochainscan.network.Network.get', new=AsyncMock(return_value={'result': '2'})
    ) as mock:
        value = await stats.eth2_supply()
        assert isinstance(value, str)
        assert mock.await_count == 1


@pytest.mark.asyncio
async def test_eth_price(stats):
    with patch(
        'aiochainscan.network.Network.get', new=AsyncMock(return_value={'result': {'ethusd': '1'}})
    ) as mock:
        data = await stats.eth_price()
        assert isinstance(data, dict)
        assert mock.await_count == 1


@pytest.mark.asyncio
async def test_eth_nodes_size(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.eth_nodes_size(start_date, end_date, 'geth', 'default', 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'chainsize',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'clienttype': 'geth',
                'syncmode': 'default',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.eth_nodes_size(
            start_date,
            end_date,
            'geth',
            'default',
        )
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'chainsize',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'clienttype': 'geth',
                'syncmode': 'default',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await stats.eth_nodes_size(start_date, end_date, 'wrong', 'default', 'asc')

    with pytest.raises(ValueError):
        await stats.eth_nodes_size(start_date, end_date, 'geth', 'wrong', 'asc')

    with pytest.raises(ValueError):
        await stats.eth_nodes_size(start_date, end_date, 'geth', 'default', 'wrong')


@pytest.mark.asyncio
async def test_nodes_size(stats):
    # Test with default parameters (should use today-30d to today)
    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.stats._default_date_range') as date_mock,
    ):
        date_mock.return_value = (date(2023, 11, 1), date(2023, 12, 1))
        await stats.nodes_size()
        assert mock.await_count == 1

    # Test with custom parameters
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.nodes_size(start=start_date, end=end_date, client='parity', sync='archive')
        assert mock.await_count == 1

    # Test return None for empty result
    with patch('aiochainscan.network.Network.get', new=AsyncMock(return_value=[])) as mock:
        result = await stats.nodes_size()
        assert result is None

    # Test with validation errors
    with pytest.raises(ValueError):
        await stats.nodes_size(client='invalid')

    with pytest.raises(ValueError):
        await stats.nodes_size(sync='invalid')


@pytest.mark.asyncio
async def test_total_nodes_count(stats):
    with patch(
        'aiochainscan.network.Network.get', new=AsyncMock(return_value={'result': {'total': 1}})
    ) as mock:
        data = await stats.total_nodes_count()
        assert isinstance(data, dict)
        assert data.get('total') == 1
        assert mock.await_count == 1


@pytest.mark.asyncio
async def test_daily_network_tx_fee(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_network_tx_fee(start_date, end_date, 'asc')
        assert mock.await_count == 1

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_network_tx_fee(start_date, end_date)
        assert mock.await_count == 1

    with pytest.raises(ValueError):
        await stats.daily_network_tx_fee(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_new_address_count(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_new_address_count(start_date, end_date, 'asc')
        assert mock.await_count == 1

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_new_address_count(start_date, end_date)
        assert mock.await_count == 1

    with pytest.raises(ValueError):
        await stats.daily_new_address_count(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_network_utilization(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_network_utilization(start_date, end_date, 'asc')
        assert mock.await_count == 1

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_network_utilization(start_date, end_date)
        assert mock.await_count == 1

    with pytest.raises(ValueError):
        await stats.daily_network_utilization(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_average_network_hash_rate(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_average_network_hash_rate(start_date, end_date, 'asc')
        assert mock.await_count == 1

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_average_network_hash_rate(start_date, end_date)
        assert mock.await_count == 1

    with pytest.raises(ValueError):
        await stats.daily_average_network_hash_rate(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_transaction_count(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_transaction_count(start_date, end_date, 'asc')
        assert mock.await_count == 1

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_transaction_count(start_date, end_date)
        assert mock.await_count == 1

    with pytest.raises(ValueError):
        await stats.daily_transaction_count(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_average_network_difficulty(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_average_network_difficulty(start_date, end_date, 'asc')
        assert mock.await_count == 1

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_average_network_difficulty(start_date, end_date)
        assert mock.await_count == 1

    with pytest.raises(ValueError):
        await stats.daily_average_network_difficulty(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_ether_historical_daily_market_cap(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.ether_historical_daily_market_cap(start_date, end_date, 'asc')
        assert mock.await_count == 1

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.ether_historical_daily_market_cap(start_date, end_date)
        assert mock.await_count == 1

    with pytest.raises(ValueError):
        await stats.ether_historical_daily_market_cap(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_ether_historical_price(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.ether_historical_price(start_date, end_date, 'asc')
        assert mock.await_count == 1

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.ether_historical_price(start_date, end_date)
        assert mock.await_count == 1

    with pytest.raises(ValueError):
        await stats.ether_historical_price(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_block_count(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    # Test with default sort
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_block_count(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyblkcount',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    # Test with custom sort
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_block_count(start_date, end_date, sort='desc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyblkcount',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'desc',
            },
            headers={},
        )

    # Test return None for empty result
    with patch('aiochainscan.network.Network.get', new=AsyncMock(return_value=[])) as mock:
        result = await stats.daily_block_count(start_date, end_date)
        assert result is None

    # Test with sample data response
    sample_response = [
        {
            'UTCDate': '2023-11-12',
            'unixTimeStamp': '1699747200',
            'blockCount': '7000',
            'blockRewards_Eth': '21000.5',
        }
    ]
    with patch(
        'aiochainscan.network.Network.get', new=AsyncMock(return_value=sample_response)
    ) as mock:
        result = await stats.daily_block_count(start_date, end_date)
        assert result == sample_response
