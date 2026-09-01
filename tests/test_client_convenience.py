"""
Tests for ChainscanClient convenience methods.

Verifies that every Method enum value is accessible via a typed convenience
method on ChainscanClient, and that critical data-integrity bugs
(silent truncation, whale block) are addressed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method
from aiochainscan.domain.models import Address, TxHash

TEST_ADDRESS = '0x1111111111111111111111111111111111111111'
TEST_CONTRACT = '0x2222222222222222222222222222222222222222'
TEST_TX_HASH = '0x' + ('a' * 64)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> ChainscanClient:
    """Create a ChainscanClient with a mocked scanner (no network calls)."""
    with patch('aiochainscan.core.client.get_scanner_class'):
        return ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'test_key')


@pytest.fixture
def mock_call(client: ChainscanClient) -> AsyncMock:
    """Patch ``client.call`` so tests never hit the network."""
    m = AsyncMock()
    client.call = m  # type: ignore[assignment]
    return m


# ---------------------------------------------------------------------------
# Single-page convenience methods → Method enum mapping
# ---------------------------------------------------------------------------


class TestSinglePageConvenienceMethods:
    """Each test verifies that the convenience method delegates to the right Method."""

    @pytest.mark.asyncio
    async def test_get_balance(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = '1000000000000000000'
        result = await client.get_balance(TEST_ADDRESS)
        mock_call.assert_awaited_once_with(
            Method.ACCOUNT_BALANCE,
            address=str(Address(TEST_ADDRESS)),
            tag='latest',
        )
        assert result == '1000000000000000000'

    @pytest.mark.asyncio
    async def test_get_transactions(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = [{'hash': '0x1'}]
        result = await client.get_transactions(TEST_ADDRESS)
        assert mock_call.await_args is not None
        assert mock_call.await_args[0][0] == Method.ACCOUNT_TRANSACTIONS
        assert result == [{'hash': '0x1'}]

    @pytest.mark.asyncio
    async def test_get_transactions_non_list(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = {'items': [{'hash': '0x1'}]}
        assert await client.get_transactions(TEST_ADDRESS) == []

    @pytest.mark.asyncio
    async def test_blockscout_v1_forwards_transaction_filters(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        client.scanner_name = 'blockscout'
        mock_call.return_value = []

        await client.get_transactions(TEST_ADDRESS, start_block=5, end_block=10, page=2, offset=25)

        mock_call.assert_awaited_once_with(
            Method.ACCOUNT_TRANSACTIONS,
            address=str(Address(TEST_ADDRESS)),
            start_block=5,
            end_block=10,
            page=2,
            offset=25,
        )

    @pytest.mark.asyncio
    async def test_get_token_transfers(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = [{'hash': '0xT'}]
        result = await client.get_token_transfers(TEST_ADDRESS)
        mock_call.assert_awaited_once_with(
            Method.ACCOUNT_ERC20_TRANSFERS,
            address=str(Address(TEST_ADDRESS)),
            start_block=0,
        )
        assert result == [{'hash': '0xT'}]

    @pytest.mark.asyncio
    async def test_get_token_transfers_forwards_zero_end_block(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = []
        await client.get_token_transfers(TEST_ADDRESS, end_block=0)
        mock_call.assert_awaited_once_with(
            Method.ACCOUNT_ERC20_TRANSFERS,
            address=str(Address(TEST_ADDRESS)),
            start_block=0,
            end_block=0,
        )

    @pytest.mark.asyncio
    async def test_get_token_transfers_forwards_nonzero_end_block(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = []
        await client.get_token_transfers(TEST_ADDRESS, end_block=200)
        mock_call.assert_awaited_once_with(
            Method.ACCOUNT_ERC20_TRANSFERS,
            address=str(Address(TEST_ADDRESS)),
            start_block=0,
            end_block=200,
        )

    @pytest.mark.asyncio
    async def test_get_internal_transactions(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = [{'hash': '0xI'}]
        result = await client.get_internal_transactions(TEST_ADDRESS)
        assert mock_call.await_args is not None
        assert mock_call.await_args[0][0] == Method.ACCOUNT_INTERNAL_TXS
        assert result == [{'hash': '0xI'}]

    @pytest.mark.asyncio
    async def test_get_internal_transactions_non_list(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = 'No records found'
        result = await client.get_internal_transactions(TEST_ADDRESS)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_erc721_transfers(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = [{'tokenID': '42'}]
        result = await client.get_erc721_transfers(TEST_ADDRESS)
        assert mock_call.await_args is not None
        assert mock_call.await_args[0][0] == Method.ACCOUNT_ERC721_TRANSFERS
        assert result == [{'tokenID': '42'}]

    @pytest.mark.asyncio
    async def test_get_erc1155_transfers(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = [{'tokenValue': '100'}]
        result = await client.get_erc1155_transfers(TEST_ADDRESS)
        assert mock_call.await_args is not None
        assert mock_call.await_args[0][0] == Method.ACCOUNT_ERC1155_TRANSFERS
        assert result == [{'tokenValue': '100'}]

    @pytest.mark.asyncio
    async def test_get_token_portfolio(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = [{'symbol': 'USDC'}]
        result = await client.get_token_portfolio(TEST_ADDRESS)
        assert mock_call.await_args is not None
        assert mock_call.await_args[0][0] == Method.ACCOUNT_TOKEN_PORTFOLIO
        assert result == [{'symbol': 'USDC'}]

    @pytest.mark.asyncio
    async def test_get_token_portfolio_non_list(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = {'items': [{'symbol': 'USDC'}]}
        assert await client.get_token_portfolio(TEST_ADDRESS) == []

    @pytest.mark.asyncio
    async def test_get_nft_portfolio(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = [{'token_id': '1'}]
        result = await client.get_nft_portfolio(TEST_ADDRESS)
        assert mock_call.await_args is not None
        assert mock_call.await_args[0][0] == Method.ACCOUNT_NFT_PORTFOLIO
        assert result == [{'token_id': '1'}]

    @pytest.mark.asyncio
    async def test_get_nft_portfolio_dict_response(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        """BlockScout V2 wraps in {items: [...]}."""
        mock_call.return_value = {'items': [{'token_id': '1'}]}
        result = await client.get_nft_portfolio(TEST_ADDRESS)
        assert result == [{'token_id': '1'}]

    @pytest.mark.asyncio
    async def test_get_transaction(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = {'hash': '0xT', 'value': '0'}
        result = await client.get_transaction(TEST_TX_HASH)
        mock_call.assert_awaited_once_with(Method.TX_BY_HASH, txhash=str(TxHash(TEST_TX_HASH)))
        assert result == {'hash': '0xT', 'value': '0'}

    @pytest.mark.asyncio
    async def test_get_transaction_status(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = {'status': '1'}
        result = await client.get_transaction_status(TEST_TX_HASH)
        mock_call.assert_awaited_once_with(
            Method.TX_RECEIPT_STATUS,
            txhash=str(TxHash(TEST_TX_HASH)),
        )
        assert result == {'status': '1'}

    @pytest.mark.asyncio
    async def test_check_transaction_status(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = {'isError': '0', 'errDescription': ''}
        result = await client.check_transaction_status(TEST_TX_HASH)
        mock_call.assert_awaited_once_with(
            Method.TX_STATUS_CHECK,
            txhash=str(TxHash(TEST_TX_HASH)),
        )
        assert result == {'isError': '0', 'errDescription': ''}

    @pytest.mark.asyncio
    async def test_get_block(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = {'blockNumber': '123'}
        result = await client.get_block(123)
        mock_call.assert_awaited_once_with(Method.BLOCK_BY_NUMBER, block_number=123)
        assert result == {'blockNumber': '123'}

    @pytest.mark.asyncio
    async def test_get_block_reward(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = {'blockReward': '2000000000000000000'}
        result = await client.get_block_reward(100)
        mock_call.assert_awaited_once_with(Method.BLOCK_REWARD, block_number=100)
        assert result == {'blockReward': '2000000000000000000'}

    @pytest.mark.asyncio
    async def test_get_block_countdown(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = {'EstimateTimeInSec': '120'}
        result = await client.get_block_countdown(999999)
        mock_call.assert_awaited_once_with(Method.BLOCK_COUNTDOWN, block_number=999999)
        assert result == {'EstimateTimeInSec': '120'}

    @pytest.mark.asyncio
    async def test_get_block_by_timestamp(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = {'blockNumber': '12345'}
        result = await client.get_block_by_timestamp(1609459200, closest='before')
        mock_call.assert_awaited_once_with(
            Method.BLOCK_NUMBER_BY_TIMESTAMP, timestamp=1609459200, closest='before'
        )
        assert result == {'blockNumber': '12345'}

    @pytest.mark.asyncio
    async def test_get_contract_abi(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = '[{"type":"function"}]'
        result = await client.get_contract_abi(TEST_CONTRACT)
        mock_call.assert_awaited_once_with(
            Method.CONTRACT_ABI, address=str(Address(TEST_CONTRACT))
        )
        assert result == '[{"type":"function"}]'

    @pytest.mark.asyncio
    async def test_get_contract_abi_serializes_list(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = [{'type': 'function'}]
        assert await client.get_contract_abi(TEST_CONTRACT) == '[{"type": "function"}]'

    @pytest.mark.asyncio
    async def test_get_contract_source(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = {'SourceCode': 'pragma solidity'}
        result = await client.get_contract_source(TEST_CONTRACT)
        mock_call.assert_awaited_once_with(
            Method.CONTRACT_SOURCE,
            address=str(Address(TEST_CONTRACT)),
        )
        assert result == {'SourceCode': 'pragma solidity'}

    @pytest.mark.asyncio
    async def test_get_contract_source_selects_first_dict_from_list(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = [{'SourceCode': 'pragma solidity'}, {'ignored': True}]
        assert await client.get_contract_source(TEST_CONTRACT) == {'SourceCode': 'pragma solidity'}

    @pytest.mark.asyncio
    async def test_get_contract_source_non_dict_returns_empty(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = 'No records found'
        assert await client.get_contract_source(TEST_CONTRACT) == {}

    @pytest.mark.asyncio
    async def test_get_contract_creation(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = [{'contractAddress': '0xC', 'txHash': '0xT'}]
        result = await client.get_contract_creation([TEST_CONTRACT])
        assert mock_call.await_args is not None
        assert mock_call.await_args[0][0] == Method.CONTRACT_CREATION
        assert result == [{'contractAddress': '0xC', 'txHash': '0xT'}]

    @pytest.mark.asyncio
    async def test_get_token_balance(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = '1000000'
        result = await client.get_token_balance(TEST_ADDRESS, TEST_CONTRACT)
        assert mock_call.await_args is not None
        assert mock_call.await_args[0][0] == Method.TOKEN_BALANCE
        assert result == '1000000'

    @pytest.mark.asyncio
    async def test_get_token_supply(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = '1000000000000'
        result = await client.get_token_supply(TEST_CONTRACT)
        mock_call.assert_awaited_once_with(Method.TOKEN_SUPPLY, contract_address=TEST_CONTRACT)
        assert result == '1000000000000'

    @pytest.mark.asyncio
    async def test_get_token_info(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = {'symbol': 'USDT', 'decimals': '6'}
        result = await client.get_token_info(TEST_CONTRACT)
        mock_call.assert_awaited_once_with(
            Method.TOKEN_INFO,
            contract_address=str(Address(TEST_CONTRACT)),
        )
        assert result == {'symbol': 'USDT', 'decimals': '6'}

    @pytest.mark.asyncio
    async def test_get_eth_price(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = {'ethusd': '3500'}
        result = await client.get_eth_price()
        mock_call.assert_awaited_once_with(Method.ETH_PRICE)
        assert result == {'ethusd': '3500'}

    @pytest.mark.asyncio
    async def test_get_eth_supply(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = '120000000000000000000000000'
        result = await client.get_eth_supply()
        mock_call.assert_awaited_once_with(Method.ETH_SUPPLY)
        assert result == '120000000000000000000000000'

    @pytest.mark.asyncio
    async def test_get_gas_oracle(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = {'SafeGasPrice': '20', 'FastGasPrice': '50'}
        result = await client.get_gas_oracle()
        mock_call.assert_awaited_once_with(Method.GAS_ORACLE)
        assert result == {'SafeGasPrice': '20', 'FastGasPrice': '50'}

    @pytest.mark.asyncio
    async def test_get_gas_estimate(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = '120'
        result = await client.get_gas_estimate(2000000000)
        mock_call.assert_awaited_once_with(Method.GAS_ESTIMATE, gas_price=2000000000)
        assert result == '120'

    @pytest.mark.asyncio
    async def test_get_logs_single_page(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = [{'logIndex': '0'}]
        result = await client.get_logs(TEST_CONTRACT, from_block=100, to_block=200)
        mock_call.assert_awaited_once_with(
            Method.EVENT_LOGS,
            address=str(Address(TEST_CONTRACT)),
            from_block=100,
            to_block=200,
        )
        assert result == [{'logIndex': '0'}]

    @pytest.mark.asyncio
    async def test_get_logs_forwards_zero_to_block(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = []
        await client.get_logs(TEST_CONTRACT, to_block=0)
        mock_call.assert_awaited_once_with(
            Method.EVENT_LOGS,
            address=str(Address(TEST_CONTRACT)),
            from_block=0,
            to_block=0,
        )

    @pytest.mark.asyncio
    async def test_get_logs_non_list_returns_empty(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = 'No records found'
        result = await client.get_logs(TEST_CONTRACT)
        mock_call.assert_awaited_once_with(
            Method.EVENT_LOGS,
            address=str(Address(TEST_CONTRACT)),
            from_block=0,
            to_block='latest',
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_eth_call(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = '0x0000000000000000000000000000000000000001'
        result = await client.eth_call(TEST_CONTRACT, '0x70a08231...')
        mock_call.assert_awaited_once_with(
            Method.PROXY_ETH_CALL,
            to=TEST_CONTRACT,
            data='0x70a08231...',
            tag='latest',
        )
        assert result == '0x0000000000000000000000000000000000000001'

    @pytest.mark.asyncio
    async def test_eth_get_balance(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = '0xde0b6b3a7640000'
        result = await client.eth_get_balance(TEST_ADDRESS)
        mock_call.assert_awaited_once_with(
            Method.PROXY_GET_BALANCE,
            address=TEST_ADDRESS,
            tag='latest',
        )
        assert result == '0xde0b6b3a7640000'


# ---------------------------------------------------------------------------
# Paginated convenience methods (get_all_*)
# ---------------------------------------------------------------------------


class TestPaginatedConvenienceMethods:
    """Test that get_all_* methods correctly accumulate streaming batches."""

    @pytest.mark.asyncio
    async def test_get_all_transactions(self, client: ChainscanClient) -> None:
        async def fake_stream(*args: Any, **kwargs: Any) -> AsyncIterator[list[dict[str, Any]]]:
            yield [{'hash': '0x1'}, {'hash': '0x2'}]
            yield [{'hash': '0x3'}]

        client.iter_transactions_streaming = fake_stream  # type: ignore[assignment]

        result = await client.get_all_transactions('0xABC')
        assert len(result) == 3
        assert result[0]['hash'] == '0x1'
        assert result[2]['hash'] == '0x3'

    @pytest.mark.asyncio
    async def test_get_all_transactions_warns_on_large_aggregation(
        self, client: ChainscanClient, monkeypatch, caplog
    ) -> None:
        from aiochainscan.core.mixins import account as account_mixin

        monkeypatch.setattr(account_mixin, 'AGGREGATION_WARNING_THRESHOLD', 4)

        async def fake_stream(*args: Any, **kwargs: Any) -> AsyncIterator[list[dict[str, Any]]]:
            yield [{'hash': '0x1'}, {'hash': '0x2'}]
            yield [{'hash': '0x3'}, {'hash': '0x4'}]

        client.iter_transactions_streaming = fake_stream  # type: ignore[assignment]

        with caplog.at_level('WARNING'):
            result = await client.get_all_transactions('0xABC')

        assert len(result) == 4
        assert 'Aggregating >100k transactions in memory' in caplog.text

    @pytest.mark.asyncio
    async def test_get_all_token_transfers(self, client: ChainscanClient) -> None:
        async def fake_stream(*args: Any, **kwargs: Any) -> AsyncIterator[list[dict[str, Any]]]:
            yield [{'hash': '0xT1'}]

        client.iter_token_transfers_streaming = fake_stream  # type: ignore[assignment]

        result = await client.get_all_token_transfers('0xABC')
        assert len(result) == 1
        assert result[0]['hash'] == '0xT1'

    @pytest.mark.asyncio
    async def test_get_all_internal_transactions(self, client: ChainscanClient) -> None:
        async def fake_stream(*args: Any, **kwargs: Any) -> AsyncIterator[list[dict[str, Any]]]:
            yield [{'hash': '0xI1'}, {'hash': '0xI2'}]

        client.iter_internal_transactions_streaming = fake_stream  # type: ignore[assignment]

        result = await client.get_all_internal_transactions('0xABC')
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_all_logs(self, client: ChainscanClient) -> None:
        async def fake_stream(*args: Any, **kwargs: Any) -> AsyncIterator[list[dict[str, Any]]]:
            yield [{'logIndex': '0'}, {'logIndex': '1'}]
            yield [{'logIndex': '2'}]

        client.iter_logs_streaming = fake_stream  # type: ignore[assignment]

        result = await client.get_all_logs('0xC')
        assert len(result) == 3


# ---------------------------------------------------------------------------
# get_transactions_df: must use paginated fetch, not single-page
# ---------------------------------------------------------------------------


class TestTransactionsDfPagination:
    """Verify that get_transactions_df uses full pagination (not single-page call)."""

    @pytest.mark.asyncio
    async def test_get_transactions_df_uses_iter_transactions(
        self, client: ChainscanClient
    ) -> None:
        """get_transactions_df must iterate ALL transactions, not just one page."""
        collected_from_iter = False

        async def fake_iter(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            nonlocal collected_from_iter
            collected_from_iter = True
            yield {
                'hash': '0x1',
                'blockNumber': '1',
                'from': '0xA',
                'to': '0xB',
                'value': '1000000000000000000',
                'gasUsed': '21000',
                'timeStamp': '1609459200',
            }

        client.iter_transactions = fake_iter  # type: ignore[assignment]

        try:
            import polars  # noqa: F401

            df = await client.get_transactions_df('0xABC')
            assert collected_from_iter, 'Should use iter_transactions, not single-page call'
            assert len(df) == 1
        except ImportError:
            pytest.skip('Polars not installed')


class TestStreamingDecodeAndTopicOperators:
    """Regression tests for decoded iteration paths."""

    @pytest.mark.asyncio
    async def test_iter_transactions_applies_abi_decode(
        self, client: ChainscanClient, monkeypatch
    ) -> None:
        # Pagination flows through the scanner port (fetch_page seam).
        fetch_page = AsyncMock()
        fetch_page.side_effect = [
            (
                [
                    {
                        'hash': '0x1',
                        'input': '0xabc',
                    }
                ],
                None,
            )
        ]
        client._scanner.fetch_page = fetch_page  # type: ignore[assignment]

        def fake_decode(tx: dict[str, Any], abi: list[dict[str, Any]]) -> dict[str, Any]:
            tx['decoded_func'] = 'transfer'
            tx['decoded_data'] = {'to': '0x2', 'value': '1'}
            return tx

        monkeypatch.setattr('aiochainscan.decode.decode_transaction_input', fake_decode)

        out: list[dict[str, Any]] = []
        async for tx in client.iter_transactions(TEST_ADDRESS, abi=[{'type': 'function'}]):
            out.append(tx)

        assert len(out) == 1
        assert out[0]['decoded_func'] == 'transfer'
        assert out[0]['decoded_data']['value'] == '1'

    @pytest.mark.asyncio
    async def test_iter_logs_preserves_topic_operators_and_decodes(
        self, client: ChainscanClient, monkeypatch
    ) -> None:
        # Pagination flows through the scanner port (fetch_page seam).
        fetch_page = AsyncMock()
        fetch_page.side_effect = [
            (
                [
                    {
                        'address': TEST_CONTRACT,
                        'topics': ['0xabc'],
                        'data': '0x',
                    }
                ],
                {'page': 2, 'offset': 1},
            ),
            ([], None),
        ]
        client._scanner.fetch_page = fetch_page  # type: ignore[assignment]

        def fake_decode(log: dict[str, Any], abi: list[dict[str, Any]]) -> dict[str, Any]:
            log['decoded_event'] = 'Transfer'
            log['decoded_data'] = {'from': TEST_ADDRESS}
            return log

        monkeypatch.setattr('aiochainscan.decode.decode_log_data', fake_decode)

        out: list[dict[str, Any]] = []
        async for log in client.iter_logs(
            TEST_CONTRACT,
            abi=[{'type': 'event'}],
            topics=['0xtopic0', '0xtopic1'],
            topic_operators=['and'],
            batch_size=1,
        ):
            out.append(log)

        assert len(out) == 1
        assert out[0]['decoded_event'] == 'Transfer'
        assert fetch_page.await_count == 2
        first_call_params = fetch_page.await_args_list[0].args[1]
        assert first_call_params['topic0'] == '0xtopic0'
        assert first_call_params['topic1'] == '0xtopic1'
        assert first_call_params['topic0_1_opr'] == 'and'
        # Cursor merges into the second page's params
        assert fetch_page.await_args_list[1].args[1]['page'] == 2


class TestBatchSizeValidation:
    @pytest.mark.parametrize(
        'method_name',
        [
            'iter_transactions',
            'iter_transactions_streaming',
            'iter_internal_transactions_streaming',
            'iter_token_transfers_streaming',
            'iter_logs_streaming',
            'iter_logs',
        ],
    )
    @pytest.mark.asyncio
    async def test_non_positive_batch_size_fails_before_fetch(
        self, client: ChainscanClient, method_name: str
    ) -> None:
        method = getattr(client, method_name)
        with pytest.raises(ValueError, match='batch_size must be at least 1'):
            async for _ in method(TEST_CONTRACT, batch_size=0):
                pass


# ---------------------------------------------------------------------------
# Method coverage: every Method enum value should have a convenience path
# ---------------------------------------------------------------------------


class TestMethodCoverage:
    """Ensure every Method enum value has a convenience method or documented reason."""

    # Methods that have no single-method convenience wrapper because they
    # require special workflows (e.g., multi-step verify, or covered by
    # higher-level get_contract()).
    EXCLUDED = {
        Method.CONTRACT_VERIFY,  # Multi-step: submit source + poll status
        Method.CONTRACT_VERIFY_STATUS,  # Used only as part of verify workflow
    }

    def test_all_methods_have_convenience(self, client: ChainscanClient) -> None:
        """Every Method should be reachable via a typed convenience method."""
        # Map: Method -> convenience method name(s)
        method_map: dict[Method, list[str]] = {
            Method.ACCOUNT_BALANCE: ['get_balance'],
            Method.ACCOUNT_TRANSACTIONS: ['get_transactions', 'get_all_transactions'],
            Method.ACCOUNT_INTERNAL_TXS: [
                'get_internal_transactions',
                'get_all_internal_transactions',
            ],
            Method.ACCOUNT_ERC20_TRANSFERS: ['get_token_transfers', 'get_all_token_transfers'],
            Method.ACCOUNT_ERC721_TRANSFERS: ['get_erc721_transfers'],
            Method.ACCOUNT_ERC1155_TRANSFERS: ['get_erc1155_transfers'],
            Method.ACCOUNT_TOKEN_PORTFOLIO: ['get_token_portfolio'],
            Method.ACCOUNT_NFT_PORTFOLIO: ['get_nft_portfolio'],
            Method.TX_BY_HASH: ['get_transaction'],
            Method.TX_RECEIPT_STATUS: ['get_transaction_status'],
            Method.TX_STATUS_CHECK: ['check_transaction_status'],
            Method.BLOCK_BY_NUMBER: ['get_block'],
            Method.BLOCK_REWARD: ['get_block_reward'],
            Method.BLOCK_COUNTDOWN: ['get_block_countdown'],
            Method.BLOCK_NUMBER_BY_TIMESTAMP: ['get_block_by_timestamp'],
            Method.CONTRACT_ABI: ['get_contract_abi'],
            Method.CONTRACT_SOURCE: ['get_contract_source'],
            Method.CONTRACT_CREATION: ['get_contract_creation'],
            Method.TOKEN_BALANCE: ['get_token_balance'],
            Method.TOKEN_SUPPLY: ['get_token_supply'],
            Method.TOKEN_INFO: ['get_token_info'],
            Method.GAS_ESTIMATE: ['get_gas_estimate'],
            Method.GAS_ORACLE: ['get_gas_oracle'],
            Method.EVENT_LOGS: ['get_logs', 'get_all_logs'],
            Method.ETH_SUPPLY: ['get_eth_supply'],
            Method.ETH_PRICE: ['get_eth_price'],
            Method.PROXY_ETH_CALL: ['eth_call'],
            Method.PROXY_GET_BALANCE: ['eth_get_balance'],
        }

        for method in Method:
            if method in self.EXCLUDED:
                continue
            assert method in method_map, f'{method.name} has no convenience method mapping'
            for method_name in method_map[method]:
                assert hasattr(
                    client, method_name
                ), f'ChainscanClient missing method {method_name} for {method.name}'
                assert callable(
                    getattr(client, method_name)
                ), f'{method_name} on ChainscanClient is not callable'
