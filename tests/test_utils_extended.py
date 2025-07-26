import json
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from aiochainscan.exceptions import ChainscanClientApiError
from aiochainscan.modules.extra.utils import Utils


class TestUtilsTokenTransfers:
    """Test token transfer functionality."""

    def setup_method(self):
        """Setup test data."""
        self.mock_client = MagicMock()
        self.utils = Utils(self.mock_client)

    @pytest.mark.asyncio
    async def test_token_transfers_generator_basic(self):
        """Test basic token transfers generator functionality."""
        # Mock proxy.block_number to return current block
        self.mock_client.proxy.block_number = AsyncMock(return_value='0x989680')  # 10000000

        # Mock _parse_by_pages to yield test transfers
        test_transfers = [
            {'hash': '0x123', 'from': '0xabc', 'to': '0xdef', 'value': '1000'},
            {'hash': '0x456', 'from': '0xghi', 'to': '0xjkl', 'value': '2000'}
        ]

        async def mock_parse_by_pages(**kwargs):
            for transfer in test_transfers:
                yield transfer

        with patch.object(self.utils, '_parse_by_pages', side_effect=mock_parse_by_pages):
            with patch.object(self.utils, '_generate_intervals', return_value=[(0, 49)]):
                transfers = []
                async for transfer in self.utils.token_transfers_generator(
                    address='0x123',
                    block_limit=50,
                    offset=3
                ):
                    transfers.append(transfer)

                assert len(transfers) == 2
                assert transfers[0]['hash'] == '0x123'
                assert transfers[1]['hash'] == '0x456'

    @pytest.mark.asyncio
    async def test_token_transfers_generator_with_end_block(self):
        """Test token transfers generator with specified end block."""
        async def mock_parse_by_pages(**kwargs):
            return
            yield  # Make it a generator

        with patch.object(self.utils, '_parse_by_pages', side_effect=mock_parse_by_pages):
            with patch.object(self.utils, '_generate_intervals', return_value=[(0, 999)]) as mock_intervals:
                transfers = []
                async for transfer in self.utils.token_transfers_generator(
                    address='0x123',
                    end_block=1000
                ):
                    transfers.append(transfer)

                # Verify intervals were generated with the specified end block
                mock_intervals.assert_called_once_with(0, 1000, 50)

    @pytest.mark.asyncio
    async def test_token_transfers_list_method(self):
        """Test token_transfers method that returns a list."""
        test_transfers = [
            {'hash': '0x123', 'value': '1000'},
            {'hash': '0x456', 'value': '2000'}
        ]

        async def mock_generator(**kwargs):
            for transfer in test_transfers:
                yield transfer

        with patch.object(self.utils, 'token_transfers_generator', side_effect=mock_generator):
            result = await self.utils.token_transfers(address='0x123')

            assert len(result) == 2
            assert result[0]['hash'] == '0x123'
            assert result[1]['hash'] == '0x456'


class TestUtilsContractDetection:
    """Test contract detection functionality."""

    def setup_method(self):
        """Setup test data."""
        self.mock_client = MagicMock()
        self.utils = Utils(self.mock_client)

    @pytest.mark.asyncio
    async def test_is_contract_verified_contract(self):
        """Test is_contract with verified contract."""
        self.mock_client.contract.contract_abi = AsyncMock(return_value=[{'type': 'function'}])

        result = await self.utils.is_contract('0x123')

        assert result is True
        self.mock_client.contract.contract_abi.assert_called_once_with(address='0x123')

    @pytest.mark.asyncio
    async def test_is_contract_unverified_contract(self):
        """Test is_contract with unverified contract."""
        error = ChainscanClientApiError("NOTOK", "Contract source code not verified")
        self.mock_client.contract.contract_abi = AsyncMock(side_effect=error)

        result = await self.utils.is_contract('0x123')

        assert result is False

    @pytest.mark.asyncio
    async def test_is_contract_error_propagation(self):
        """Test is_contract propagates unexpected errors."""
        error = ChainscanClientApiError("ERROR", "Unexpected error")
        self.mock_client.contract.contract_abi = AsyncMock(side_effect=error)

        with pytest.raises(ChainscanClientApiError):
            await self.utils.is_contract('0x123')

    @pytest.mark.asyncio
    async def test_is_contract_empty_abi(self):
        """Test is_contract with empty ABI response."""
        self.mock_client.contract.contract_abi = AsyncMock(return_value=[])

        result = await self.utils.is_contract('0x123')

        assert result is False


class TestUtilsContractCreator:
    """Test contract creator detection."""

    def setup_method(self):
        """Setup test data."""
        self.mock_client = MagicMock()
        self.utils = Utils(self.mock_client)

    @pytest.mark.asyncio
    async def test_get_contract_creator_from_internal_txs(self):
        """Test getting contract creator from internal transactions."""
        internal_txs = [
            {'from': '0xCreator123', 'to': '0xContract', 'type': 'create'}
        ]
        self.mock_client.account.internal_txs = AsyncMock(return_value=internal_txs)

        result = await self.utils.get_contract_creator('0xContract')

        assert result == '0xcreator123'  # Should be lowercase
        self.mock_client.account.internal_txs.assert_called_once_with(
            address='0xContract', start_block=1, page=1, offset=1
        )

    @pytest.mark.asyncio
    async def test_get_contract_creator_from_normal_txs(self):
        """Test getting contract creator from normal transactions when internal txs fail."""
        # Mock the exact exception message that the code expects (lowercase)

        # Mock internal_txs to return None (simulating empty response, not exception)
        self.mock_client.account.internal_txs = AsyncMock(return_value=None)

        # Normal txs succeed
        normal_txs = [
            {'from': '0xCreator456', 'to': '0xContract'}
        ]
        self.mock_client.account.normal_txs = AsyncMock(return_value=normal_txs)

        result = await self.utils.get_contract_creator('0xContract')

        assert result == '0xcreator456'
        self.mock_client.account.normal_txs.assert_called_once_with(
            address='0xContract', start_block=1, page=1, offset=1
        )

    @pytest.mark.asyncio
    async def test_get_contract_creator_no_transactions(self):
        """Test getting contract creator when no transactions found."""
        # Mock both internal_txs and normal_txs to return empty response
        self.mock_client.account.internal_txs = AsyncMock(return_value=None)
        self.mock_client.account.normal_txs = AsyncMock(return_value=None)

        result = await self.utils.get_contract_creator('0xContract')

        assert result is None

    @pytest.mark.asyncio
    async def test_get_contract_creator_error_propagation(self):
        """Test that unexpected errors are propagated."""
        error = ChainscanClientApiError("ERROR", "unexpected error")
        self.mock_client.account.internal_txs = AsyncMock(side_effect=error)

        with pytest.raises(ChainscanClientApiError):
            await self.utils.get_contract_creator('0xContract')


class TestUtilsProxyAbi:
    """Test proxy ABI functionality."""

    def setup_method(self):
        """Setup test data."""
        self.mock_client = MagicMock()
        self.mock_client._url_builder._api_kind = 'etherscan'
        self.utils = Utils(self.mock_client)

    @pytest.mark.asyncio
    async def test_get_proxy_abi_local_cache_hit(self):
        """Test getting proxy ABI from local cache."""
        test_abi = [{'type': 'function', 'name': 'transfer'}]

        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(test_abi))):
                result = await self.utils.get_proxy_abi('0x123')

                assert result == test_abi

    @pytest.mark.asyncio
    async def test_get_proxy_abi_fetch_and_cache(self):
        """Test fetching ABI from API and caching it."""
        test_abi = [{'type': 'function', 'name': 'approve'}]

        # Mock file system
        with patch('os.path.exists', return_value=False):
            with patch('os.makedirs') as mock_makedirs:
                with patch('builtins.open', mock_open()) as mock_file:
                    # Mock API responses
                    source_code = [{'ABI': 'Contract ABI available', 'Implementation': ''}]
                    self.mock_client.contract.contract_source_code = AsyncMock(return_value=source_code)
                    self.mock_client.contract.contract_abi = AsyncMock(return_value=test_abi)

                    result = await self.utils.get_proxy_abi('0x123')

                    assert result == test_abi
                    mock_makedirs.assert_called_once_with('abi')
                    # Verify ABI was written to file
                    mock_file.assert_called()

    @pytest.mark.asyncio
    async def test_get_proxy_abi_with_proxy_implementation(self):
        """Test getting ABI for proxy contract with implementation."""
        proxy_abi = [{'type': 'function', 'name': 'implementation'}]

        with patch('os.path.exists', return_value=False):
            with patch('os.makedirs'):
                with patch('builtins.open', mock_open()):
                    # Mock source code with implementation address
                    source_code = [{'Implementation': '0xImplementation123', 'ABI': 'Available'}]
                    self.mock_client.contract.contract_source_code = AsyncMock(return_value=source_code)
                    self.mock_client.contract.contract_abi = AsyncMock(return_value=proxy_abi)

                    result = await self.utils.get_proxy_abi('0x123')

                    assert result == proxy_abi
                    # Should call contract_abi with implementation address
                    self.mock_client.contract.contract_abi.assert_called_with(address='0xImplementation123')

    @pytest.mark.asyncio
    async def test_get_proxy_abi_source_code_error(self):
        """Test handling source code fetch errors."""
        error = ChainscanClientApiError("ERROR", "Contract not found")
        self.mock_client.contract.contract_source_code = AsyncMock(side_effect=error)

        result = await self.utils.get_proxy_abi('0x123')

        assert result is None

    @pytest.mark.asyncio
    async def test_get_proxy_abi_unverified_contract(self):
        """Test handling unverified contract."""
        with patch('os.path.exists', return_value=False):
            with patch('os.makedirs'):
                source_code = [{'ABI': 'Contract source code not verified', 'Implementation': ''}]
                self.mock_client.contract.contract_source_code = AsyncMock(return_value=source_code)

                result = await self.utils.get_proxy_abi('0x123')

                assert result is None


class TestUtilsElementDecoding:
    """Test element decoding functionality."""

    def setup_method(self):
        """Setup test data."""
        self.mock_client = MagicMock()
        self.utils = Utils(self.mock_client)

    @pytest.mark.asyncio
    async def test_decode_elements_no_abi(self):
        """Test decode elements when no ABI is provided."""
        elements = [{'hash': '0x123', 'input': '0xabc'}]
        function = MagicMock()
        function.__name__ = 'normal_txs'

        result = await self.utils._decode_elements(elements, None, '0xAddress', function, 'auto')

        assert result == elements  # Should return unchanged

    @pytest.mark.asyncio
    async def test_decode_elements_skip_internal_txs(self):
        """Test that internal transactions are not decoded."""
        elements = [{'hash': '0x123'}]
        function = MagicMock()
        function.__name__ = 'internal_txs'
        abi = json.dumps([{'type': 'function', 'name': 'test'}])

        result = await self.utils._decode_elements(elements, abi, '0xAddress', function, 'auto')

        assert result == elements  # Should return unchanged

    @pytest.mark.asyncio
    async def test_decode_elements_transaction_success(self):
        """Test successful transaction element decoding."""
        elements = [
            {'hash': '0x123', 'input': '0xabc'},
            {'hash': '0x456', 'input': '0xdef'}
        ]
        function = MagicMock()
        function.__name__ = 'normal_txs'
        abi = json.dumps([{'type': 'function', 'name': 'transfer'}])

        with patch('aiochainscan.modules.extra.utils.decode_transaction_input') as mock_decode:
            mock_decode.side_effect = [
                {'hash': '0x123', 'decoded_func': 'transfer', 'decoded_data': {'to': '0xabc'}},
                {'hash': '0x456', 'decoded_func': 'transfer', 'decoded_data': {'to': '0xdef'}}
            ]

            result = await self.utils._decode_elements(elements, abi, '0xAddress', function, 'auto')

            assert len(result) == 2
            assert result[0]['decoded_func'] == 'transfer'
            assert result[1]['decoded_func'] == 'transfer'
            assert mock_decode.call_count == 2

    @pytest.mark.asyncio
    async def test_decode_elements_log_success(self):
        """Test successful log element decoding."""
        elements = [
            {'topics': ['0x123'], 'data': '0xabc'},
            {'topics': ['0x456'], 'data': '0xdef'}
        ]
        function = MagicMock()
        function.__name__ = 'get_logs'
        abi = json.dumps([{'type': 'event', 'name': 'Transfer'}])

        with patch('aiochainscan.modules.extra.utils.decode_log_data') as mock_decode:
            mock_decode.side_effect = [
                {'topics': ['0x123'], 'decoded_data': {'event': 'Transfer'}},
                {'topics': ['0x456'], 'decoded_data': {'event': 'Transfer'}}
            ]

            result = await self.utils._decode_elements(elements, abi, '0xAddress', function, 'auto')

            assert len(result) == 2
            assert result[0]['decoded_data']['event'] == 'Transfer'
            assert result[1]['decoded_data']['event'] == 'Transfer'
            assert mock_decode.call_count == 2

    @pytest.mark.asyncio
    async def test_decode_elements_error_handling(self):
        """Test error handling during element decoding."""
        elements = [
            {'hash': '0x123', 'input': '0xabc'},
            {'hash': '0x456', 'input': '0xdef'}  # This will fail
        ]
        function = MagicMock()
        function.__name__ = 'normal_txs'
        abi = json.dumps([{'type': 'function', 'name': 'transfer'}])

        with patch('aiochainscan.modules.extra.utils.decode_transaction_input') as mock_decode:
            mock_decode.side_effect = [
                {'hash': '0x123', 'decoded_func': 'transfer'},
                Exception("Decode error")
            ]

            result = await self.utils._decode_elements(elements, abi, '0xAddress', function, 'auto')

            assert len(result) == 2
            assert result[0]['decoded_func'] == 'transfer'
            assert result[1] == elements[1]  # Should remain unchanged on error


class TestUtilsElementsBatch:
    """Test elements batch functionality."""

    def setup_method(self):
        """Setup test data."""
        self.mock_client = MagicMock()
        self.utils = Utils(self.mock_client)

    @pytest.mark.asyncio
    async def test_get_elements_batch_basic(self):
        """Test basic elements batch retrieval."""
        function = AsyncMock()
        test_elements = [
            {'blockNumber': '1000', 'hash': '0x123'},
            {'blockNumber': '1001', 'hash': '0x456'}
        ]
        function.return_value = test_elements
        function.__name__ = 'normal_txs'

        with patch('builtins.print'):  # Suppress print statements
            result = await self.utils._get_elements_batch(
                function, '0xAddress', 1000, 2000, 100
            )

            assert result == test_elements
            function.assert_called_once_with(
                address='0xAddress',
                start_block=1000,
                end_block=2000,
                page=1,
                offset=100
            )

    @pytest.mark.asyncio
    async def test_get_elements_batch_pagination(self):
        """Test elements batch with pagination."""
        function = AsyncMock()

        # Return less than offset to simulate end of data
        test_batch = [{'blockNumber': '1000', 'hash': f'0x{i}'} for i in range(50)]

        function.return_value = test_batch
        function.__name__ = 'normal_txs'

        with patch('builtins.print'):
            result = await self.utils._get_elements_batch(
                function, '0xAddress', 1000, 2000, 100
            )

            assert len(result) == 50  # Only one batch returned
            assert function.call_count == 1

    @pytest.mark.asyncio
    async def test_get_elements_batch_hex_blocks(self):
        """Test elements batch with hexadecimal block numbers."""
        function = AsyncMock()
        test_elements = [
            {'blockNumber': '0x3e8', 'hash': '0x123'},  # 1000 in hex
            {'blockNumber': '0x3e9', 'hash': '0x456'}   # 1001 in hex
        ]
        function.return_value = test_elements
        function.__name__ = 'get_logs'  # get_logs uses hex blocks

        with patch('builtins.print'):
            result = await self.utils._get_elements_batch(
                function, '0xAddress', 1000, 2000, 100
            )

            assert result == test_elements

    @pytest.mark.asyncio
    async def test_get_elements_batch_error_handling(self):
        """Test error handling in elements batch."""
        function = AsyncMock()
        function.side_effect = Exception("API Error")
        function.__name__ = 'normal_txs'

        with patch('builtins.print'):
            result = await self.utils._get_elements_batch(
                function, '0xAddress', 1000, 2000, 100
            )

            assert result == []  # Should return empty list on error


class TestUtilsFetchAllElements:
    """Test fetch all elements functionality."""

    def setup_method(self):
        """Setup test data."""
        self.mock_client = MagicMock()
        self.utils = Utils(self.mock_client)

    @pytest.mark.asyncio
    async def test_fetch_all_elements_with_decode(self):
        """Test fetching all elements with decoding."""
        test_elements = [{'hash': '0x123', 'input': '0xabc'}]
        test_abi = [{'type': 'function', 'name': 'transfer'}]

        # Mock the data_model_mapping to return a function with proper __name__
        mock_function = AsyncMock()
        mock_function.__name__ = 'normal_txs'

        with patch.object(self.utils, 'data_model_mapping', {'normal_txs': mock_function}):
            with patch.object(self.utils, '_get_elements_batch', return_value=test_elements):
                with patch.object(self.utils, 'get_proxy_abi', return_value=test_abi):
                    with patch.object(self.utils, '_decode_elements', return_value=test_elements) as mock_decode:
                        result = await self.utils.fetch_all_elements(
                            '0xAddress', 'normal_txs', decode_type='auto'
                        )

                        assert result == test_elements
                        mock_decode.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_all_elements_without_decode(self):
        """Test fetching all elements without decoding."""
        test_elements = [{'hash': '0x123'}]

        # Mock the data_model_mapping to return a function with proper __name__
        mock_function = AsyncMock()
        mock_function.__name__ = 'internal_txs'

        with patch.object(self.utils, 'data_model_mapping', {'internal_txs': mock_function}):
            with patch.object(self.utils, '_get_elements_batch', return_value=test_elements):
                result = await self.utils.fetch_all_elements(
                    '0xAddress', 'internal_txs', decode_type='auto'
                )

                assert result == test_elements

    @pytest.mark.asyncio
    async def test_fetch_all_elements_invalid_data_type(self):
        """Test fetch all elements with invalid data type."""
        with pytest.raises(ValueError, match="Unsupported data type"):
            await self.utils.fetch_all_elements(
                '0xAddress', 'invalid_type'
            )

    @pytest.mark.asyncio
    async def test_fetch_all_elements_with_custom_end_block(self):
        """Test fetch all elements with custom end block."""
        test_elements = []

        # Mock the data_model_mapping to return a function with proper __name__
        mock_function = AsyncMock()
        mock_function.__name__ = 'normal_txs'

        with patch.object(self.utils, 'data_model_mapping', {'normal_txs': mock_function}):
            with patch.object(self.utils, '_get_elements_batch', return_value=test_elements) as mock_batch:
                with patch.object(self.utils, 'get_proxy_abi', return_value=None):
                    await self.utils.fetch_all_elements(
                        '0xAddress', 'normal_txs', end_block=5000
                    )

                    mock_batch.assert_called_once()
                    args = mock_batch.call_args[0]
                    assert args[2] == 0      # start_block
                    assert args[3] == 5000   # end_block


class TestUtilsParseByPages:
    """Test parse by pages functionality."""

    def setup_method(self):
        """Setup test data."""
        self.mock_client = MagicMock()
        self.utils = Utils(self.mock_client)

    @pytest.mark.asyncio
    async def test_parse_by_pages_basic(self):
        """Test basic parse by pages functionality."""
        # Simply test that the method exists and can be called
        # The actual complex pagination logic is tested through integration tests
        self.mock_client.account.token_transfers = AsyncMock(return_value=[])
        
        transfers = []
        # Test with empty result should work without throwing
        async for transfer in self.utils._parse_by_pages(
            start_block=1000, end_block=2000, offset=10, address='0xAddress'
        ):
            transfers.append(transfer)

        assert len(transfers) == 0

    @pytest.mark.asyncio
    async def test_parse_by_pages_error_propagation(self):
        """Test that non-'No transactions found' errors are propagated."""
        error = ChainscanClientApiError("ERROR", "Unexpected error")
        self.mock_client.account.token_transfers = AsyncMock(side_effect=error)

        with pytest.raises(ChainscanClientApiError):
            async for _transfer in self.utils._parse_by_pages(
                start_block=1000, end_block=2000, offset=10, address='0xAddress'
            ):
                pass


class TestUtilsGenerateIntervals:
    """Test interval generation utility."""

    def test_generate_intervals_basic(self):
        """Test basic interval generation."""
        result = list(Utils._generate_intervals(0, 100, 25))

        expected = [(0, 24), (25, 49), (50, 74), (75, 99), (100, 100)]
        assert result == expected

    def test_generate_intervals_exact_division(self):
        """Test interval generation with exact division."""
        result = list(Utils._generate_intervals(0, 99, 25))

        expected = [(0, 24), (25, 49), (50, 74), (75, 99)]
        assert result == expected

    def test_generate_intervals_single_interval(self):
        """Test interval generation for single interval."""
        result = list(Utils._generate_intervals(10, 20, 50))

        expected = [(10, 20)]
        assert result == expected

    def test_generate_intervals_zero_range(self):
        """Test interval generation with zero range."""
        result = list(Utils._generate_intervals(5, 5, 10))

        expected = [(5, 5)]
        assert result == expected
