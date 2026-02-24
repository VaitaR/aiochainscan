"""
Tests for SmartContract abstraction.

Tests proxy resolution, event iteration, transaction iteration,
and error handling.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method
from aiochainscan.domain.contract import DecodedEvent, DecodedTransaction, SmartContract

# Sample ERC20 ABI (minimal for testing)
SAMPLE_ERC20_ABI = [
    {
        'type': 'function',
        'name': 'transfer',
        'inputs': [
            {'name': 'to', 'type': 'address'},
            {'name': 'value', 'type': 'uint256'},
        ],
        'outputs': [{'name': '', 'type': 'bool'}],
        'stateMutability': 'nonpayable',
    },
    {
        'type': 'function',
        'name': 'balanceOf',
        'inputs': [{'name': 'account', 'type': 'address'}],
        'outputs': [{'name': '', 'type': 'uint256'}],
        'stateMutability': 'view',
    },
    {
        'type': 'event',
        'name': 'Transfer',
        'inputs': [
            {'indexed': True, 'name': 'from', 'type': 'address'},
            {'indexed': True, 'name': 'to', 'type': 'address'},
            {'indexed': False, 'name': 'value', 'type': 'uint256'},
        ],
    },
    {
        'type': 'event',
        'name': 'Approval',
        'inputs': [
            {'indexed': True, 'name': 'owner', 'type': 'address'},
            {'indexed': True, 'name': 'spender', 'type': 'address'},
            {'indexed': False, 'name': 'value', 'type': 'uint256'},
        ],
    },
]


@pytest.fixture
def mock_client():
    """Create a mock ChainscanClient."""
    client = MagicMock(spec=ChainscanClient)
    client.call = AsyncMock()
    return client


@pytest.fixture
def sample_contract(mock_client):
    """Create a sample SmartContract instance."""
    return SmartContract(
        address='0x1234567890123456789012345678901234567890',
        abi=SAMPLE_ERC20_ABI,
        client=mock_client,
        is_proxy=False,
        implementation_address=None,
    )


class TestSmartContractInit:
    """Test SmartContract initialization."""

    def test_init_basic(self, mock_client):
        """Test basic initialization."""
        contract = SmartContract(
            address='0xABCD1234567890123456789012345678ABCD1234',
            abi=SAMPLE_ERC20_ABI,
            client=mock_client,
        )

        assert contract.address == '0xabcd1234567890123456789012345678abcd1234'
        assert contract.abi == SAMPLE_ERC20_ABI
        assert contract.client == mock_client
        assert contract.is_proxy is False
        assert contract.implementation_address is None

    def test_init_proxy(self, mock_client):
        """Test initialization with proxy."""
        impl_addr = '0x9876543210987654321098765432109876543210'
        contract = SmartContract(
            address='0x1234567890123456789012345678901234567890',
            abi=SAMPLE_ERC20_ABI,
            client=mock_client,
            is_proxy=True,
            implementation_address=impl_addr,
        )

        assert contract.is_proxy is True
        assert contract.implementation_address == impl_addr.lower()

    def test_build_lookup_maps(self, sample_contract):
        """Test that lookup maps are built correctly."""
        # Check function map
        assert 'transfer' in sample_contract._function_map
        assert 'balanceOf' in sample_contract._function_map

        # Check event map
        assert 'Transfer' in sample_contract._event_map
        assert 'Approval' in sample_contract._event_map

        # Check event signature map (should have topic hashes)
        assert len(sample_contract._event_signature_map) == 2


class TestSmartContractFromAddress:
    """Test SmartContract.from_address() factory method."""

    @pytest.mark.asyncio
    async def test_from_address_normal_contract(self, mock_client):
        """Test creating contract from address (non-proxy)."""
        # Mock CONTRACT_SOURCE to return non-proxy
        mock_client.call.side_effect = [
            [{'Proxy': '0', 'SourceCode': 'contract Test {}'}],  # CONTRACT_SOURCE
            json.dumps(SAMPLE_ERC20_ABI),  # CONTRACT_ABI
        ]

        contract = await SmartContract.from_address(
            '0x1234567890123456789012345678901234567890', mock_client
        )

        assert contract.address == '0x1234567890123456789012345678901234567890'
        assert contract.is_proxy is False
        assert contract.implementation_address is None
        assert len(contract.abi) == 4

        # Verify calls
        assert mock_client.call.call_count == 2
        mock_client.call.assert_any_call(
            Method.CONTRACT_SOURCE, address='0x1234567890123456789012345678901234567890'
        )
        mock_client.call.assert_any_call(
            Method.CONTRACT_ABI, address='0x1234567890123456789012345678901234567890'
        )

    @pytest.mark.asyncio
    async def test_from_address_proxy_contract(self, mock_client):
        """Test creating contract from proxy address."""
        impl_addr = '0x9876543210987654321098765432109876543210'

        # Mock CONTRACT_SOURCE to return proxy info
        mock_client.call.side_effect = [
            [{'Proxy': '1', 'Implementation': impl_addr}],  # CONTRACT_SOURCE
            json.dumps(SAMPLE_ERC20_ABI),  # CONTRACT_ABI from implementation
        ]

        contract = await SmartContract.from_address(
            '0x1234567890123456789012345678901234567890', mock_client
        )

        assert contract.address == '0x1234567890123456789012345678901234567890'
        assert contract.is_proxy is True
        assert contract.implementation_address == impl_addr.lower()

        # Verify ABI was fetched from implementation
        mock_client.call.assert_any_call(Method.CONTRACT_ABI, address=impl_addr.lower())

    @pytest.mark.asyncio
    async def test_from_address_source_fails(self, mock_client):
        """Test graceful fallback when CONTRACT_SOURCE fails."""
        # Mock CONTRACT_SOURCE to fail, but ABI succeeds
        mock_client.call.side_effect = [
            Exception('Source not available'),  # CONTRACT_SOURCE fails
            json.dumps(SAMPLE_ERC20_ABI),  # CONTRACT_ABI succeeds
        ]

        contract = await SmartContract.from_address(
            '0x1234567890123456789012345678901234567890', mock_client
        )

        assert contract.address == '0x1234567890123456789012345678901234567890'
        assert contract.is_proxy is False
        assert len(contract.abi) == 4

    @pytest.mark.asyncio
    async def test_from_address_abi_fails(self, mock_client):
        """Test error when ABI fetch fails."""
        mock_client.call.side_effect = [
            [{'Proxy': '0'}],  # CONTRACT_SOURCE
            Exception('ABI not found'),  # CONTRACT_ABI fails
        ]

        with pytest.raises(ValueError, match='Failed to fetch ABI'):
            await SmartContract.from_address(
                '0x1234567890123456789012345678901234567890', mock_client
            )

    @pytest.mark.asyncio
    async def test_from_address_invalid_abi_format(self, mock_client):
        """Test error when ABI has invalid format."""
        mock_client.call.side_effect = [
            [{'Proxy': '0'}],  # CONTRACT_SOURCE
            'not a valid json',  # Invalid ABI
        ]

        with pytest.raises(ValueError, match='Failed to fetch ABI'):
            await SmartContract.from_address(
                '0x1234567890123456789012345678901234567890', mock_client
            )


class TestSmartContractHelperMethods:
    """Test helper methods for accessing ABI."""

    def test_get_event_abi(self, sample_contract):
        """Test getting event ABI by name."""
        transfer_abi = sample_contract.get_event_abi('Transfer')
        assert transfer_abi is not None
        assert transfer_abi['name'] == 'Transfer'
        assert transfer_abi['type'] == 'event'

        approval_abi = sample_contract.get_event_abi('Approval')
        assert approval_abi is not None
        assert approval_abi['name'] == 'Approval'

        # Non-existent event
        assert sample_contract.get_event_abi('NonExistent') is None

    def test_get_function_abi(self, sample_contract):
        """Test getting function ABI by name."""
        transfer_abi = sample_contract.get_function_abi('transfer')
        assert transfer_abi is not None
        assert transfer_abi['name'] == 'transfer'
        assert transfer_abi['type'] == 'function'

        balance_abi = sample_contract.get_function_abi('balanceOf')
        assert balance_abi is not None
        assert balance_abi['name'] == 'balanceOf'

        # Non-existent function
        assert sample_contract.get_function_abi('nonExistent') is None


class TestSmartContractIterEvents:
    """Test event iteration functionality."""

    @pytest.mark.asyncio
    async def test_iter_events_basic(self, sample_contract):
        """Test basic event iteration."""
        # Mock EVENT_LOGS to return sample logs
        sample_logs = [
            {
                'address': '0x1234567890123456789012345678901234567890',
                'topics': [
                    '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',  # Transfer topic
                    '0x000000000000000000000000a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',  # from
                    '0x000000000000000000000000b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3',  # to
                ],
                'data': '0x0000000000000000000000000000000000000000000000000000000000000064',  # value: 100
                'blockNumber': '0x123456',
                'transactionHash': '0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
                'logIndex': '0x0',
            }
        ]

        sample_contract.client.call.return_value = sample_logs

        events = []
        async for event in sample_contract.iter_events('Transfer', limit=10):
            events.append(event)

        assert len(events) == 1
        assert isinstance(events[0], DecodedEvent)
        assert events[0].name == 'Transfer'
        assert events[0].block_number == 0x123456
        assert (
            events[0].tx_hash
            == '0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890'
        )

    @pytest.mark.asyncio
    async def test_iter_events_with_limit(self, sample_contract):
        """Test event iteration with limit."""
        # Create 5 sample logs
        sample_logs = [
            {
                'address': '0x1234567890123456789012345678901234567890',
                'topics': [
                    '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',
                    '0x000000000000000000000000a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
                    '0x000000000000000000000000b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3',
                ],
                'data': '0x0000000000000000000000000000000000000000000000000000000000000064',
                'blockNumber': str(hex(i)),
                'transactionHash': f'0x{i:064x}',
                'logIndex': '0x0',
            }
            for i in range(5)
        ]

        sample_contract.client.call.return_value = sample_logs

        events = []
        async for event in sample_contract.iter_events('Transfer', limit=3):
            events.append(event)

        # Should only get 3 events due to limit
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_iter_events_invalid_event_name(self, sample_contract):
        """Test error when requesting non-existent event."""
        with pytest.raises(ValueError, match="Event 'NonExistent' not found"):
            async for _ in sample_contract.iter_events('NonExistent'):
                pass

    @pytest.mark.asyncio
    async def test_iter_events_all_events(self, sample_contract):
        """Test iterating all events (no event_name filter)."""
        sample_contract.client.call.return_value = []

        events = []
        async for event in sample_contract.iter_events():
            events.append(event)

        # Should call EVENT_LOGS without topic filter
        call_args = sample_contract.client.call.call_args
        assert call_args[0][0] == Method.EVENT_LOGS
        assert 'topic0' not in call_args[1]


class TestSmartContractIterTransactions:
    """Test transaction iteration functionality."""

    @pytest.mark.asyncio
    async def test_iter_transactions_basic(self, sample_contract):
        """Test basic transaction iteration."""
        # Mock transactions
        sample_txs = [
            {
                'hash': '0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
                'from': '0xa1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
                'to': '0x1234567890123456789012345678901234567890',  # Contract address
                'value': '1000000000000000000',  # 1 ETH
                'input': '0xa9059cbb000000000000000000000000b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c30000000000000000000000000000000000000000000000000000000000000064',
                'blockNumber': '123456',
                'gas': '21000',
                'gasPrice': '1000000000',
            }
        ]

        # Mock client.call to return transactions
        sample_contract.client.call.return_value = sample_txs

        # Ensure iter_transactions attribute doesn't exist or isn't callable
        if hasattr(sample_contract.client, 'iter_transactions'):
            delattr(sample_contract.client, 'iter_transactions')

        transactions = []
        async for tx in sample_contract.iter_transactions(limit=10):
            transactions.append(tx)

        assert len(transactions) == 1
        assert isinstance(transactions[0], DecodedTransaction)
        assert transactions[0].function_name == 'transfer'
        assert (
            transactions[0].tx_hash
            == '0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890'
        )
        assert transactions[0].value_wei == 1000000000000000000

    @pytest.mark.asyncio
    async def test_iter_transactions_filter_to_contract(self, sample_contract):
        """Test that only transactions TO the contract are returned."""
        sample_txs = [
            {
                'hash': '0x1111111111111111111111111111111111111111111111111111111111111111',
                'from': '0xa1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
                'to': '0x1234567890123456789012345678901234567890',  # TO contract
                'value': '0',
                'input': '0xa9059cbb000000000000000000000000b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c30000000000000000000000000000000000000000000000000000000000000064',
                'blockNumber': '123456',
                'gas': '21000',
                'gasPrice': '1000000000',
            },
            {
                'hash': '0x2222222222222222222222222222222222222222222222222222222222222222',
                'from': '0x1234567890123456789012345678901234567890',  # FROM contract
                'to': '0xa1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
                'value': '0',
                'input': '0x',
                'blockNumber': '123457',
                'gas': '21000',
                'gasPrice': '1000000000',
            },
        ]

        sample_contract.client.call.return_value = sample_txs

        # Ensure iter_transactions attribute doesn't exist or isn't callable
        if hasattr(sample_contract.client, 'iter_transactions'):
            delattr(sample_contract.client, 'iter_transactions')

        transactions = []
        async for tx in sample_contract.iter_transactions():
            transactions.append(tx)

        # Should only get transaction TO the contract
        assert len(transactions) == 1
        assert (
            transactions[0].tx_hash
            == '0x1111111111111111111111111111111111111111111111111111111111111111'
        )

    @pytest.mark.asyncio
    async def test_iter_transactions_with_streaming(self, sample_contract):
        """Test transaction iteration using client's streaming API."""

        async def mock_iter_transactions(address):
            """Mock async generator for iter_transactions."""
            sample_txs = [
                {
                    'hash': '0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
                    'from': '0xa1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
                    'to': '0x1234567890123456789012345678901234567890',
                    'value': '0',
                    'input': '0xa9059cbb000000000000000000000000b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c30000000000000000000000000000000000000000000000000000000000000064',
                    'blockNumber': 123456,
                    'gas': '21000',
                    'gasPrice': '1000000000',
                }
            ]
            for tx in sample_txs:
                yield tx

        # Add iter_transactions method to mock client
        sample_contract.client.iter_transactions = mock_iter_transactions

        transactions = []
        async for tx in sample_contract.iter_transactions(limit=10):
            transactions.append(tx)

        assert len(transactions) == 1
        assert transactions[0].function_name == 'transfer'


class TestDecodedEventAndTransaction:
    """Test DecodedEvent and DecodedTransaction classes."""

    def test_decoded_event(self):
        """Test DecodedEvent creation and repr."""
        event = DecodedEvent(
            name='Transfer',
            args={'from': '0x123', 'to': '0x456', 'value': 100},
            address='0x789',
            block_number=123456,
            tx_hash='0xabc',
            log_index=0,
            raw_log={},
        )

        assert event.name == 'Transfer'
        assert event.args['from'] == '0x123'
        assert event.block_number == 123456
        assert 'Transfer' in repr(event)

    def test_decoded_transaction(self):
        """Test DecodedTransaction creation and repr."""
        tx = DecodedTransaction(
            function_name='transfer',
            args={'to': '0x456', 'value': 100},
            tx_hash='0xabc',
            from_address='0x123',
            to_address='0x789',
            value_wei=1000000000000000000,
            block_number=123456,
            gas=21000,
            gas_price_wei=1000000000,
            raw_transaction={},
        )

        assert tx.function_name == 'transfer'
        assert tx.args['to'] == '0x456'
        assert tx.value_wei == 1000000000000000000
        assert 'transfer' in repr(tx)


class TestSmartContractRepr:
    """Test string representations."""

    def test_repr_normal_contract(self, sample_contract):
        """Test repr for normal contract."""
        repr_str = repr(sample_contract)
        assert 'SmartContract' in repr_str
        assert sample_contract.address in repr_str
        assert 'proxy=False' not in repr_str  # Only shown for proxies

    def test_repr_proxy_contract(self, mock_client):
        """Test repr for proxy contract."""
        contract = SmartContract(
            address='0x1234567890123456789012345678901234567890',
            abi=SAMPLE_ERC20_ABI,
            client=mock_client,
            is_proxy=True,
            implementation_address='0x9876543210987654321098765432109876543210',
        )

        repr_str = repr(contract)
        assert 'SmartContract' in repr_str
        assert 'proxy=True' in repr_str
        assert '0x9876543210987654321098765432109876543210' in repr_str
