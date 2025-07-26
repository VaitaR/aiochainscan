from unittest.mock import AsyncMock, Mock, call, patch

import pytest
import pytest_asyncio

from aiochainscan import Client


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
