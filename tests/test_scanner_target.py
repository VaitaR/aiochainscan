"""Unit tests for scanner target resolution (chain_registry.resolve_scanner_target)."""

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

import aiochainscan.chain_registry as chain_registry
from aiochainscan.chain_registry import (
    ScannerTarget,
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
    # NodeReal resolves its key through the generic SUGGESTED-NAME ladder
    # (NODEREAL_KEY / NODEREAL_API_KEY), so a shell export must be cleared too.
    'NODEREAL_KEY',
    'NODEREAL_API_KEY',
)


@pytest.fixture(autouse=True)
def _reset_config_singleton():
    """Isolate each test from both configuration-manager access paths."""
    ConfigurationManager.reset_instance()
    yield
    ConfigurationManager.reset_instance()


@pytest.fixture
def clean_key_env(monkeypatch: pytest.MonkeyPatch, tmp_path: object):
    """Fresh config dir, no API key environment variables, no home credentials.

    ``ConfigurationManager`` reads ``~/.aiochainscan/.env`` for every cwd, so
    isolating cwd and ``os.environ`` is not enough: a developer with a real key
    there turns every "missing key raises" assertion green-by-accident into a
    failure. ``Path.home()`` resolves ``$HOME``, so repointing it removes that
    third source.
    """
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
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


class TestSingleResolutionSeam:
    """ScannerTarget is the only construction seam: resolution runs exactly
    once per client, at ``resolve_scanner_target``, for every public form."""

    @pytest.fixture
    def counters(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
        """Count every resolution attempt the client path could make."""
        counts = {'target': 0, 'chain_id': 0}
        real_target = chain_registry.resolve_scanner_target
        real_chain = chain_registry.resolve_chain_id

        def counting_target(*args: Any, **kwargs: Any) -> ScannerTarget:
            counts['target'] += 1
            return real_target(*args, **kwargs)

        def counting_chain(value: str | int) -> int:
            counts['chain_id'] += 1
            return real_chain(value)

        # The client-module binding (used by from_config and the keyword
        # constructor), the registry-internal binding (used by the resolver
        # itself) and the Scanner fallback binding are all intercepted.
        monkeypatch.setattr('aiochainscan.core.client.resolve_scanner_target', counting_target)
        monkeypatch.setattr(chain_registry, 'resolve_chain_id', counting_chain)
        monkeypatch.setattr('aiochainscan.scanners.base.resolve_chain_id', counting_chain)
        return counts

    async def test_from_config_resolves_exactly_once(self, counters: dict[str, int]) -> None:
        from aiochainscan import ChainscanClient

        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
        try:
            assert counters['target'] == 1
            # registry resolver: 1; client re-derivation: 0; scanner fallback: 0
            assert counters['chain_id'] == 1
        finally:
            await client.close()

    async def test_chain_provider_form_resolves_exactly_once(
        self, counters: dict[str, int]
    ) -> None:
        from aiochainscan import ChainscanClient

        client = ChainscanClient(chain='ethereum', provider='etherscan', api_key='k')
        try:
            assert counters['target'] == 1
            assert counters['chain_id'] == 1
        finally:
            await client.close()

    async def test_direct_target_constructs_without_any_resolution(
        self, counters: dict[str, int]
    ) -> None:
        from aiochainscan import ChainscanClient

        target = chain_registry.resolve_scanner_target('blockscout_v2', 'ethereum')
        counters['target'] = 0
        counters['chain_id'] = 0

        client = ChainscanClient(target)
        try:
            # The client trusts the target: no resolution, no re-derivation.
            assert counters['target'] == 0
            assert counters['chain_id'] == 0
            assert client.scanner_name == 'blockscout'
            assert client.chain_id == 1
        finally:
            await client.close()

    async def test_url_network_resolved_once_by_registry(self, counters: dict[str, int]) -> None:
        from aiochainscan import ChainscanClient

        # 'ethereum' must arrive at the UrlBuilder as its dialect name 'main',
        # resolved by the registry — never re-mapped by the client.
        client = ChainscanClient.from_config('etherscan', 'ethereum', api_key='k')
        try:
            assert client._url_builder._network == 'main'
            assert counters['chain_id'] == 1
        finally:
            await client.close()


class TestScannerNetwork:
    """Scanner-dialect network naming is resolved once by the registry and
    carried on ``ScannerTarget.scanner_network`` — the client consumes the
    field and never re-derives it."""

    @pytest.mark.parametrize(
        ('scanner', 'network', 'expected'),
        [
            ('blockscout', 'ethereum', 'eth'),
            ('blockscout', 'main', 'eth'),
            ('blockscout', 'polygon', 'polygon'),
            ('blockscout_v2', 'main', 'ethereum'),
            ('blockscout_v2', 'ethereum', 'ethereum'),
            ('etherscan', 'ethereum', 'main'),
            ('etherscan', 'polygon', 'polygon'),
        ],
    )
    def test_mapping(self, scanner: str, network: str, expected: str) -> None:
        kwargs: dict[str, Any] = {'api_key': 'k'} if scanner == 'etherscan' else {}
        target = resolve_scanner_target(scanner, network, **kwargs)
        assert target.scanner_network == expected

    def test_custom_base_url_carries_the_custom_label(self) -> None:
        target = resolve_scanner_target('blockscout', 'https://bsc.example')
        assert target.scanner_network == 'custom'
        assert target.network == 'custom'


class TestDerivedInstanceTopology:
    """The BlockScout satellite tables derive from the one 'blockscout'
    scanner record, and the silent failure modes of the hand-maintained era
    stay impossible: no instance alias may vanish from ``BLOCKSCOUT_HOSTS``
    without a declaration in ``DROPPED_INSTANCE_ALIASES``, and no derived
    host id may lack a display name (the configuration manager would die on
    a bare ``KeyError``). Mirrors chain_registry's import-time validation so
    the contract is pinned by the suite as well, not only by module import.
    """

    def test_every_instance_alias_is_derived_or_declared_dropped(self) -> None:
        hosts = chain_registry.BLOCKSCOUT_HOSTS
        for alias, host in chain_registry.BLOCKSCOUT_INSTANCE_HOSTS.items():
            # 'ethereum' reaches BLOCKSCOUT_HOSTS through its shared host
            # (the 'eth' entry) — an alias is covered when its instance is
            # reachable under its own key OR under another alias's key.
            derived = f'blockscout_{alias}' in hosts or host in hosts.values()
            assert derived or alias in chain_registry.DROPPED_INSTANCE_ALIASES, (
                f'instance alias {alias!r} ({host}) is neither derived into '
                f'BLOCKSCOUT_HOSTS nor declared in DROPPED_INSTANCE_ALIASES'
            )

    def test_dropped_aliases_are_real_and_still_dropped(self) -> None:
        hosts = chain_registry.BLOCKSCOUT_HOSTS
        instances = chain_registry.BLOCKSCOUT_INSTANCE_HOSTS
        for alias in chain_registry.DROPPED_INSTANCE_ALIASES:
            assert alias in instances, f'dropped alias {alias!r} is not an instance alias'
            assert f'blockscout_{alias}' not in hosts, (
                f'dropped alias {alias!r} derives its own host id — remove it '
                f'from DROPPED_INSTANCE_ALIASES'
            )
            assert instances[alias] not in hosts.values(), (
                f'dropped alias {alias!r} shares a derived host — remove it '
                f'from DROPPED_INSTANCE_ALIASES'
            )

    def test_display_names_cover_exactly_the_derived_host_ids(self) -> None:
        names = chain_registry.BLOCKSCOUT_DISPLAY_NAMES
        for host_id in chain_registry.BLOCKSCOUT_HOSTS:
            assert host_id in names, f'derived host id {host_id!r} has no display name'
        assert not set(names) - set(chain_registry.BLOCKSCOUT_HOSTS), (
            'display names declared for non-derived host ids: '
            f'{sorted(set(names) - set(chain_registry.BLOCKSCOUT_HOSTS))}'
        )

    def test_zksync_stays_declared_dropped(self) -> None:
        # Public-surface pin: today's drop keeps today's behaviour — declared,
        # not resurrected and not silently extended.
        assert frozenset({'zksync'}) == chain_registry.DROPPED_INSTANCE_ALIASES
        assert 'blockscout_zksync' not in chain_registry.BLOCKSCOUT_HOSTS
