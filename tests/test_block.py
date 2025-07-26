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
    # Test with specific block number
    with patch(
        'aiochainscan.network.Network.get',
        new=AsyncMock(return_value={'status': '1', 'result': {'blockNumber': '123'}}),
    ) as mock:
        result = await block.block_reward(123)
        mock.assert_called_once_with(
            params={'module': 'block', 'action': 'getblockreward', 'blockno': 123}, headers={}
        )
        assert result == {'status': '1', 'result': {'blockNumber': '123'}}

    # Test with default (current block - 1)
    with (
        patch(
            'aiochainscan.modules.proxy.Proxy.block_number', new=AsyncMock(return_value='0x64')
        ) as proxy_mock,
        patch(
            'aiochainscan.network.Network.get',
            new=AsyncMock(return_value={'status': '1', 'result': {'blockNumber': '99'}}),
        ) as mock,
    ):
        result = await block.block_reward()
        proxy_mock.assert_called_once()
        mock.assert_called_once_with(
            params={'module': 'block', 'action': 'getblockreward', 'blockno': 99}, headers={}
        )

    # Test status='0' response (no reward available)
    with patch(
        'aiochainscan.network.Network.get',
        new=AsyncMock(return_value={'status': '0', 'message': 'No reward available'}),
    ):
        result = await block.block_reward(123)
        assert result is None


@pytest.mark.asyncio
async def test_block_countdown(block):
    # Test with default parameters (current + 1000)
    with (
        patch(
            'aiochainscan.modules.proxy.Proxy.block_number', new=AsyncMock(return_value='0x64')
        ) as proxy_mock,
        patch(
            'aiochainscan.network.Network.get',
            new=AsyncMock(return_value={'status': '1', 'result': {'countdownBlock': '1100'}}),
        ) as mock,
    ):
        result = await block.block_countdown()  # Default: current + 1000
        proxy_mock.assert_called_once()
        mock.assert_called_once_with(
            params={'module': 'block', 'action': 'getblockcountdown', 'blockno': 1100}, headers={}
        )

    # Test with custom offset
    with (
        patch('aiochainscan.modules.proxy.Proxy.block_number', new=AsyncMock(return_value='0x64')),
        patch(
            'aiochainscan.network.Network.get',
            new=AsyncMock(return_value={'status': '1', 'result': {'countdownBlock': '600'}}),
        ) as mock,
    ):
        result = await block.block_countdown(offset=500)
        mock.assert_called_once_with(
            params={'module': 'block', 'action': 'getblockcountdown', 'blockno': 600}, headers={}
        )

    # Test with specific future block
    with (
        patch('aiochainscan.modules.proxy.Proxy.block_number', new=AsyncMock(return_value='0x64')),
        patch(
            'aiochainscan.network.Network.get',
            new=AsyncMock(return_value={'status': '1', 'result': {'countdownBlock': '200'}}),
        ) as mock,
    ):
        result = await block.block_countdown(200)
        mock.assert_called_once_with(
            params={'module': 'block', 'action': 'getblockcountdown', 'blockno': 200}, headers={}
        )

    # Test with past block (should raise ValueError)
    with (
        patch(
            'aiochainscan.modules.proxy.Proxy.block_number', new=AsyncMock(return_value='0x64')
        ),  # current block = 100
        pytest.raises(ValueError, match='Past block for countdown'),
    ):
        await block.block_countdown(50)  # Past block

    # Test with current block (should raise ValueError)
    with (
        patch(
            'aiochainscan.modules.proxy.Proxy.block_number', new=AsyncMock(return_value='0x64')
        ),  # current block = 100
        pytest.raises(ValueError, match='Past block for countdown'),
    ):
        await block.block_countdown(100)  # Current block

    # Test with block difference too large
    with (
        patch(
            'aiochainscan.modules.proxy.Proxy.block_number', new=AsyncMock(return_value='0x64')
        ),  # current block = 100
        pytest.raises(ValueError, match='Block number too large'),
    ):
        await block.block_countdown(2_100_101)  # More than 2M blocks ahead

    # Test API error for "Block number too large"
    with (
        patch('aiochainscan.modules.proxy.Proxy.block_number', new=AsyncMock(return_value='0x64')),
        patch(
            'aiochainscan.network.Network.get',
            new=AsyncMock(
                return_value={'status': '0', 'message': 'Error! Block number too large'}
            ),
        ),
        pytest.raises(ValueError, match='Error! Block number too large'),
    ):
        await block.block_countdown(200)

    # Test "No transactions found" response
    with (
        patch('aiochainscan.modules.proxy.Proxy.block_number', new=AsyncMock(return_value='0x64')),
        patch(
            'aiochainscan.network.Network.get',
            new=AsyncMock(return_value={'status': '0', 'message': 'No transactions found'}),
        ),
    ):
        result = await block.block_countdown(200)
        assert result is None


@pytest.mark.asyncio
async def test_est_block_countdown_time(block):
    # Test the deprecated method with future block (mock current block as 100)
    with (
        patch('aiochainscan.modules.proxy.Proxy.block_number', new=AsyncMock(return_value='0x64')),
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
    ):
        await block.est_block_countdown_time(200)  # Future block
        mock.assert_called_once_with(
            params={'module': 'block', 'action': 'getblockcountdown', 'blockno': 200}, headers={}
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

    # Test with specific date parameters
    sample_response = {
        'status': '1',
        'result': [
            {
                'UTCDate': '2023-11-12',
                'unixTimeStamp': '1699747200',
                'blockCount': '7200',
                'blockRewards_Eth': '21600',
            }
        ],
    }

    with patch(
        'aiochainscan.network.Network.get', new=AsyncMock(return_value=sample_response)
    ) as mock:
        result = await block.daily_block_count(
            start_date=start_date, end_date=end_date, sort='asc'
        )
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
        assert result == sample_response

    # Test with default dates (should use today-30d to today)
    with patch('aiochainscan.modules.block.default_range') as date_mock:
        date_mock.return_value = (date(2023, 10, 13), date(2023, 11, 13))
        with patch(
            'aiochainscan.network.Network.get', new=AsyncMock(return_value=sample_response)
        ) as mock:
            result = await block.daily_block_count()
            date_mock.assert_called_once_with(days=30)
            mock.assert_called_once_with(
                params={
                    'module': 'stats',
                    'action': 'dailyblkcount',
                    'startdate': '2023-10-13',
                    'enddate': '2023-11-13',
                    'sort': None,
                },
                headers={},
            )

    # Test "No transactions found" response
    with patch(
        'aiochainscan.network.Network.get',
        new=AsyncMock(return_value={'status': '0', 'message': 'No transactions found'}),
    ):
        result = await block.daily_block_count(start_date=start_date, end_date=end_date)
        assert result is None

    # Test with partial date parameters (should use defaults for missing ones)
    with patch('aiochainscan.modules.block.default_range') as date_mock:
        date_mock.return_value = (date(2023, 10, 13), date(2023, 11, 13))
        with patch(
            'aiochainscan.network.Network.get', new=AsyncMock(return_value=sample_response)
        ) as mock:
            result = await block.daily_block_count(
                start_date=start_date
            )  # Only start_date provided
            date_mock.assert_called_once_with(days=30)
            mock.assert_called_once_with(
                params={
                    'module': 'stats',
                    'action': 'dailyblkcount',
                    'startdate': '2023-10-13',
                    'enddate': '2023-11-13',
                    'sort': None,
                },
                headers={},
            )


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
