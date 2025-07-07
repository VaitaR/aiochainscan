from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from aiochainscan import Client


@pytest_asyncio.fixture
async def gas_tracker():
    c = Client('TestApiKey')
    yield c.gas_tracker
    await c.close()


@pytest.mark.asyncio
async def test_estimation_of_confirmation_time(gas_tracker):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await gas_tracker.estimation_of_confirmation_time(123)
        mock.assert_called_once_with(
            params={'module': 'gastracker', 'action': 'gasestimate', 'gasprice': 123}, headers={}
        )


@pytest.mark.asyncio
async def test_gas_oracle(gas_tracker):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await gas_tracker.gas_oracle()
        mock.assert_called_once_with(
            params={'module': 'gastracker', 'action': 'gasoracle'}, headers={}
        )


@pytest.mark.asyncio
async def test_daily_average_gas_limit(gas_tracker):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await gas_tracker.daily_average_gas_limit(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavggaslimit',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await gas_tracker.daily_average_gas_limit(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavggaslimit',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await gas_tracker.daily_average_gas_limit(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_total_gas_used(gas_tracker):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await gas_tracker.daily_total_gas_used(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailygasused',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await gas_tracker.daily_total_gas_used(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailygasused',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await gas_tracker.daily_total_gas_used(start_date, end_date, 'wrong')


@pytest.mark.asyncio
async def test_daily_average_gas_price(gas_tracker):
    start_date = date(2023, 11, 12)
    end_date = date(2023, 11, 13)

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await gas_tracker.daily_average_gas_price(start_date, end_date, 'asc')
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavggasprice',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': 'asc',
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await gas_tracker.daily_average_gas_price(start_date, end_date)
        mock.assert_called_once_with(
            params={
                'module': 'stats',
                'action': 'dailyavggasprice',
                'startdate': '2023-11-12',
                'enddate': '2023-11-13',
                'sort': None,
            },
            headers={},
        )

    with pytest.raises(ValueError):
        await gas_tracker.daily_average_gas_price(start_date, end_date, 'wrong')
