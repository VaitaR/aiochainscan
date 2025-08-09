from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from aiochainscan import Client
from aiochainscan.adapters.aiohttp_graphql_client import AiohttpGraphQLClient
from aiochainscan.adapters.blockscout_graphql_builder import BlockscoutGraphQLBuilder
from aiochainscan.adapters.endpoint_builder_urlbuilder import UrlBuilderEndpoint
from aiochainscan.adapters.simple_provider_federator import SimpleProviderFederator
from aiochainscan.domain.models import TxHash
from aiochainscan.services.transaction import get_transaction_by_hash as get_tx_service


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


@pytest.mark.asyncio
async def test_check_tx_status(transaction):
    """Test check_tx_status method calls tx_receipt_status."""
    with patch.object(
        transaction, 'tx_receipt_status', new=AsyncMock(return_value={'status': '1'})
    ) as mock_tx_receipt:
        result = await transaction.check_tx_status('0xabcdef123456')
        mock_tx_receipt.assert_called_once_with('0xabcdef123456')
        assert result == {'status': '1'}

    # Test with another transaction hash
    with patch.object(
        transaction, 'tx_receipt_status', new=AsyncMock(return_value={'status': '0'})
    ) as mock_tx_receipt:
        result = await transaction.check_tx_status('0x987654321')
        mock_tx_receipt.assert_called_once_with('0x987654321')
        assert result == {'status': '0'}


@pytest.mark.asyncio
async def test_get_transaction_by_hash_graphql(monkeypatch):
    # Mock GraphQL execute to return a minimal but valid payload
    async def fake_execute(self, url, query, variables=None, headers=None):  # noqa: ARG001
        return {
            'transaction': {
                'hash': '0xabc',
                'blockNumber': 123,
                'fromAddressHash': '0xfrom',
                'toAddressHash': '0xto',
                'gas': '21000',
                'gasPrice': '100',
                'input': '0x',
            }
        }

    monkeypatch.setattr(
        'aiochainscan.adapters.aiohttp_graphql_client.AiohttpGraphQLClient.execute',
        fake_execute,
    )

    data = await get_tx_service(
        txhash=TxHash('0x' + '0' * 64),
        api_kind='blockscout_sepolia',
        network='sepolia',
        api_key='',
        http=None,  # type: ignore[arg-type]
        _endpoint_builder=UrlBuilderEndpoint(),
        _gql=AiohttpGraphQLClient(),
        _gql_builder=BlockscoutGraphQLBuilder(),
        _federator=SimpleProviderFederator(),
    )
    assert data.get('hash') == '0xabc'
