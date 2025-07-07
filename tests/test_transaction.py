from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from aiochainscan import Client


@pytest_asyncio.fixture
async def transaction():
    c = Client('TestApiKey')
    yield c.transaction
    await c.close()


@pytest.mark.asyncio
async def test_contract_execution_status(transaction):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await transaction.contract_execution_status('0x123')
        mock.assert_called_once_with(
            params={'module': 'transaction', 'action': 'getstatus', 'txhash': '0x123'}, headers={}
        )


@pytest.mark.asyncio
async def test_tx_receipt_status(transaction):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await transaction.tx_receipt_status('0x123')
        mock.assert_called_once_with(
            params={'module': 'transaction', 'action': 'gettxreceiptstatus', 'txhash': '0x123'},
            headers={},
        )
