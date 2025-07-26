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
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.eth_supply()
        mock.assert_called_once_with(params={'module': 'stats', 'action': 'ethsupply'}, headers={})


@pytest.mark.asyncio
async def test_eth2_supply(stats):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.eth2_supply()
        mock.assert_called_once_with(
            params={'module': 'stats', 'action': 'ethsupply2'}, headers={}
        )


@pytest.mark.asyncio
async def test_eth_price(stats):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.eth_price()
        mock.assert_called_once_with(params={'module': 'stats', 'action': 'ethprice'}, headers={})


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
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'chainsize',
                'startdate': '2023-11-01',
                'enddate': '2023-12-01',
                'clienttype': 'geth',
                'syncmode': 'default',
            },
            headers={},
        )

    # Test with custom parameters
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.nodes_size(start=start_date, end=end_date, client='parity', sync='archive')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'chainsize',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'clienttype': 'parity',
                'syncmode': 'archive',
            },
            headers={},
        )

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
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.total_nodes_count()
        mock.assert_called_once_with(params={'module': 'stats', 'action': 'nodecount'}, headers={})


@pytest.mark.asyncio
async def test_daily_network_tx_fee(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_network_tx_fee(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailytxnfee',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_network_tx_fee(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailytxnfee',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await stats.daily_network_tx_fee(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_new_address_count(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_new_address_count(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailynewaddress',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_new_address_count(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailynewaddress',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await stats.daily_new_address_count(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_network_utilization(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_network_utilization(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailynetutilization',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_network_utilization(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailynetutilization',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await stats.daily_network_utilization(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_average_network_hash_rate(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_average_network_hash_rate(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavghashrate',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_average_network_hash_rate(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavghashrate',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await stats.daily_average_network_hash_rate(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_transaction_count(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_transaction_count(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailytx',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_transaction_count(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailytx',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await stats.daily_transaction_count(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_average_network_difficulty(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_average_network_difficulty(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavgnetdifficulty',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.daily_average_network_difficulty(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavgnetdifficulty',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await stats.daily_average_network_difficulty(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_ether_historical_daily_market_cap(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.ether_historical_daily_market_cap(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'ethdailymarketcap',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.ether_historical_daily_market_cap(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'ethdailymarketcap',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await stats.ether_historical_daily_market_cap(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_ether_historical_price(stats):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.ether_historical_price(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'ethdailyprice',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await stats.ether_historical_price(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'ethdailyprice',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

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
            "UTCDate": "2023-11-12",
            "unixTimeStamp": "1699747200",
            "blockCount": "7000",
            "blockRewards_Eth": "21000.5"
        }
    ]
    with patch('aiochainscan.network.Network.get', new=AsyncMock(return_value=sample_response)) as mock:
        result = await stats.daily_block_count(start_date, end_date)
        assert result == sample_response
