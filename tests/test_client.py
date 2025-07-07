from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
import pytest_asyncio

from aiochainscan import Client
from aiochainscan.modules.account import Account
from aiochainscan.modules.block import Block
from aiochainscan.modules.contract import Contract
from aiochainscan.modules.extra.links import LinkHelper
from aiochainscan.modules.extra.utils import Utils
from aiochainscan.modules.logs import Logs
from aiochainscan.modules.proxy import Proxy
from aiochainscan.modules.stats import Stats
from aiochainscan.modules.transaction import Transaction
from aiochainscan.network import Network
from aiochainscan.url_builder import UrlBuilder


@pytest_asyncio.fixture
async def client():
    c = Client('TestApiKey')
    yield c
    await c.close()


def test_init(client):
    assert isinstance(client._url_builder, UrlBuilder)
    assert isinstance(client._http, Network)

    assert isinstance(client.account, Account)
    assert isinstance(client.block, Block)
    assert isinstance(client.contract, Contract)
    assert isinstance(client.transaction, Transaction)
    assert isinstance(client.stats, Stats)
    assert isinstance(client.logs, Logs)
    assert isinstance(client.proxy, Proxy)

    assert isinstance(client.utils, Utils)
    assert isinstance(client.links, LinkHelper)

    assert isinstance(client.account._client, Client)
    assert isinstance(client.block._client, Client)
    assert isinstance(client.contract._client, Client)
    assert isinstance(client.transaction._client, Client)
    assert isinstance(client.stats._client, Client)
    assert isinstance(client.logs._client, Client)
    assert isinstance(client.proxy._client, Client)

    assert isinstance(client.utils._client, Client)
    assert isinstance(client.links._url_builder, UrlBuilder)


@pytest.mark.asyncio
async def test_close_session(client):
    with patch('aiochainscan.network.Network.close', new_callable=AsyncMock) as m:
        await client.close()
        m.assert_called_once_with()


def test_currency(client):
    with patch('aiochainscan.url_builder.UrlBuilder.currency', new_callable=PropertyMock) as m:
        currency = 'ETH'
        m.return_value = currency

        assert client.currency == currency
        m.assert_called_once()
