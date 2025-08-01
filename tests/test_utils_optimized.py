"""Tests for optimized transaction fetching functionality."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.modules.extra.utils import Utils


class TestOptimizedTransactionFetching:
    """Test cases for the optimized transaction fetching method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client for testing."""
        client = MagicMock()
        client.proxy = MagicMock()
        client.proxy.block_number = AsyncMock(return_value="0x1000")  # Block 4096
        return client

    @pytest.fixture
    def utils(self, mock_client):
        """Create Utils instance with mock client."""
        utils = Utils(mock_client)
        utils.data_model_mapping = {
            "normal_txs": AsyncMock(),
            "internal_txs": AsyncMock(),
            "token_transfers": AsyncMock(),
        }
        utils.get_proxy_abi = AsyncMock(return_value=None)
        utils._decode_elements = AsyncMock(side_effect=lambda x, *args: x)
        return utils

    @pytest.mark.asyncio
    async def test_fetch_all_elements_optimized_basic(self, utils):
        """Test basic functionality of optimized fetching."""
        # Mock function returns
        mock_function = utils.data_model_mapping["normal_txs"]
        mock_function.return_value = [
            {"hash": "tx1", "blockNumber": "100", "transactionIndex": "0"},
            {"hash": "tx2", "blockNumber": "101", "transactionIndex": "1"},
        ]

        result = await utils.fetch_all_elements_optimized(
            address="0x123",
            data_type="normal_txs",
            start_block=100,
            end_block=200,
            max_concurrent=1,
            max_offset=10,
        )

        assert len(result) == 2
        assert result[0]["hash"] == "tx1"
        assert result[1]["hash"] == "tx2"

        # Verify function was called
        mock_function.assert_called()

    @pytest.mark.asyncio
    async def test_fetch_all_elements_optimized_splitting(self, utils):
        """Test range splitting when max results are returned."""
        mock_function = utils.data_model_mapping["normal_txs"]

        # First call returns max results (triggers split)
        # Second and third calls return fewer results (range complete)
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Return max results to trigger split
                return [
                    {
                        "hash": f"tx{i}",
                        "blockNumber": str(100 + i),
                        "transactionIndex": str(i),
                    }
                    for i in range(10)
                ]  # max_offset=10
            else:
                # Return fewer results for subsequent calls
                return [
                    {
                        "hash": f"tx{call_count}0",
                        "blockNumber": str(100 + call_count),
                        "transactionIndex": "0",
                    }
                ]

        mock_function.side_effect = side_effect

        result = await utils.fetch_all_elements_optimized(
            address="0x123",
            data_type="normal_txs",
            start_block=100,
            end_block=200,
            max_concurrent=1,
            max_offset=10,
        )

        # Should have called the function multiple times due to range splitting
        assert mock_function.call_count > 1

        # Should have results from multiple calls (first call + split calls)
        assert len(result) >= 4  # At least some results from multiple calls

    @pytest.mark.asyncio
    async def test_fetch_all_elements_optimized_deduplication(self, utils):
        """Test that duplicate transactions are removed."""
        mock_function = utils.data_model_mapping["normal_txs"]

        # Return same transaction multiple times
        mock_function.return_value = [
            {"hash": "tx1", "blockNumber": "100", "transactionIndex": "0"},
            {"hash": "tx1", "blockNumber": "100", "transactionIndex": "0"},  # Duplicate
            {"hash": "tx2", "blockNumber": "101", "transactionIndex": "1"},
        ]

        result = await utils.fetch_all_elements_optimized(
            address="0x123",
            data_type="normal_txs",
            start_block=100,
            end_block=200,
            max_concurrent=1,
            max_offset=10,
        )

        # Should have only 2 unique transactions
        assert len(result) == 2
        hashes = [tx["hash"] for tx in result]
        assert "tx1" in hashes
        assert "tx2" in hashes
        assert len(set(hashes)) == 2  # All unique

    @pytest.mark.asyncio
    async def test_fetch_all_elements_optimized_sorting(self, utils):
        """Test that results are sorted by block number and transaction index."""
        mock_function = utils.data_model_mapping["normal_txs"]

        # Return unsorted transactions
        mock_function.return_value = [
            {"hash": "tx3", "blockNumber": "102", "transactionIndex": "0"},
            {"hash": "tx1", "blockNumber": "100", "transactionIndex": "1"},
            {"hash": "tx2", "blockNumber": "100", "transactionIndex": "0"},
            {"hash": "tx4", "blockNumber": "101", "transactionIndex": "0"},
        ]

        result = await utils.fetch_all_elements_optimized(
            address="0x123",
            data_type="normal_txs",
            start_block=100,
            end_block=200,
            max_concurrent=1,
            max_offset=10,
        )

        # Should be sorted by block number, then by transaction index
        expected_order = [
            "tx2",
            "tx1",
            "tx4",
            "tx3",
        ]  # Block 100(idx 0,1), 101(idx 0), 102(idx 0)
        actual_order = [tx["hash"] for tx in result]
        assert actual_order == expected_order

    @pytest.mark.asyncio
    async def test_fetch_all_elements_optimized_empty_range(self, utils):
        """Test handling of empty block ranges."""
        result = await utils.fetch_all_elements_optimized(
            address="0x123",
            data_type="normal_txs",
            start_block=200,
            end_block=100,  # Invalid range: end < start
            max_concurrent=1,
            max_offset=10,
        )

        # Should return empty list for invalid range
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_all_elements_optimized_error_handling(self, utils):
        """Test error handling in optimized fetching."""
        mock_function = utils.data_model_mapping["normal_txs"]

        # Mock function raises exception
        mock_function.side_effect = Exception("API Error")

        result = await utils.fetch_all_elements_optimized(
            address="0x123",
            data_type="normal_txs",
            start_block=100,
            end_block=200,
            max_concurrent=1,
            max_offset=10,
        )

        # Should return empty list on error
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_all_elements_optimized_unsupported_data_type(self, utils):
        """Test handling of unsupported data types."""
        with pytest.raises(ValueError, match="Unsupported data type"):
            await utils.fetch_all_elements_optimized(
                address="0x123",
                data_type="unsupported_type",
                start_block=100,
                end_block=200,
                max_concurrent=1,
                max_offset=10,
            )

    @pytest.mark.asyncio
    async def test_fetch_all_elements_optimized_concurrent_processing(self, utils):
        """Test concurrent processing with multiple workers."""
        mock_function = utils.data_model_mapping["normal_txs"]

        # Mock function with delay to test concurrency
        async def delayed_return(*args, **kwargs):
            await asyncio.sleep(0.01)  # Small delay
            return [{"hash": "tx1", "blockNumber": "100", "transactionIndex": "0"}]

        mock_function.side_effect = delayed_return

        start_time = asyncio.get_event_loop().time()
        result = await utils.fetch_all_elements_optimized(
            address="0x123",
            data_type="normal_txs",
            start_block=100,
            end_block=200,
            max_concurrent=3,  # Multiple concurrent workers
            max_offset=1,  # Force many small requests
        )
        end_time = asyncio.get_event_loop().time()

        # Should complete in reasonable time with concurrency
        execution_time = end_time - start_time
        assert execution_time < 1.0  # Should be much faster than sequential
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_fetch_all_elements_optimized_hex_block_numbers(self, utils):
        """Test handling of hexadecimal block numbers."""
        mock_function = utils.data_model_mapping["normal_txs"]

        # Return transactions with hex block numbers
        mock_function.return_value = [
            {
                "hash": "tx1",
                "blockNumber": "0x64",
                "transactionIndex": "0x0",
            },  # Block 100, index 0
            {
                "hash": "tx2",
                "blockNumber": "0x65",
                "transactionIndex": "0x1",
            },  # Block 101, index 1
        ]

        result = await utils.fetch_all_elements_optimized(
            address="0x123",
            data_type="normal_txs",
            start_block=100,
            end_block=200,
            max_concurrent=1,
            max_offset=10,
        )

        # Should handle hex numbers correctly and sort properly
        assert len(result) == 2
        assert result[0]["hash"] == "tx1"  # Lower block number first
        assert result[1]["hash"] == "tx2"

    def test_generate_intervals_method_exists(self, utils):
        """Test that the _generate_intervals static method still works."""
        intervals = list(utils._generate_intervals(0, 100, 30))
        expected = [(0, 29), (30, 59), (60, 89), (90, 100)]
        assert intervals == expected
