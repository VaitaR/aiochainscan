from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from aiochainscan import Client


@pytest_asyncio.fixture
async def block():
    c = Client('TestApiKey')
    yield c.block
    await c.close()


@pytest.mark.asyncio
async def test_block_reward(block):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.block_reward(123)
        mock.assert_called_once_with(
            params={'module': 'block', 'action': 'getblockreward', 'blockno': 123}, headers={}
        )


@pytest.mark.asyncio
async def test_est_block_countdown_time(block):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.est_block_countdown_time(123)
        mock.assert_called_once_with(
            params={'module': 'block', 'action': 'getblockcountdown', 'blockno': 123}, headers={}
        )


@pytest.mark.asyncio
async def test_block_number_by_ts(block):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.block_number_by_ts(123, 'before')
        mock.assert_called_once_with(
            params={
                'module': 'block',
                'action': 'getblocknobytime',
                'timestamp': 123,
                'closest': 'before',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.block_number_by_ts(321, 'after')
        mock.assert_called_once_with(
            params={
                'module': 'block',
                'action': 'getblocknobytime',
                'timestamp': 321,
                'closest': 'after',
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await block.block_number_by_ts(
            ts=111,
            closest='wrong',
        )


@pytest.mark.asyncio
async def test_daily_average_block_size(block):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.daily_average_block_size(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavgblocksize',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.daily_average_block_size(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavgblocksize',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await block.daily_average_block_size(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_block_count(block):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.daily_block_count(start_date, end_date, 'asc')
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

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.daily_block_count(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyblkcount',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await block.daily_block_count(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_block_rewards(block):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.daily_block_rewards(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyblockrewards',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.daily_block_rewards(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyblockrewards',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await block.daily_block_rewards(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_average_time_for_a_block(block):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.daily_average_time_for_a_block(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavgblocktime',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.daily_average_time_for_a_block(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavgblocktime',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await block.daily_average_time_for_a_block(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_uncle_block_count(block):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.daily_uncle_block_count(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyuncleblkcount',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await block.daily_uncle_block_count(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyuncleblkcount',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await block.daily_uncle_block_count(start_date, end_date, 'wrong')
