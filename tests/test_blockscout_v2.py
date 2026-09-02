"""
Tests for BlockScout REST API V2 scanner implementation.

Tests cover:
- Scanner registration
- Endpoint specifications
- Response parsers
- Path parameter substitution
- URL building
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from aiochainscan.core.method import Method
from aiochainscan.scanners import SCANNER_REGISTRY, get_scanner_class, list_scanners
from aiochainscan.scanners.blockscout_v2 import (
    BlockScoutV2Scanner,
    _parse_balance,
    _parse_contract_abi,
    _parse_token_portfolio,
    _parse_transactions,
)

# ============================================================================
# Scanner Registration Tests
# ============================================================================


class TestScannerRegistration:
    """Tests for scanner registration in the global registry."""

    def test_scanner_registered(self) -> None:
        """BlockScoutV2Scanner should be registered in SCANNER_REGISTRY."""
        assert ('blockscout', 'v2') in SCANNER_REGISTRY

    def test_get_scanner_class(self) -> None:
        """Should be able to retrieve scanner class by name and version."""
        scanner_class = get_scanner_class('blockscout', 'v2')
        assert scanner_class is BlockScoutV2Scanner

    def test_list_scanners_includes_v2(self) -> None:
        """list_scanners should include blockscout v2."""
        scanners = list_scanners()
        assert ('blockscout', 'v2') in scanners


# ============================================================================
# Scanner Attributes Tests
# ============================================================================


class TestScannerAttributes:
    """Tests for scanner class attributes."""

    def test_name_and_version(self) -> None:
        """Scanner should have correct name and version."""
        assert BlockScoutV2Scanner.name == 'blockscout'
        assert BlockScoutV2Scanner.version == 'v2'

    def test_supported_networks(self) -> None:
        """Scanner should support expected networks."""
        expected_networks = {
            'ethereum',
            'eth',
            'sepolia',
            'gnosis',
            'polygon',
            'arbitrum',
            'optimism',
            'base',
        }
        assert expected_networks.issubset(BlockScoutV2Scanner.supported_networks)

    def test_base_urls_defined(self) -> None:
        """All supported networks should have base URLs."""
        for network in BlockScoutV2Scanner.supported_networks:
            assert network in BlockScoutV2Scanner.BASE_URLS

    def test_auth_not_required(self) -> None:
        """V2 API should not require API key."""
        for method, spec in BlockScoutV2Scanner.SPECS.items():
            assert spec.requires_api_key is False, f'{method} should not require API key'


# ============================================================================
# Endpoint Specs Tests
# ============================================================================


class TestEndpointSpecs:
    """Tests for endpoint specifications."""

    def test_account_balance_spec(self) -> None:
        """ACCOUNT_BALANCE spec should be correctly configured."""
        spec = BlockScoutV2Scanner.SPECS[Method.ACCOUNT_BALANCE]
        assert spec.http_method == 'GET'
        assert spec.path == '/api/v2/addresses/{address}'
        assert spec.requires_api_key is False
        assert spec.parser is _parse_balance

    def test_token_portfolio_spec(self) -> None:
        """ACCOUNT_TOKEN_PORTFOLIO spec should be correctly configured."""
        spec = BlockScoutV2Scanner.SPECS[Method.ACCOUNT_TOKEN_PORTFOLIO]
        assert spec.http_method == 'GET'
        assert spec.path == '/api/v2/addresses/{address}/tokens'
        assert spec.query == {'type': 'ERC-20'}
        assert spec.requires_api_key is False
        assert spec.parser is _parse_token_portfolio

    def test_transactions_spec(self) -> None:
        """ACCOUNT_TRANSACTIONS spec should be correctly configured."""
        spec = BlockScoutV2Scanner.SPECS[Method.ACCOUNT_TRANSACTIONS]
        assert spec.http_method == 'GET'
        assert spec.path == '/api/v2/addresses/{address}/transactions'
        assert spec.requires_api_key is False
        assert spec.parser is _parse_transactions

    def test_contract_abi_spec(self) -> None:
        """CONTRACT_ABI spec should be correctly configured."""
        spec = BlockScoutV2Scanner.SPECS[Method.CONTRACT_ABI]
        assert spec.http_method == 'GET'
        assert spec.path == '/api/v2/smart-contracts/{address}'
        assert spec.requires_api_key is False
        assert spec.parser is _parse_contract_abi

    def test_all_specs_have_path_placeholder(self) -> None:
        """All specs should substitute a path parameter (e.g. {address})."""
        for method, spec in BlockScoutV2Scanner.SPECS.items():
            assert (
                '{' in spec.path and '}' in spec.path
            ), f'{method} path should contain a path placeholder: {spec.path}'

    def test_block_by_number_spec(self) -> None:
        """BLOCK_BY_NUMBER spec should be correctly configured."""
        spec = BlockScoutV2Scanner.SPECS[Method.BLOCK_BY_NUMBER]
        assert spec.http_method == 'GET'
        assert spec.path == '/api/v2/blocks/{block_number}'
        assert spec.requires_api_key is False
        assert 'block_number' in spec.param_map


# ============================================================================
# Response Parser Tests
# ============================================================================


class TestResponseParsers:
    """Tests for response parser functions."""

    def test_parse_balance_extracts_coin_balance(self) -> None:
        """_parse_balance should extract coin_balance field."""
        response = {
            'hash': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
            'coin_balance': '32122885900610537215',
            'ens_domain_name': 'vitalik.eth',
            'is_contract': False,
        }
        assert _parse_balance(response) == '32122885900610537215'

    def test_parse_balance_returns_zero_if_missing(self) -> None:
        """_parse_balance should return '0' if coin_balance is missing."""
        assert _parse_balance({}) == '0'
        assert _parse_balance({'hash': '0x...'}) == '0'

    def test_parse_token_portfolio_extracts_items(self) -> None:
        """_parse_token_portfolio should extract items array."""
        response = {
            'items': [
                {
                    'token': {
                        'address_hash': '0xA0b86a33E6441e72f8F289e4Ee40e99f12',
                        'name': 'USDC',
                        'symbol': 'USDC',
                        'decimals': '6',
                    },
                    'value': '5878047570',
                },
                {
                    'token': {
                        'address_hash': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
                        'name': 'Tether USD',
                        'symbol': 'USDT',
                        'decimals': '6',
                    },
                    'value': '1000000000',
                },
            ],
            'next_page_params': {'fiat_value': '1234.56', 'id': 123},
        }
        result = _parse_token_portfolio(response)
        assert len(result) == 2
        assert result[0]['token']['symbol'] == 'USDC'
        assert result[0]['value'] == '5878047570'

    def test_parse_token_portfolio_returns_empty_if_no_items(self) -> None:
        """_parse_token_portfolio should return empty list if items missing."""
        assert _parse_token_portfolio({}) == []
        assert _parse_token_portfolio({'next_page_params': {}}) == []

    def test_parse_transactions_extracts_items(self) -> None:
        """_parse_transactions should extract items array."""
        response = {
            'items': [
                {'hash': '0x123...', 'from': '0xabc...', 'to': '0xdef...'},
                {'hash': '0x456...', 'from': '0xghi...', 'to': '0xjkl...'},
            ],
            'next_page_params': {'block_number': 12345},
        }
        result = _parse_transactions(response)
        assert len(result) == 2
        assert result[0]['hash'] == '0x123...'

    def test_parse_transactions_returns_empty_if_no_items(self) -> None:
        """_parse_transactions should return empty list if items missing."""
        assert _parse_transactions({}) == []

    def test_parse_contract_abi_extracts_abi(self) -> None:
        """_parse_contract_abi should extract abi array."""
        response = {
            'abi': [
                {'type': 'function', 'name': 'transfer'},
                {'type': 'event', 'name': 'Transfer'},
            ],
            'name': 'TestContract',
            'is_verified': True,
        }
        result = _parse_contract_abi(response)
        assert result is not None
        assert len(result) == 2
        assert result[0]['name'] == 'transfer'

    def test_parse_contract_abi_returns_none_if_missing(self) -> None:
        """_parse_contract_abi should return None if abi is missing."""
        assert _parse_contract_abi({}) is None
        assert _parse_contract_abi({'is_verified': False}) is None


# ============================================================================
# Scanner Initialization Tests
# ============================================================================


class TestScannerInitialization:
    """Tests for scanner initialization."""

    @pytest.fixture
    def mock_url_builder(self) -> MagicMock:
        """Create a mock URL builder."""
        return MagicMock()

    def test_init_ethereum_network(self, mock_url_builder: MagicMock) -> None:
        """Scanner should initialize correctly for ethereum network."""
        scanner = BlockScoutV2Scanner(
            api_key='',
            network='ethereum',
            url_builder=mock_url_builder,
        )
        assert scanner.network == 'ethereum'
        assert scanner.base_url == 'https://eth.blockscout.com'

    def test_init_eth_alias(self, mock_url_builder: MagicMock) -> None:
        """Scanner should accept 'eth' as alias for ethereum."""
        scanner = BlockScoutV2Scanner(
            api_key='',
            network='eth',
            url_builder=mock_url_builder,
        )
        assert scanner.base_url == 'https://eth.blockscout.com'

    def test_init_other_networks(self, mock_url_builder: MagicMock) -> None:
        """Scanner should initialize for various supported networks."""
        networks_and_urls = [
            ('sepolia', 'https://eth-sepolia.blockscout.com'),
            ('gnosis', 'https://gnosis.blockscout.com'),
            ('polygon', 'https://polygon.blockscout.com'),
            ('base', 'https://base.blockscout.com'),
        ]
        for network, expected_url in networks_and_urls:
            scanner = BlockScoutV2Scanner(
                api_key='',
                network=network,
                url_builder=mock_url_builder,
            )
            assert scanner.base_url == expected_url

    def test_init_unsupported_network_raises(self, mock_url_builder: MagicMock) -> None:
        """Scanner should raise ValueError for unsupported network."""
        with pytest.raises(ValueError, match='not supported'):
            BlockScoutV2Scanner(
                api_key='',
                network='unsupported_network',
                url_builder=mock_url_builder,
            )


# ============================================================================
# URL Building Tests
# ============================================================================


class TestUrlBuilding:
    """Tests for URL building with path parameters."""

    @pytest.fixture
    def scanner(self) -> BlockScoutV2Scanner:
        """Create a scanner instance for testing."""
        mock_url_builder = MagicMock()
        return BlockScoutV2Scanner(
            api_key='',
            network='ethereum',
            url_builder=mock_url_builder,
        )

    def test_build_url_substitutes_address(self, scanner: BlockScoutV2Scanner) -> None:
        """_build_url should substitute {address} placeholder."""
        spec = BlockScoutV2Scanner.SPECS[Method.ACCOUNT_BALANCE]
        address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

        url = scanner._build_url(spec, address=address)

        expected = f'https://eth.blockscout.com/api/v2/addresses/{address}'
        assert url == expected

    def test_build_url_for_transactions(self, scanner: BlockScoutV2Scanner) -> None:
        """_build_url should work for transactions endpoint."""
        spec = BlockScoutV2Scanner.SPECS[Method.ACCOUNT_TRANSACTIONS]
        address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

        url = scanner._build_url(spec, address=address)

        expected = f'https://eth.blockscout.com/api/v2/addresses/{address}/transactions'
        assert url == expected

    def test_build_url_for_smart_contract(self, scanner: BlockScoutV2Scanner) -> None:
        """_build_url should work for smart contracts endpoint."""
        spec = BlockScoutV2Scanner.SPECS[Method.CONTRACT_ABI]
        address = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'

        url = scanner._build_url(spec, address=address)

        expected = f'https://eth.blockscout.com/api/v2/smart-contracts/{address}'
        assert url == expected

    def test_build_query_params_excludes_path_params(self, scanner: BlockScoutV2Scanner) -> None:
        """_build_query_params should not include path parameters."""
        spec = BlockScoutV2Scanner.SPECS[Method.ACCOUNT_TOKEN_PORTFOLIO]
        address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

        params = scanner._build_query_params(spec, address=address)

        # Should include static query params but not address
        assert 'type' in params
        assert params['type'] == 'ERC-20'
        # Address should NOT be in query params (it's a path param)
        assert 'address' not in params

    def test_build_query_params_includes_static_params(self, scanner: BlockScoutV2Scanner) -> None:
        """_build_query_params should include static query parameters."""
        spec = BlockScoutV2Scanner.SPECS[Method.ACCOUNT_TOKEN_PORTFOLIO]

        params = scanner._build_query_params(spec, address='0x...')

        assert params == {'type': 'ERC-20'}


# ============================================================================
# Method Support Tests
# ============================================================================


class TestMethodSupport:
    """Tests for method support checking."""

    @pytest.fixture
    def scanner(self) -> BlockScoutV2Scanner:
        """Create a scanner instance for testing."""
        mock_url_builder = MagicMock()
        return BlockScoutV2Scanner(
            api_key='',
            network='ethereum',
            url_builder=mock_url_builder,
        )

    def test_supports_account_balance(self, scanner: BlockScoutV2Scanner) -> None:
        """Scanner should support ACCOUNT_BALANCE method."""
        assert scanner.supports_method(Method.ACCOUNT_BALANCE)

    def test_supports_token_portfolio(self, scanner: BlockScoutV2Scanner) -> None:
        """Scanner should support ACCOUNT_TOKEN_PORTFOLIO method."""
        assert scanner.supports_method(Method.ACCOUNT_TOKEN_PORTFOLIO)

    def test_supports_transactions(self, scanner: BlockScoutV2Scanner) -> None:
        """Scanner should support ACCOUNT_TRANSACTIONS method."""
        assert scanner.supports_method(Method.ACCOUNT_TRANSACTIONS)

    def test_supports_contract_abi(self, scanner: BlockScoutV2Scanner) -> None:
        """Scanner should support CONTRACT_ABI method."""
        assert scanner.supports_method(Method.CONTRACT_ABI)

    def test_does_not_support_unsupported_methods(self, scanner: BlockScoutV2Scanner) -> None:
        """Scanner should not support methods not in SPECS."""
        assert not scanner.supports_method(Method.GAS_ORACLE)
        assert not scanner.supports_method(Method.ETH_PRICE)

    def test_get_supported_methods(self, scanner: BlockScoutV2Scanner) -> None:
        """get_supported_methods should return list of supported methods."""
        methods = scanner.get_supported_methods()
        assert Method.ACCOUNT_BALANCE in methods
        assert Method.ACCOUNT_TOKEN_PORTFOLIO in methods
        assert Method.ACCOUNT_TRANSACTIONS in methods
        assert Method.CONTRACT_ABI in methods
        assert Method.BLOCK_BY_NUMBER in methods
        assert Method.TOKEN_HOLDERS in methods
        assert Method.TOKEN_HOLDER_COUNT in methods
        assert len(methods) == 7


# ============================================================================
# Call Method Tests (Mocked)
# ============================================================================


class TestCallMethod:
    """Tests for the call method with mocked HTTP."""

    @pytest.fixture
    def scanner(self) -> BlockScoutV2Scanner:
        """Create a scanner instance for testing."""
        mock_url_builder = MagicMock()
        return BlockScoutV2Scanner(
            api_key='',
            network='ethereum',
            url_builder=mock_url_builder,
        )

    @pytest.mark.asyncio
    async def test_call_unsupported_method_raises(self, scanner: BlockScoutV2Scanner) -> None:
        """Calling unsupported method should raise ValueError."""
        with pytest.raises(ValueError, match='not supported'):
            await scanner.call(Method.GAS_ORACLE)

    @pytest.mark.asyncio
    async def test_call_balance_with_mocked_response(self, scanner: BlockScoutV2Scanner) -> None:
        """call should correctly fetch and parse balance."""
        mock_response = {
            'hash': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
            'coin_balance': '12345678901234567890',
        }

        # Mock _network_client.request() (scanner now uses Network layer)
        scanner._network_client = MagicMock()
        scanner._network_client.request = AsyncMock(return_value=mock_response)

        result = await scanner.call(
            Method.ACCOUNT_BALANCE,
            address='0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        )

        assert result == '12345678901234567890'
        # Verify request was made with correct parameters
        scanner._network_client.request.assert_called_once()
        call_args = scanner._network_client.request.call_args
        assert call_args.kwargs['method'] == 'GET'
        assert 'addresses' in call_args.kwargs['url']

    @pytest.mark.asyncio
    async def test_call_token_portfolio_with_mocked_response(
        self, scanner: BlockScoutV2Scanner
    ) -> None:
        """call should correctly fetch and parse token portfolio."""
        mock_response = {
            'items': [
                {
                    'token': {'symbol': 'USDC', 'decimals': '6'},
                    'value': '1000000',
                }
            ],
            'next_page_params': None,
        }

        # Mock _network_client.request() (scanner now uses Network layer)
        scanner._network_client = MagicMock()
        scanner._network_client.request = AsyncMock(return_value=mock_response)

        result = await scanner.call(
            Method.ACCOUNT_TOKEN_PORTFOLIO,
            address='0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        )

        assert len(result) == 1
        assert result[0]['token']['symbol'] == 'USDC'
        assert result[0]['value'] == '1000000'
        # Verify request was made
        scanner._network_client.request.assert_called_once()


# ============================================================================
# String Representation Tests
# ============================================================================


class TestStringRepresentation:
    """Tests for __str__ and __repr__ methods."""

    @pytest.fixture
    def scanner(self) -> BlockScoutV2Scanner:
        """Create a scanner instance for testing."""
        mock_url_builder = MagicMock()
        return BlockScoutV2Scanner(
            api_key='',
            network='ethereum',
            url_builder=mock_url_builder,
        )

    def test_str_representation(self, scanner: BlockScoutV2Scanner) -> None:
        """__str__ should return human-readable representation."""
        result = str(scanner)
        assert 'BlockScout' in result
        assert 'v2' in result
        assert 'eth.blockscout.com' in result

    def test_repr_representation(self, scanner: BlockScoutV2Scanner) -> None:
        """__repr__ should return detailed representation."""
        result = repr(scanner)
        assert 'BlockScoutV2Scanner' in result
        assert 'ethereum' in result
        assert 'eth.blockscout.com' in result
        assert 'methods=7' in result
