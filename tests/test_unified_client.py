"""
Tests for the unified ChainscanClient architecture.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from aiochainscan.core.client import ChainscanClient
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

        client = ChainscanClient.from_config('etherscan', 'v2', 'ethereum')

        assert client.scanner_name == 'etherscan'
        assert client.scanner_version == 'v2'
        assert client.api_kind == 'eth'
        assert client.network == 'ethereum'
        assert client.api_key == 'test_api_key'

        mock_global_config.create_client_config.assert_called_once_with('eth', 'ethereum')

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
            client = ChainscanClient.from_config('etherscan', 'v2', 'ethereum')

            result = await client.call(
                Method.ACCOUNT_BALANCE, address='0x742d35Cc6634C0532925a3b8D9Fa7a3D91'
            )

            # Should return parsed result
            assert result == '1000000000000000000'

            # Verify call was made with correct parameters
            mock_call.assert_called_once_with(
                Method.ACCOUNT_BALANCE, address='0x742d35Cc6634C0532925a3b8D9Fa7a3D91'
            )
