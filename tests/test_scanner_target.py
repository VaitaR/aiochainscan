"""Unit tests for scanner target resolution (chain_registry.resolve_scanner_target)."""

from dataclasses import FrozenInstanceError

import pytest

from aiochainscan.chain_registry import (
    ScannerTarget,
    get_scanner_network_name,
    resolve_scanner_target,
)
from aiochainscan.config import ConfigurationManager
from aiochainscan.scanners.blockscout_v1 import BlockScoutV1

KEY_ENV_VARS = (
    'ETHERSCAN_KEY',
    'ETH_KEY',
    'ETH_API_KEY',
    'SCANNER_ETH_KEY',
    'API_KEY_ETH',
)


@pytest.fixture(autouse=True)
def _reset_config_singleton():
    """Isolate each test from both configuration-manager access paths."""
    ConfigurationManager.reset_instance()
    yield
    ConfigurationManager.reset_instance()


@pytest.fixture
def clean_key_env(monkeypatch: pytest.MonkeyPatch, tmp_path: object):
    """Fresh config dir and no API key environment variables."""
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    for var in KEY_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


class TestScannerTarget:
    """Test the ScannerTarget frozen dataclass."""

    def test_is_frozen(self):
        target = resolve_scanner_target('blockscout_v2', 'ethereum')
        assert isinstance(target, ScannerTarget)
        with pytest.raises(FrozenInstanceError):
            target.scanner_name = 'etherscan'  # type: ignore[misc]


class TestBlockscoutV2Rename:
    """blockscout_v2 is a public alias for ('blockscout', 'v2')."""

    def test_rename_and_keyless(self):
        target = resolve_scanner_target('blockscout_v2', 'ethereum')
        assert target.scanner_name == 'blockscout'
        assert target.scanner_version == 'v2'
        assert target.api_kind == 'blockscout_eth'
        assert target.api_key == ''
        assert target.network == 'ethereum'
        assert target.chain_id == 1

    def test_rename_forces_v2_even_with_explicit_version(self):
        target = resolve_scanner_target('blockscout_v2', 'ethereum', scanner_version='v1')
        assert target.scanner_name == 'blockscout'
        assert target.scanner_version == 'v2'

    def test_int_network_resolves_canonical_name(self):
        target = resolve_scanner_target('blockscout_v2', 8453)
        assert target.network == 'base'
        assert target.chain_id == 8453


class TestAliasResolution:
    """Network alias handling and canonical network naming."""

    def test_blockscout_v1_ethereum(self):
        target = resolve_scanner_target('blockscout', 'ethereum')
        assert target.scanner_name == 'blockscout'
        assert target.scanner_version == 'v1'
        assert target.api_kind == 'blockscout_eth'
        assert target.api_key == ''  # BlockScout needs no key
        assert target.network == 'ethereum'

    def test_blockscout_main_alias_uses_ethereum_profile(self):
        target = resolve_scanner_target('blockscout', 'main')
        assert target.api_kind == 'blockscout_eth'
        assert target.api_key == ''
        assert target.network == 'main'

    def test_blockscout_network_specific_api_kind(self):
        target = resolve_scanner_target('blockscout', 'polygon')
        assert target.api_kind == 'blockscout_polygon'
        assert target.network == 'polygon'
        assert target.chain_id == 137

    def test_blockscout_bnb_alias_quirk(self):
        # Preserved behavior: 'bnb' resolves to chain 56 but BlockScout's config
        # validation only knows the 'bsc' network name, so it raises.
        with pytest.raises(ValueError, match='Network "bnb" not supported by BlockScout BSC'):
            resolve_scanner_target('blockscout', 'bnb')

    def test_etherscan_preserves_network_name(self):
        target = resolve_scanner_target('etherscan', 'ethereum', api_key='k')
        assert target.network == 'ethereum'
        assert target.chain_id == 1

    def test_etherscan_accepts_chain_alias(self):
        target = resolve_scanner_target('etherscan', 'eth', api_key='k')
        assert target.network == 'eth'  # string input preserved
        assert target.chain_id == 1

    def test_default_version_v2_for_etherscan_v1_otherwise(self):
        assert resolve_scanner_target('etherscan', 1, api_key='k').scanner_version == 'v2'
        assert resolve_scanner_target('blockscout', 1).scanner_version == 'v1'

    def test_explicit_version_override(self):
        target = resolve_scanner_target('etherscan', 'ethereum', api_key='k', scanner_version='v9')
        assert target.scanner_version == 'v9'


class TestApiKindDefaulting:
    """api_kind mapping for UrlBuilder."""

    def test_etherscan_api_kind(self):
        target = resolve_scanner_target('etherscan', 'ethereum', api_key='k')
        assert target.api_kind == 'eth'

    def test_unknown_scanner_falls_back_to_own_name(self):
        # 'bsc' exists as a config id but not as a scanner api_kind mapping
        target = resolve_scanner_target('bsc', 'bnb', api_key='k')
        assert target.api_kind == 'bsc'
        assert target.scanner_version == 'v1'


class TestApiKeyResolution:
    """API key defaults from the configuration manager and explicit overrides."""

    def test_explicit_key_skips_config_lookup(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('ETHERSCAN_KEY', 'envkey123456')
        target = resolve_scanner_target('etherscan', 'ethereum', api_key='explicit')
        assert target.api_key == 'explicit'

    def test_default_key_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('ETHERSCAN_KEY', 'envkey123456')
        target = resolve_scanner_target('etherscan', 'ethereum')
        assert target.api_key == 'envkey123456'

    def test_blockscout_v2_ignores_explicit_key(self):
        # BlockScout V2 is keyless by definition
        target = resolve_scanner_target('blockscout_v2', 'ethereum', api_key='ignored')
        assert target.api_key == ''

    def test_missing_key_raises(self, clean_key_env):  # noqa: ARG001
        with pytest.raises(ValueError, match='API key required for Etherscan'):
            resolve_scanner_target('etherscan', 'ethereum')


class TestPhantomScannerRejection:
    """'moralis'/'routscan' entries were removed: they must raise the honest
    unknown-scanner error instead of resolving into a missing scanner."""

    @pytest.mark.parametrize('phantom', ['moralis', 'routscan', 'nonexistent'])
    def test_unknown_scanner_raises(self, phantom: str):
        with pytest.raises(ValueError, match=f'Unknown scanner "{phantom}"'):
            resolve_scanner_target(phantom, 'ethereum')


class TestNodeRealResolution:
    """from_config('nodereal', 'bsc') resolution wiring."""

    def test_nodereal_bsc_mainnet(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('NODEREAL_KEY', 'nrkey123')
        target = resolve_scanner_target('nodereal', 'bsc')
        assert target.scanner_name == 'nodereal'
        assert target.scanner_version == 'v1'
        assert target.network == 'bsc'
        assert target.api_kind == 'nodereal'
        assert target.api_key == 'nrkey123'
        assert target.chain_id == 56

    def test_nodereal_bnb_alias_maps_config_lookup(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('NODEREAL_KEY', 'nrkey123')
        target = resolve_scanner_target('nodereal', 'bnb')
        assert target.network == 'bnb'
        assert target.chain_id == 56
        assert target.api_key == 'nrkey123'  # alias mapped to 'bsc' for config lookup

    def test_nodereal_testnet(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('NODEREAL_API_KEY', 'nrkey456')
        target = resolve_scanner_target('nodereal', 'bsc-testnet')
        assert target.network == 'bsc-testnet'
        assert target.chain_id == 97
        assert target.api_key == 'nrkey456'

    def test_nodereal_missing_key_raises(self, clean_key_env):  # noqa: ARG001
        with pytest.raises(ValueError, match='API key required for NodeReal'):
            resolve_scanner_target('nodereal', 'bsc')


class TestErrorBehavior:
    """Exact error surface for bad networks."""

    def test_unknown_chain_raises(self):
        with pytest.raises(ValueError, match='Unknown chain'):
            resolve_scanner_target('etherscan', 'not-a-chain', api_key='k')

    def test_blockscout_unsupported_network_raises_unknown_scanner(self):
        with pytest.raises(ValueError, match='Unknown scanner "blockscout_fantom"'):
            resolve_scanner_target('blockscout', 'fantom')

    def test_etherscan_unsupported_network_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('ETHERSCAN_KEY', 'envkey123456')
        with pytest.raises(ValueError, match='not supported by Etherscan'):
            resolve_scanner_target('etherscan', 'holesky')


class TestFromConfigIntegration:
    """from_config stays a thin resolve + construct over resolve_scanner_target."""

    async def test_from_config_blockscout_v2(self):
        from aiochainscan import ChainscanClient

        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
        try:
            assert client.scanner_name == 'blockscout'
            assert client.scanner_version == 'v2'
            assert client.api_kind == 'blockscout_eth'
            assert client.network == 'ethereum'
            assert client.api_key == ''
            assert client.chain_id == 1
        finally:
            await client.close()

    async def test_from_config_blockscout_main_alias(self):
        from aiochainscan import ChainscanClient

        client = ChainscanClient.from_config('blockscout', 'main')
        try:
            assert client.api_kind == 'blockscout_eth'
            assert client._scanner.network == 'eth'
            assert client._scanner.instance_domain == 'eth.blockscout.com'
        finally:
            await client.close()

    @pytest.mark.parametrize('network', sorted(BlockScoutV1.supported_networks))
    async def test_from_config_all_blockscout_v1_networks(self, network: str):
        from aiochainscan import ChainscanClient

        client = ChainscanClient.from_config('blockscout', network)
        try:
            assert client.api_key == ''
            assert client.api_kind == f'blockscout_{network}'
            assert client._scanner.instance_domain == BlockScoutV1.NETWORK_INSTANCES[network]
        finally:
            await client.close()

    def test_from_config_unknown_scanner_raises(self):
        from aiochainscan import ChainscanClient

        with pytest.raises(ValueError, match='Unknown scanner "moralis"'):
            ChainscanClient.from_config('moralis', 'ethereum')


class TestScannerNetworkName:
    """Scanner-specific network name mapping."""

    @pytest.mark.parametrize(
        ('scanner', 'version', 'network', 'expected'),
        [
            ('blockscout', 'v1', 'ethereum', 'eth'),
            ('blockscout', 'v1', 'main', 'eth'),
            ('blockscout', 'v1', 'polygon', 'polygon'),
            ('blockscout', 'v2', 'main', 'ethereum'),
            ('blockscout', 'v2', 'ethereum', 'ethereum'),
            ('etherscan', 'v2', 'ethereum', 'main'),
            ('etherscan', 'v2', 'polygon', 'polygon'),
        ],
    )
    def test_mapping(self, scanner: str, version: str, network: str, expected: str) -> None:
        assert get_scanner_network_name(scanner, version, network) == expected
