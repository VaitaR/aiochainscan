"""
Tests for the unified ChainscanClient architecture.
"""

from unittest.mock import Mock, patch

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
            supported_networks = {'main', 'test'}
            SPECS = {}

        from aiochainscan.chains import ChainInfo

        chain_info = ChainInfo(
            chain_id=1,
            name='ethereum',
            display_name='Ethereum Mainnet',
            etherscan_network_name='main',
        )
        scanner = TestScanner('test_key', chain_info, mock_url_builder)
        assert scanner.api_key == 'test_key'
        assert scanner.network == 'main'
        assert scanner.url_builder == mock_url_builder

    def test_scanner_initialization_unsupported_network(self, mock_url_builder):
        """Test scanner initialization with unsupported network."""

        @register_scanner
        class TestScanner2(Scanner):
            name = 'test2'
            version = 'v1'
            supported_networks = {'main'}
            SPECS = {}

        from aiochainscan.chains import ChainInfo

        chain_info_unsupported = ChainInfo(
            chain_id=999,
            name='testchain',
            display_name='Test Chain',
            etherscan_network_name='testnet',
        )
        with pytest.raises(ValueError, match='not supported'):
            TestScanner2('test_key', chain_info_unsupported, mock_url_builder)

    def test_scanner_supports_method(self, mock_url_builder):
        """Test method support checking."""

        @register_scanner
        class TestScanner3(Scanner):
            name = 'test3'
            version = 'v1'
            supported_networks = {'main'}
            SPECS = {Method.ACCOUNT_BALANCE: EndpointSpec('GET', '/api')}

        from aiochainscan.chains import ChainInfo

        chain_info = ChainInfo(
            chain_id=1,
            name='ethereum',
            display_name='Ethereum Mainnet',
            etherscan_network_name='main',
        )
        scanner = TestScanner3('test_key', chain_info, mock_url_builder)
        assert scanner.supports_method(Method.ACCOUNT_BALANCE)
        assert not scanner.supports_method(Method.TX_BY_HASH)

    def test_scanner_get_supported_methods(self, mock_url_builder):
        """Test getting list of supported methods."""

        @register_scanner
        class TestScanner4(Scanner):
            name = 'test4'
            version = 'v1'
            supported_networks = {'main'}
            SPECS = {
                Method.ACCOUNT_BALANCE: EndpointSpec('GET', '/api'),
                Method.TX_BY_HASH: EndpointSpec('GET', '/api'),
            }

        from aiochainscan.chains import ChainInfo

        chain_info = ChainInfo(
            chain_id=1,
            name='ethereum',
            display_name='Ethereum Mainnet',
            etherscan_network_name='main',
        )
        scanner = TestScanner4('test_key', chain_info, mock_url_builder)
        methods = scanner.get_supported_methods()
        assert Method.ACCOUNT_BALANCE in methods
        assert Method.TX_BY_HASH in methods
        assert len(methods) == 2


class TestChainscanClient:
    """Test ChainscanClient functionality."""

    @pytest.fixture
    def ethereum_chain_info(self):
        """Ethereum chain info fixture."""
        from aiochainscan.chains import ChainInfo

        return ChainInfo(
            chain_id=1,
            name='ethereum',
            display_name='Ethereum Mainnet',
            etherscan_network_name='main',
            etherscan_api_kind='eth',
        )

    def test_client_direct_initialization(self, ethereum_chain_info):
        """Test direct client initialization."""
        client = ChainscanClient(
            scanner_name='etherscan',
            scanner_version='v2',
            chain_info=ethereum_chain_info,
            api_key='test_key',
        )

        assert client.scanner_name == 'etherscan'
        assert client.scanner_version == 'v2'
        assert client.chain_info == ethereum_chain_info
        assert client.api_key == 'test_key'

    @pytest.mark.asyncio
    async def test_client_call_method(self, ethereum_chain_info):
        """Test calling a method through the client."""
        from unittest.mock import AsyncMock

        # Create a mock scanner
        mock_scanner = AsyncMock()
        mock_scanner.call.return_value = '1000000000000000000'

        with patch('aiochainscan.core.client.get_scanner_class') as mock_get_scanner:
            mock_scanner_class = Mock()
            mock_scanner_class.return_value = mock_scanner
            mock_get_scanner.return_value = mock_scanner_class

            client = ChainscanClient('etherscan', 'v2', ethereum_chain_info, 'test_key')

            result = await client.call(Method.ACCOUNT_BALANCE, address='0x123')

            assert result == '1000000000000000000'
            mock_scanner.call.assert_called_once_with(Method.ACCOUNT_BALANCE, address='0x123')

    def test_client_supports_method(self, ethereum_chain_info):
        """Test checking method support."""
        mock_scanner = Mock()
        mock_scanner.supports_method.return_value = True

        with patch('aiochainscan.core.client.get_scanner_class') as mock_get_scanner:
            mock_scanner_class = Mock()
            mock_scanner_class.return_value = mock_scanner
            mock_get_scanner.return_value = mock_scanner_class

            client = ChainscanClient('etherscan', 'v2', ethereum_chain_info, 'test_key')

            assert client.supports_method(Method.ACCOUNT_BALANCE)
            mock_scanner.supports_method.assert_called_once_with(Method.ACCOUNT_BALANCE)

    def test_client_get_supported_methods(self, ethereum_chain_info):
        """Test getting supported methods."""
        mock_scanner = Mock()
        mock_scanner.get_supported_methods.return_value = [Method.ACCOUNT_BALANCE]

        with patch('aiochainscan.core.client.get_scanner_class') as mock_get_scanner:
            mock_scanner_class = Mock()
            mock_scanner_class.return_value = mock_scanner
            mock_get_scanner.return_value = mock_scanner_class

            client = ChainscanClient('etherscan', 'v2', ethereum_chain_info, 'test_key')

            methods = client.get_supported_methods()
            assert methods == [Method.ACCOUNT_BALANCE]
            mock_scanner.get_supported_methods.assert_called_once()

    def test_client_string_representation(self, ethereum_chain_info):
        """Test client string representations."""
        with patch('aiochainscan.core.client.get_scanner_class'):
            client = ChainscanClient('etherscan', 'v2', ethereum_chain_info, 'test_key')

            str_repr = str(client)
            assert 'etherscan' in str_repr.lower()
            assert 'v2' in str_repr

            repr_repr = repr(client)
            assert 'etherscan' in repr_repr.lower()
            assert 'v2' in repr_repr

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
        mock_scanner_class.supported_networks = {'main', 'sepolia'}
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
            assert 'main' in scanner_info['networks']
            assert scanner_info['auth_mode'] == 'header'
            assert scanner_info['method_count'] == 1


class TestIntegrationWithExistingConfig:
    """Test integration with existing configuration system."""

    def test_scanner_registry_integration(self):
        """Test that scanners are properly registered."""
        # EtherscanV2 and BaseScanV1 should be registered
        etherscan_class = get_scanner_class('etherscan', 'v2')
        basescan_class = get_scanner_class('basescan', 'v1')

        assert etherscan_class is not None
        assert basescan_class is not None
        assert etherscan_class.name == 'etherscan'
        assert basescan_class.name == 'basescan'

    def test_unknown_scanner_error(self):
        """Test error for unknown scanner."""
        with pytest.raises(ValueError, match='Scanner .* not found'):
            get_scanner_class('unknown', 'v1')


@pytest.mark.asyncio
async def test_end_to_end_workflow():
    """Test complete end-to-end workflow (mocked)."""
    from unittest.mock import AsyncMock

    from aiochainscan.chains import ChainInfo

    # Create test chain info
    chain_info = ChainInfo(
        chain_id=1,
        name='ethereum',
        display_name='Ethereum Mainnet',
        etherscan_network_name='main',
        etherscan_api_kind='eth',
    )

    # Mock the scanner's call method
    with patch.object(ChainscanClient, 'call', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = '1000000000000000000'

        # Create client with ChainInfo
        with patch('aiochainscan.core.client.get_scanner_class'):
            client = ChainscanClient('etherscan', 'v2', chain_info, 'test_key')

            result = await client.call(
                Method.ACCOUNT_BALANCE, address='0x742d35Cc6634C0532925a3b8D9Fa7a3D91'
            )

            # Should return parsed result
            assert result == '1000000000000000000'

            # Verify call was made with correct parameters
            mock_call.assert_called_once_with(
                Method.ACCOUNT_BALANCE, address='0x742d35Cc6634C0532925a3b8D9Fa7a3D91'
            )
