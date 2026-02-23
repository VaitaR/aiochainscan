"""
Tests for new API methods: token/NFT portfolio and contract verification.
"""

from aiochainscan.core.method import Method
from aiochainscan.scanners._etherscan_like import EtherscanLikeScanner
from aiochainscan.scanners.etherscan_v2 import EtherscanV2


class TestNewMethodsExist:
    """Test that new methods exist in Method enum."""

    def test_account_token_portfolio_exists(self):
        """ACCOUNT_TOKEN_PORTFOLIO method should exist."""
        assert hasattr(Method, 'ACCOUNT_TOKEN_PORTFOLIO')
        assert Method.ACCOUNT_TOKEN_PORTFOLIO is not None

    def test_account_nft_portfolio_exists(self):
        """ACCOUNT_NFT_PORTFOLIO method should exist."""
        assert hasattr(Method, 'ACCOUNT_NFT_PORTFOLIO')
        assert Method.ACCOUNT_NFT_PORTFOLIO is not None

    def test_contract_verify_exists(self):
        """CONTRACT_VERIFY method should exist."""
        assert hasattr(Method, 'CONTRACT_VERIFY')
        assert Method.CONTRACT_VERIFY is not None

    def test_contract_verify_status_exists(self):
        """CONTRACT_VERIFY_STATUS method should exist."""
        assert hasattr(Method, 'CONTRACT_VERIFY_STATUS')
        assert Method.CONTRACT_VERIFY_STATUS is not None

    def test_all_new_methods_are_enum_members(self):
        """All new methods should be proper enum members."""
        new_methods = [
            Method.ACCOUNT_TOKEN_PORTFOLIO,
            Method.ACCOUNT_NFT_PORTFOLIO,
            Method.CONTRACT_VERIFY,
            Method.CONTRACT_VERIFY_STATUS,
        ]
        for method in new_methods:
            assert isinstance(method, Method)
            assert method.name in dir(Method)


class TestEtherscanV2Specs:
    """Test that EtherscanV2 SPECS contain new methods."""

    def test_specs_contain_account_token_portfolio(self):
        """SPECS should contain ACCOUNT_TOKEN_PORTFOLIO."""
        assert Method.ACCOUNT_TOKEN_PORTFOLIO in EtherscanV2.SPECS

    def test_specs_contain_account_nft_portfolio(self):
        """SPECS should contain ACCOUNT_NFT_PORTFOLIO."""
        assert Method.ACCOUNT_NFT_PORTFOLIO in EtherscanV2.SPECS

    def test_specs_contain_contract_verify(self):
        """SPECS should contain CONTRACT_VERIFY."""
        assert Method.CONTRACT_VERIFY in EtherscanV2.SPECS

    def test_specs_contain_contract_verify_status(self):
        """SPECS should contain CONTRACT_VERIFY_STATUS."""
        assert Method.CONTRACT_VERIFY_STATUS in EtherscanV2.SPECS

    def test_account_token_portfolio_spec_structure(self):
        """ACCOUNT_TOKEN_PORTFOLIO spec should have correct structure."""
        spec = EtherscanV2.SPECS[Method.ACCOUNT_TOKEN_PORTFOLIO]
        assert spec.http_method == 'GET'
        assert spec.path == '/api'
        assert spec.query['module'] == 'account'
        assert spec.query['action'] == 'addresstokenbalance'
        assert 'address' in spec.param_map

    def test_account_nft_portfolio_spec_structure(self):
        """ACCOUNT_NFT_PORTFOLIO spec should have correct structure."""
        spec = EtherscanV2.SPECS[Method.ACCOUNT_NFT_PORTFOLIO]
        assert spec.http_method == 'GET'
        assert spec.path == '/api'
        assert spec.query['module'] == 'account'
        assert spec.query['action'] == 'addresstokennftinventory'
        assert 'address' in spec.param_map

    def test_contract_verify_spec_structure(self):
        """CONTRACT_VERIFY spec should have correct structure."""
        spec = EtherscanV2.SPECS[Method.CONTRACT_VERIFY]
        assert spec.http_method == 'POST'
        assert spec.path == '/api'
        assert spec.query['module'] == 'contract'
        assert spec.query['action'] == 'verifysourcecode'
        assert 'contract_address' in spec.param_map
        assert 'source_code' in spec.param_map
        assert 'compiler_version' in spec.param_map

    def test_contract_verify_status_spec_structure(self):
        """CONTRACT_VERIFY_STATUS spec should have correct structure."""
        spec = EtherscanV2.SPECS[Method.CONTRACT_VERIFY_STATUS]
        assert spec.http_method == 'GET'
        assert spec.path == '/api'
        assert spec.query['module'] == 'contract'
        assert spec.query['action'] == 'checkverifystatus'
        assert 'guid' in spec.param_map


class TestEtherscanLikeSpecs:
    """Test that EtherscanLikeScanner (base for BlockscoutV1) contains new methods."""

    def test_specs_contain_account_token_portfolio(self):
        """SPECS should contain ACCOUNT_TOKEN_PORTFOLIO."""
        assert Method.ACCOUNT_TOKEN_PORTFOLIO in EtherscanLikeScanner.SPECS

    def test_specs_contain_account_nft_portfolio(self):
        """SPECS should contain ACCOUNT_NFT_PORTFOLIO."""
        assert Method.ACCOUNT_NFT_PORTFOLIO in EtherscanLikeScanner.SPECS

    def test_specs_contain_contract_verify(self):
        """SPECS should contain CONTRACT_VERIFY."""
        assert Method.CONTRACT_VERIFY in EtherscanLikeScanner.SPECS

    def test_specs_contain_contract_verify_status(self):
        """SPECS should contain CONTRACT_VERIFY_STATUS."""
        assert Method.CONTRACT_VERIFY_STATUS in EtherscanLikeScanner.SPECS


class TestEndpointSpecParamMapping:
    """Test that param_map correctly maps parameters."""

    def test_token_portfolio_param_mapping(self):
        """Test param mapping for token portfolio."""
        spec = EtherscanV2.SPECS[Method.ACCOUNT_TOKEN_PORTFOLIO]
        params = spec.map_params(address='0x123', page=1, offset=100)
        assert params['address'] == '0x123'
        assert params['page'] == 1
        assert params['offset'] == 100
        assert params['module'] == 'account'
        assert params['action'] == 'addresstokenbalance'

    def test_nft_portfolio_param_mapping(self):
        """Test param mapping for NFT portfolio."""
        spec = EtherscanV2.SPECS[Method.ACCOUNT_NFT_PORTFOLIO]
        params = spec.map_params(address='0x456', page=2, offset=50)
        assert params['address'] == '0x456'
        assert params['page'] == 2
        assert params['offset'] == 50
        assert params['module'] == 'account'
        assert params['action'] == 'addresstokennftinventory'

    def test_contract_verify_param_mapping(self):
        """Test param mapping for contract verification."""
        spec = EtherscanV2.SPECS[Method.CONTRACT_VERIFY]
        params = spec.map_params(
            contract_address='0xabc',
            source_code='pragma solidity ^0.8.0;',
            code_format='solidity-single-file',
            contract_name='MyContract',
            compiler_version='v0.8.0+commit.c7dfd78e',
            optimization_used='1',
            runs='200',
        )
        assert params['contractaddress'] == '0xabc'
        assert params['sourceCode'] == 'pragma solidity ^0.8.0;'
        assert params['codeformat'] == 'solidity-single-file'
        assert params['contractname'] == 'MyContract'
        assert params['compilerversion'] == 'v0.8.0+commit.c7dfd78e'
        assert params['optimizationUsed'] == '1'
        assert params['runs'] == '200'

    def test_contract_verify_status_param_mapping(self):
        """Test param mapping for verification status check."""
        spec = EtherscanV2.SPECS[Method.CONTRACT_VERIFY_STATUS]
        params = spec.map_params(guid='abc123-guid-string')
        assert params['guid'] == 'abc123-guid-string'
        assert params['module'] == 'contract'
        assert params['action'] == 'checkverifystatus'


class TestMethodStringRepresentation:
    """Test Method enum string representation."""

    def test_account_token_portfolio_str(self):
        """ACCOUNT_TOKEN_PORTFOLIO should have readable string."""
        assert str(Method.ACCOUNT_TOKEN_PORTFOLIO) == 'Account Token Portfolio'

    def test_account_nft_portfolio_str(self):
        """ACCOUNT_NFT_PORTFOLIO should have readable string."""
        assert str(Method.ACCOUNT_NFT_PORTFOLIO) == 'Account Nft Portfolio'

    def test_contract_verify_str(self):
        """CONTRACT_VERIFY should have readable string."""
        assert str(Method.CONTRACT_VERIFY) == 'Contract Verify'

    def test_contract_verify_status_str(self):
        """CONTRACT_VERIFY_STATUS should have readable string."""
        assert str(Method.CONTRACT_VERIFY_STATUS) == 'Contract Verify Status'
