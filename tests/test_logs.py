from unittest.mock import AsyncMock, Mock, call, patch

import pytest
import pytest_asyncio

from aiochainscan import Client, Page, get_logs_page_typed, get_token_transfers_page_typed


@pytest_asyncio.fixture
async def logs():
    c = Client('TestApiKey')
    yield c.logs
    await c.close()


@pytest.mark.asyncio
async def test_balance(logs):
    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await logs.get_logs(
            start_block=1,
            end_block=2,
            address='addr',
            topics=[
                'topic',
            ],
        )
        mock.assert_called_once_with(
            params={
                'module': 'logs',
                'action': 'getLogs',
                'fromBlock': 1,
                'toBlock': 2,
                'address': 'addr',
                'topic0': 'topic',
                'page': None,
                'offset': None,
            },
            headers={},
        )

    with patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock:
        await logs.get_logs(
            start_block='latest',
            end_block='latest',
            address='addr',
            topics=[
                'topic',
            ],
        )
        mock.assert_called_once_with(
            params={
                'module': 'logs',
                'action': 'getLogs',
                'fromBlock': 'latest',
                'toBlock': 'latest',
                'address': 'addr',
                'topic0': 'topic',
                'page': None,
                'offset': None,
            },
            headers={},
        )

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.logs.Logs._check_block', new=Mock()) as block_mock,
    ):
        await logs.get_logs(
            start_block=1,
            end_block=2,
            address='addr',
            topics=['top1', 'top2'],
            topic_operators=['and'],
        )
        block_mock.assert_has_calls([call(1), call(2)])
        mock.assert_called_once()

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.logs.Logs._fill_topics', new=Mock()) as topic_mock,
    ):
        topic_mock.return_value = {}
        await logs.get_logs(
            start_block=1,
            end_block=2,
            address='addr',
            topics=[
                'topic',
            ],
        )
        topic_mock.assert_called_once_with(
            [
                'topic',
            ],
            None,
        )
        mock.assert_called_once()

    with (
        patch('aiochainscan.network.Network.get', new=AsyncMock()) as mock,
        patch('aiochainscan.modules.logs.Logs._fill_topics', new=Mock()) as topic_mock,
    ):
        topic_mock.return_value = {}
        await logs.get_logs(
            start_block=1,
            end_block=2,
            address='addr',
            topics=['top1', 'top2'],
            topic_operators=['and'],
        )
        topic_mock.assert_called_once_with(
            ['top1', 'top2'],
            ['and'],
        )
        mock.assert_called_once()


def test_check_block(logs):
    assert logs._check_block(1) == 1
    assert logs._check_block(0x1) == 1
    assert logs._check_block('latest') == 'latest'
    with pytest.raises(ValueError):
        logs._check_block('123')


def test_fill_topics(logs):
    assert logs._fill_topics(['top1'], None) == {'topic0': 'top1'}

    topics = ['top1', 'top2']
    topic_operators = ['or']
    assert logs._fill_topics(topics, topic_operators) == {
        'topic0': 'top1',
        'topic1': 'top2',
        'topic0_1_opr': 'or',
    }

    topics = ['top1', 'top2', 'top3']
    topic_operators = ['or', 'and']
    assert logs._fill_topics(topics, topic_operators) == {
        'topic0': 'top1',
        'topic1': 'top2',
        'topic2': 'top3',
        'topic0_1_opr': 'or',
        'topic1_2_opr': 'and',
    }

    with patch('aiochainscan.modules.logs.Logs._check_topics', new=Mock()) as check_topics_mock:
        logs._fill_topics(topics, topic_operators)
        check_topics_mock.assert_called_once_with(topics, topic_operators)


def test_check_topics(logs):
    with pytest.raises(ValueError):
        logs._check_topics([], [])

    with pytest.raises(ValueError):
        logs._check_topics([], ['xor'])

    with pytest.raises(ValueError):
        logs._check_topics(['top1'], ['or'])

    assert logs._check_topics(['top1', 'top2'], ['or']) is None


@pytest.mark.asyncio
async def test_get_logs_page_typed_graphql(monkeypatch):
    """Ensure GraphQL path is used and mapped to Page[LogEntryDTO]."""

    # Stub response matching BlockscoutGraphQLBuilder expectations
    gql_data = {
        'logs': {
            'pageInfo': {'endCursor': 'cursor123', 'hasNextPage': True},
            'edges': [
                {
                    'node': {
                        'addressHash': '0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef',
                        'blockNumber': 12345678,
                        'transactionHash': '0xabc',
                        'data': '0x',
                        'topics': ['0xfeed'],
                    }
                }
            ],
        }
    }

    called = {'count': 0}

    async def fake_execute(self, url, query, variables=None, headers=None):  # noqa: ARG001
        called['count'] += 1
        return gql_data

    # Patch the GraphQL client execute method
    monkeypatch.setattr(
        'aiochainscan.adapters.aiohttp_graphql_client.AiohttpGraphQLClient.execute',
        fake_execute,
    )

    page = await get_logs_page_typed(
        start_block=1,
        end_block=2,
        address='0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef',
        api_kind='blockscout_sepolia',
        network='sepolia',
        api_key='TEST_KEY',
        page_size=10,
    )

    assert isinstance(page, Page)
    assert page.next_cursor == 'cursor123'
    assert len(page.items) == 1
    item = page.items[0]
    assert item['address'].lower().startswith('0xdeadbeef')
    assert item['block_number'] == 12345678
    assert called['count'] == 1


@pytest.mark.asyncio
async def test_get_token_transfers_page_typed_graphql(monkeypatch):
    # Fake GraphQL response for Address.tokenTransfers
    gql_data = {
        'address': {
            'tokenTransfers': {
                'pageInfo': {'endCursor': 'tok_cursor', 'hasNextPage': True},
                'edges': [
                    {
                        'node': {
                            'transactionHash': '0xth',
                            'tokenContractAddressHash': '0xcontract',
                            'fromAddressHash': '0xfrom',
                            'toAddressHash': '0xto',
                            'amount': '1',
                            'logIndex': 1,
                            'blockNumber': 123,
                        }
                    }
                ],
            }
        }
    }

    async def fake_execute(self, url, query, variables=None, headers=None):  # noqa: ARG001
        return gql_data

    monkeypatch.setattr(
        'aiochainscan.adapters.aiohttp_graphql_client.AiohttpGraphQLClient.execute',
        fake_execute,
    )

    page = await get_token_transfers_page_typed(
        address='0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef',
        api_kind='blockscout_sepolia',
        network='sepolia',
        api_key='',
        first=10,
    )
    assert isinstance(page, Page)
    assert page.next_cursor == 'tok_cursor'
    assert len(page.items) == 1
