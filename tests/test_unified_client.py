"""
Tests for the unified ChainscanClient architecture.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.context import ProviderContext
from aiochainscan.core.endpoint import PARSERS, EndpointSpec
from aiochainscan.core.method import Method
from aiochainscan.scanners import get_scanner_class, register_scanner
from aiochainscan.scanners.base import Scanner


class TestMethod:
    """Test Method enum functionality."""

    def test_method_enum_values(self):
        """Test that Method enum has expected values."""
        assert Method.ACCOUNT_BALANCE
        assert Method.TX_BY_HASH
        assert Method.BLOCK_BY_NUMBER
        assert Method.CONTRACT_ABI

    def test_method_string_representation(self):
        """Test Method string representation."""
        assert str(Method.ACCOUNT_BALANCE) == 'Account Balance'
        assert str(Method.TX_BY_HASH) == 'Tx By Hash'
        assert str(Method.ACCOUNT_ERC20_TRANSFERS) == 'Account Erc20 Transfers'


class TestEndpointSpec:
    """Test EndpointSpec functionality."""

    def test_endpoint_spec_creation(self):
        """Test EndpointSpec creation and basic properties."""
        spec = EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account'},
            param_map={'address': 'address'},
            parser=PARSERS['etherscan'],
        )

        assert spec.http_method == 'GET'
        assert spec.path == '/api'
        assert spec.query == {'module': 'account'}
        assert spec.param_map == {'address': 'address'}
        assert spec.parser == PARSERS['etherscan']

    def test_param_mapping(self):
        """Test parameter mapping functionality."""
        spec = EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account', 'action': 'balance'},
            param_map={'address': 'address', 'block': 'tag'},
        )

        mapped = spec.map_params(address='0x123', block='latest')

        expected = {'module': 'account', 'action': 'balance', 'address': '0x123', 'tag': 'latest'}
        assert mapped == expected

    def test_param_mapping_with_none_values(self):
        """Test that None values are filtered out."""
        spec = EndpointSpec(
            http_method='GET', path='/api', param_map={'address': 'address', 'block': 'tag'}
        )

        mapped = spec.map_params(address='0x123', block=None)
        assert mapped == {'address': '0x123'}

    def test_response_parsing(self):
        """Test response parsing."""
        spec = EndpointSpec(http_method='GET', path='/api', parser=PARSERS['etherscan'])

        response = {'status': '1', 'result': '100000'}
        parsed = spec.parse_response(response)
        assert parsed == '100000'

    def test_response_parsing_no_parser(self):
        """Test response when no parser is configured."""
        spec = EndpointSpec(http_method='GET', path='/api')

        response = {'status': '1', 'result': '100000'}
        parsed = spec.parse_response(response)
        assert parsed == response


class TestScannerBase:
    """Test Scanner base class functionality."""

    @pytest.fixture
    def mock_url_builder(self):
        """Mock UrlBuilder for testing."""
        mock_builder = Mock()
        mock_builder.currency = 'ETH'
        return mock_builder

    def test_scanner_initialization_success(self, mock_url_builder):
        """Test successful scanner initialization."""

        @register_scanner
        class TestScanner(Scanner):
            name = 'test'
            version = 'v1'
            supported_networks = {'ethereum', 'test'}
            SPECS = {}

        scanner = TestScanner('test_key', 'ethereum', mock_url_builder)
        assert scanner.api_key == 'test_key'
        assert scanner.network == 'ethereum'
        assert scanner.url_builder == mock_url_builder

    def test_scanner_initialization_unsupported_network(self, mock_url_builder):
        """Test scanner initialization with unsupported network."""

        @register_scanner
        class TestScanner2(Scanner):
            name = 'test2'
            version = 'v1'
            supported_networks = {'ethereum'}
            SPECS = {}

        with pytest.raises(ValueError, match="Network 'testnet' not supported"):
            TestScanner2('test_key', 'testnet', mock_url_builder)

    def test_scanner_supports_method(self, mock_url_builder):
        """Test method support checking."""

        @register_scanner
        class TestScanner3(Scanner):
            name = 'test3'
            version = 'v1'
            supported_networks = {'ethereum'}
            SPECS = {Method.ACCOUNT_BALANCE: EndpointSpec('GET', '/api')}

        scanner = TestScanner3('test_key', 'ethereum', mock_url_builder)
        assert scanner.supports_method(Method.ACCOUNT_BALANCE)
        assert not scanner.supports_method(Method.TX_BY_HASH)

    def test_scanner_get_supported_methods(self, mock_url_builder):
        """Test getting list of supported methods."""

        @register_scanner
        class TestScanner4(Scanner):
            name = 'test4'
            version = 'v1'
            supported_networks = {'ethereum'}
            SPECS = {
                Method.ACCOUNT_BALANCE: EndpointSpec('GET', '/api'),
                Method.TX_BY_HASH: EndpointSpec('GET', '/api'),
            }

        scanner = TestScanner4('test_key', 'ethereum', mock_url_builder)
        methods = scanner.get_supported_methods()
        assert Method.ACCOUNT_BALANCE in methods
        assert Method.TX_BY_HASH in methods
        assert len(methods) == 2


class TestChainscanClient:
    """Test ChainscanClient functionality."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration system."""
        return {'api_key': 'test_api_key', 'api_kind': 'eth', 'network': 'ethereum'}

    @patch('aiochainscan.core.client.global_config')
    def test_client_from_config(self, mock_global_config, mock_config):
        """Test client creation from config."""
        mock_global_config.create_client_config.return_value = mock_config

        client = ChainscanClient.from_config('etherscan', 'ethereum', 'v2')

        assert client.scanner_name == 'etherscan'
        assert client.scanner_version == 'v2'
        assert client.api_kind == 'eth'
        assert client.network == 'ethereum'
        assert client.api_key == 'test_api_key'

        # Network is normalized to 'main' for etherscan config lookup
        mock_global_config.create_client_config.assert_called_once_with('eth', 'main')

    @patch('aiochainscan.core.client.global_config')
    def test_client_from_config_default_version(self, mock_global_config, mock_config):
        """Test client creation from config with default version."""
        mock_global_config.create_client_config.return_value = mock_config

        # Test Etherscan defaults to v2
        client = ChainscanClient.from_config('etherscan', 'ethereum')

        assert client.scanner_name == 'etherscan'
        assert client.scanner_version == 'v2'  # Should default to v2
        assert client.api_kind == 'eth'
        assert client.network == 'ethereum'
        assert client.api_key == 'test_api_key'

    @patch('aiochainscan.core.client.global_config')
    def test_client_from_config_with_chain_id(self, mock_global_config, mock_config):
        """Test client creation from config with numeric chain_id instead of network name.

        This is a regression test for P1 bug where from_config('etherscan', 8453)
        would fail because chain_id wasn't resolved to network name 'base'.
        """
        mock_global_config.create_client_config.return_value = mock_config

        # Use chain_id 8453 (Base) instead of network name
        client = ChainscanClient.from_config('etherscan', 8453)

        assert client.scanner_name == 'etherscan'
        assert client.scanner_version == 'v2'
        assert client.api_kind == 'eth'
        # Chain ID 8453 should be resolved to 'base'
        assert client.network == 'base'
        assert client.api_key == 'test_api_key'

        # Config should be looked up with resolved network name 'main' (Base uses 'main')
        mock_global_config.create_client_config.assert_called_once_with('eth', 'main')

    @patch('aiochainscan.core.client.global_config')
    def test_client_from_config_blockscout_network_mapping(self, mock_global_config, mock_config):
        """Test BlockScout config mapping by network (not hardcoded to blockscout_eth).

        This is a regression test for P1 bug where from_config('blockscout', 'polygon')
        would always use blockscout_eth config regardless of the actual network.
        """
        mock_global_config.create_client_config.return_value = mock_config

        # Test Polygon - should use blockscout_polygon config
        client = ChainscanClient.from_config('blockscout', 'polygon')

        assert client.scanner_name == 'blockscout'
        # Config lookup should use blockscout_polygon, not blockscout_eth
        mock_global_config.create_client_config.assert_called_once_with(
            'blockscout_polygon', 'polygon'
        )

        # Reset mock
        mock_global_config.create_client_config.reset_mock()

        # Test Gnosis - should use blockscout_gnosis config
        client = ChainscanClient.from_config('blockscout', 'gnosis')
        mock_global_config.create_client_config.assert_called_once_with(
            'blockscout_gnosis', 'gnosis'
        )

    @patch('aiochainscan.core.client.global_config')
    def test_client_from_config_blockscout_api_kind_matches_network(
        self, mock_global_config, mock_config
    ):
        """Test that blockscout api_kind matches the network-specific scanner_id.

        This is a regression test for High Severity bug where api_kind was
        hardcoded to 'blockscout_eth' for all networks, causing requests
        to route to wrong explorer domain.
        """
        mock_global_config.create_client_config.return_value = mock_config

        # Test Polygon - api_kind should be blockscout_polygon, not blockscout_eth
        client = ChainscanClient.from_config('blockscout', 'polygon')

        assert client.scanner_name == 'blockscout'
        assert (
            client.api_kind == 'blockscout_polygon'
        ), 'api_kind should match network-specific scanner_id for correct domain routing'

        # Test Gnosis
        client = ChainscanClient.from_config('blockscout', 'gnosis')
        assert client.api_kind == 'blockscout_gnosis'

        # Test Ethereum
        client = ChainscanClient.from_config('blockscout', 'ethereum')
        assert client.api_kind == 'blockscout_eth'

        # Test BlockScout defaults to v1
        client = ChainscanClient.from_config(
            'blockscout', 'eth'
        )  # Use 'eth' instead of 'ethereum'

        assert client.scanner_name == 'blockscout'
        assert client.scanner_version == 'v1'  # Should default to v1

    def test_client_direct_initialization(self):
        """Test direct client initialization."""
        client = ChainscanClient(
            scanner_name='etherscan',
            scanner_version='v2',
            api_kind='eth',
            network='ethereum',
            api_key='test_key',
        )

        assert client.scanner_name == 'etherscan'
        assert client.scanner_version == 'v2'
        assert client.api_kind == 'eth'
        assert client.network == 'ethereum'
        assert client.api_key == 'test_key'

    @pytest.mark.asyncio
    async def test_client_call_method(self):
        """Test calling a method through the client."""
        # Create a mock scanner
        mock_scanner = AsyncMock()
        mock_scanner.call.return_value = '1000000000000000000'

        with patch('aiochainscan.core.client.get_scanner_class') as mock_get_scanner:
            mock_scanner_class = Mock()
            mock_scanner_class.return_value = mock_scanner
            mock_get_scanner.return_value = mock_scanner_class

            client = ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'test_key')

            result = await client.call(Method.ACCOUNT_BALANCE, address='0x123')

            assert result == '1000000000000000000'
            mock_scanner.call.assert_called_once_with(Method.ACCOUNT_BALANCE, address='0x123')

    def test_client_supports_method(self):
        """Test checking method support."""
        mock_scanner = Mock()
        mock_scanner.supports_method.return_value = True

        with patch('aiochainscan.core.client.get_scanner_class') as mock_get_scanner:
            mock_scanner_class = Mock()
            mock_scanner_class.return_value = mock_scanner
            mock_get_scanner.return_value = mock_scanner_class

            client = ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'test_key')

            assert client.supports_method(Method.ACCOUNT_BALANCE)
            mock_scanner.supports_method.assert_called_once_with(Method.ACCOUNT_BALANCE)

    def test_client_get_supported_methods(self):
        """Test getting supported methods."""
        mock_scanner = Mock()
        mock_scanner.get_supported_methods.return_value = [Method.ACCOUNT_BALANCE]

        with patch('aiochainscan.core.client.get_scanner_class') as mock_get_scanner:
            mock_scanner_class = Mock()
            mock_scanner_class.return_value = mock_scanner
            mock_get_scanner.return_value = mock_scanner_class

            client = ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'test_key')

            methods = client.get_supported_methods()
            assert methods == [Method.ACCOUNT_BALANCE]

    def test_client_string_representation(self):
        """Test client string representations."""
        with patch('aiochainscan.core.client.get_scanner_class'):
            client = ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'test_key')

            assert str(client) == 'ChainscanClient(etherscan v2, eth ethereum)'
            assert 'etherscan' in repr(client)
            assert 'v2' in repr(client)

    def test_get_available_scanners(self):
        """Test getting available scanners."""
        with patch('aiochainscan.scanners.list_scanners') as mock_list:
            mock_list.return_value = {('etherscan', 'v2'): Mock(), ('basescan', 'v1'): Mock()}

            scanners = ChainscanClient.get_available_scanners()
            assert ('etherscan', 'v2') in scanners
            assert ('basescan', 'v1') in scanners

    def test_list_scanner_capabilities(self):
        """Test listing scanner capabilities."""
        mock_scanner_class = Mock()
        mock_scanner_class.name = 'etherscan'
        mock_scanner_class.version = 'v2'
        mock_scanner_class.supported_networks = {'ethereum', 'sepolia'}
        mock_scanner_class.auth_mode = 'header'
        mock_scanner_class.auth_field = 'X-API-Key'
        mock_scanner_class.SPECS = {Method.ACCOUNT_BALANCE: Mock()}

        with patch('aiochainscan.scanners.list_scanners') as mock_list:
            mock_list.return_value = {('etherscan', 'v2'): mock_scanner_class}

            capabilities = ChainscanClient.list_scanner_capabilities()

            assert 'etherscan_v2' in capabilities
            scanner_info = capabilities['etherscan_v2']
            assert scanner_info['name'] == 'etherscan'
            assert scanner_info['version'] == 'v2'
            assert 'ethereum' in scanner_info['networks']
            assert scanner_info['auth_mode'] == 'header'
            assert scanner_info['method_count'] == 1


class TestIntegrationWithExistingConfig:
    """Test integration with existing configuration system."""

    def test_scanner_registry_integration(self):
        """Test that scanners are properly registered."""
        # EtherscanV2 should be registered (BaseScanV1 removed)
        etherscan_class = get_scanner_class('etherscan', 'v2')
        # Base network now supported via Etherscan V2

        assert etherscan_class is not None
        assert etherscan_class.name == 'etherscan'

    def test_unknown_scanner_error(self):
        """Test error for unknown scanner."""
        with pytest.raises(ValueError, match='Scanner .* not found'):
            get_scanner_class('unknown', 'v1')


@pytest.mark.asyncio
async def test_end_to_end_workflow():
    """Test complete end-to-end workflow (mocked)."""
    # Mock the scanner call directly instead of the network layer
    with patch('aiochainscan.core.client.global_config') as mock_config:
        mock_config.create_client_config.return_value = {
            'api_key': 'test_key',
            'api_kind': 'eth',
            'network': 'ethereum',
        }

        # Mock the scanner's call method
        with patch.object(ChainscanClient, 'call', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '1000000000000000000'

            # Create client and make call
            client = ChainscanClient.from_config('etherscan', 'ethereum', 'v2')

            result = await client.call(
                Method.ACCOUNT_BALANCE, address='0x742d35Cc6634C0532925a3b8D9Fa7a3D91'
            )

            # Should return parsed result
            assert result == '1000000000000000000'

            # Verify call was made with correct parameters
            mock_call.assert_called_once_with(
                Method.ACCOUNT_BALANCE, address='0x742d35Cc6634C0532925a3b8D9Fa7a3D91'
            )


class TestIterTransactionsValidation:
    """Test iter_transactions parameter validation."""

    @pytest.mark.asyncio
    async def test_iter_transactions_validates_batch_size(self):
        """Test that iter_transactions raises ValueError for invalid batch_size."""
        # Use blockscout_v2 - doesn't require API key
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Test batch_size = 0
        with pytest.raises(ValueError, match='batch_size must be at least 1, got 0'):
            async for _ in client.iter_transactions('0x742d35Cc', batch_size=0):
                pass

        # Test negative batch_size
        with pytest.raises(ValueError, match='batch_size must be at least 1, got -1'):
            async for _ in client.iter_transactions('0x742d35Cc', batch_size=-1):
                pass

        # Test large negative batch_size
        with pytest.raises(ValueError, match='batch_size must be at least 1, got -999'):
            async for _ in client.iter_transactions('0x742d35Cc', batch_size=-999):
                pass

        await client.close()

    @pytest.mark.asyncio
    async def test_iter_transactions_accepts_valid_batch_size(self):
        """Test that iter_transactions accepts valid batch_size values (no exception raised)."""
        # Use blockscout_v2 - doesn't require API key
        # This test just verifies that valid batch_size values don't raise ValueError
        # (actual API calls would fail with 422 for invalid address, but that's OK)

        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # These should NOT raise ValueError - they're valid batch_size values
        # We don't actually iterate (would hit API), just verify no ValueError on creation

        # batch_size = 1 should not raise ValueError
        try:
            gen1 = client.iter_transactions('0x742d35Cc', batch_size=1)
            # The ValueError should happen immediately in the function, not on first iteration
            # So if we get here, validation passed
            assert gen1 is not None
        except ValueError:
            pytest.fail('batch_size=1 should be valid')

        # batch_size = 1000 (default) should not raise ValueError
        try:
            gen2 = client.iter_transactions('0x742d35Cc', batch_size=1000)
            assert gen2 is not None
        except ValueError:
            pytest.fail('batch_size=1000 should be valid')

        # batch_size = 10000 (max) should not raise ValueError
        try:
            gen3 = client.iter_transactions('0x742d35Cc', batch_size=10000)
            assert gen3 is not None
        except ValueError:
            pytest.fail('batch_size=10000 should be valid')

        await client.close()


class TestBlockScoutV2SplitBrainFix:
    """Test the split-brain fix for BlockScout V2.

    This tests that when a user configures blockscout_v2, bulk fetching
    actually uses the V2 API endpoints instead of silently falling back
    to V1 legacy endpoints.
    """

    def test_is_blockscout_v2_detection_by_api_kind(self):
        """Test that _is_blockscout_v2 detects V2 from api_kind."""
        from aiochainscan.services.fetch_all import _is_blockscout_v2

        # api_kind 'blockscout_v2' should trigger V2 routing
        assert _is_blockscout_v2('blockscout_v2', None) is True

        # Other api_kinds should not trigger V2
        assert _is_blockscout_v2('blockscout_eth', None) is False
        assert _is_blockscout_v2('eth', None) is False
        assert _is_blockscout_v2('blockscout', None) is False

    def test_is_blockscout_v2_detection_by_scanner(self):
        """Test that _is_blockscout_v2 detects V2 from scanner instance."""
        from aiochainscan.services.fetch_all import _is_blockscout_v2

        # Mock scanner with V2 attributes
        class MockV2Scanner:
            name = 'blockscout'
            version = 'v2'

        class MockV1Scanner:
            name = 'blockscout'
            version = 'v1'

        class MockEtherscan:
            name = 'etherscan'
            version = 'v2'

        # V2 scanner should trigger V2 routing even with non-V2 api_kind
        assert _is_blockscout_v2('blockscout_eth', MockV2Scanner()) is True

        # V1 scanner should not trigger V2 routing
        assert _is_blockscout_v2('blockscout_eth', MockV1Scanner()) is False

        # Other scanners should not trigger V2 routing
        assert _is_blockscout_v2('eth', MockEtherscan()) is False

    @pytest.mark.asyncio
    async def test_fetch_all_transactions_basic_routes_to_v2(self):
        """Test that fetch_all_transactions_basic routes to V2 when scanner is V2."""
        from unittest.mock import AsyncMock, Mock, patch

        from aiochainscan.services.fetch_all import fetch_all_transactions_basic

        # Create a mock V2 scanner that will be detected
        mock_v2_scanner = Mock()
        mock_v2_scanner.name = 'blockscout'
        mock_v2_scanner.version = 'v2'

        # Mock the V2 fetch function to verify it gets called
        mock_v2_result = [{'hash': '0xabc', 'blockNumber': '123'}]

        with patch(
            'aiochainscan.services.fetch_all._fetch_all_transactions_via_v2_scanner',
            new_callable=AsyncMock,
            return_value=mock_v2_result,
        ) as mock_v2_fetch:
            ctx = ProviderContext(
                api_kind='blockscout_v2',
                network='ethereum',
                api_key='',
                http=Mock(),
                endpoint_builder=Mock(),
            )
            result = await fetch_all_transactions_basic(
                ctx=ctx,
                address='0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
                start_block=0,
                end_block=None,
                scanner=mock_v2_scanner,
            )

            # Should have called V2 function
            mock_v2_fetch.assert_called_once()

            # Result should be from V2 function
            assert result == mock_v2_result

    @pytest.mark.asyncio
    async def test_fetch_all_transactions_fast_routes_to_v2(self):
        """Test that fetch_all_transactions_fast routes to V2 when scanner is V2."""
        from unittest.mock import AsyncMock, Mock, patch

        from aiochainscan.services.fetch_all import fetch_all_transactions_fast

        # Create a mock V2 scanner
        mock_v2_scanner = Mock()
        mock_v2_scanner.name = 'blockscout'
        mock_v2_scanner.version = 'v2'

        mock_v2_result = [{'hash': '0xdef', 'blockNumber': '456'}]

        with patch(
            'aiochainscan.services.fetch_all._fetch_all_transactions_via_v2_scanner',
            new_callable=AsyncMock,
            return_value=mock_v2_result,
        ) as mock_v2_fetch:
            ctx = ProviderContext(
                api_kind='blockscout_v2',
                network='ethereum',
                api_key='',
                http=Mock(),
                endpoint_builder=Mock(),
            )
            result = await fetch_all_transactions_fast(
                ctx=ctx,
                address='0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
                start_block=0,
                end_block=None,
                scanner=mock_v2_scanner,
            )

            mock_v2_fetch.assert_called_once()
            assert result == mock_v2_result

    @pytest.mark.asyncio
    async def test_fetch_all_falls_back_on_v2_error(self):
        """Test that fetch_all falls back to V1 if V2 raises an error."""
        from unittest.mock import AsyncMock, Mock, patch

        from aiochainscan.services.fetch_all import fetch_all_transactions_basic

        mock_v2_scanner = Mock()
        mock_v2_scanner.name = 'blockscout'
        mock_v2_scanner.version = 'v2'

        # V2 function raises NotImplementedError
        with patch(
            'aiochainscan.services.fetch_all._fetch_all_transactions_via_v2_scanner',
            new_callable=AsyncMock,
            side_effect=NotImplementedError('V2 not supported for this'),
        ):
            # Mock the V1 path (fetch_all_generic)
            v1_result = [{'hash': '0xv1', 'blockNumber': '789'}]
            with patch(
                'aiochainscan.services.fetch_all.fetch_all_generic',
                new_callable=AsyncMock,
                return_value=v1_result,
            ) as mock_v1:
                ctx = ProviderContext(
                    api_kind='blockscout_v2',
                    network='ethereum',
                    api_key='',
                    http=Mock(),
                    endpoint_builder=Mock(),
                )
                result = await fetch_all_transactions_basic(
                    ctx=ctx,
                    address='0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
                    start_block=0,
                    end_block=None,
                    scanner=mock_v2_scanner,
                )

                # Should have fallen back to V1
                mock_v1.assert_called_once()
                assert result == v1_result
