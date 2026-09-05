"""Registry consistency sweep — the mechanical cross-product guard.

Every bug this suite pins was found by hand in the 2026-09-05 audit round 2,
and each one is a case of two registry views disagreeing:

- **H2**: ``etherscan`` declared 13 network aliases, but the six short ones
  ('eth', 'bnb', 'binance', 'matic', 'arb', 'op') resolved in the registry and
  then died in ``Scanner.__init__`` — ``url_network`` was canonicalized while
  ``scanner_network`` carried the raw spelling the scanner's
  ``supported_networks`` rejects.
- **M4**: two of 32 ``moralis_hex`` values did not round-trip to their chain
  id (arbitrum-sepolia carried a corrupted copy of sepolia's hex; mode was off
  by one).
- **M6**: ``blockscout_v2`` reported currency 'ETH' for every non-Ethereum
  network because its record pinned the ``blockscout_eth`` kind, while v1
  derived the kind per network.
- **M7**: four ``STANDARD_CHAINS`` entries advertised ``blockscout_instance``
  hosts no scanner could construct against (goerli, fantom, blast, mode).

The sweep derives each scanner's declared surface from the registry tables
themselves (scanner records, class ``supported_networks``,
``BLOCKSCOUT_SCANNER_NETWORKS``, ``config_ids_by_network``, instance hosts,
``URL_BUILDER_CHAIN_IDS``, ``STANDARD_CHAINS`` names and aliases) and asserts
the views agree — construction included, since resolution alone does not reach
``Scanner.__init__``, which is where H2 fired.

Everything here is offline: constructions pass dummy API keys explicitly (so
no credential lookup varies with the machine), and no request is ever sent —
``ChainscanClient`` construction wires its collaborators lazily.
"""

from collections.abc import Iterator
from typing import Any

import pytest

from aiochainscan import ChainscanClient
from aiochainscan.chain_registry import (
    BLOCKSCOUT_INSTANCE_HOSTS,
    BLOCKSCOUT_SCANNER_NETWORKS,
    DEFAULT_SCANNER_VERSIONS,
    SCANNER_RECORDS,
    STANDARD_CHAINS,
    URL_BUILDER_CHAIN_IDS,
    resolve_chain_id,
    resolve_scanner_target,
)
from aiochainscan.config import ConfigurationManager
from aiochainscan.scanners import get_scanner_class

KEY_ENV_VARS = (
    'ETHERSCAN_KEY',
    'ETH_KEY',
    'ETH_API_KEY',
    'SCANNER_ETH_KEY',
    'API_KEY_ETH',
    'NODEREAL_KEY',
    'NODEREAL_API_KEY',
)

#: Key-requiring scanners get an explicit dummy key so construction never
#: depends on the machine's credential state.
DUMMY_KEYS: dict[str, str] = {
    'etherscan': 'k' * 34,
    'nodereal': 'nr' * 25,
}


@pytest.fixture(autouse=True)
def _offline_hermetic_env(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> Iterator[None]:
    """No machine credentials, no home config, fresh config-manager singleton."""
    ConfigurationManager.reset_instance()
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    for var in KEY_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    yield
    ConfigurationManager.reset_instance()


def _scanner_class(scanner: str) -> type:
    """The scanner class a registry-declared name resolves to."""
    record = SCANNER_RECORDS[scanner]
    version = DEFAULT_SCANNER_VERSIONS.get(scanner, 'v1')
    name = scanner if scanner == record.kind else record.kind
    return get_scanner_class(name, version)


def _chain_spellings(chain_id: int) -> set[str]:
    """Every registry spelling of one chain: its canonical name plus aliases."""
    info = STANDARD_CHAINS[chain_id]
    return {str(info['name']), *map(str, info['aliases'])}


def _declared_spellings(scanner: str) -> set[str]:
    """Network spellings the scanner declares anywhere in the registry.

    Union of: the scanner record's alias keys AND values, the record's config
    networks, the BlockScout host tables (blockscout family only), the shared
    BlockScout scanner networks, and the scanner class's own
    ``supported_networks``. (The UrlBuilder chain-id table is a separate
    dimension: its names are per-kind UrlBuilder dialect, not scanner-declared
    networks — it is cross-checked in ``TestUrlBuilderChainIdCrossCheck``.)
    """
    record = SCANNER_RECORDS[scanner]
    declared: set[str] = set(record.network_aliases) | set(record.network_aliases.values())
    declared |= set(record.supported_networks or ())
    declared |= set(record.config_ids_by_network)
    declared |= set(record.instance_hosts)
    if record.kind == 'blockscout':
        declared |= set(BLOCKSCOUT_SCANNER_NETWORKS)
    declared |= {str(net) for net in _scanner_class(scanner).supported_networks}
    return declared


def _declared_chains(scanner: str) -> dict[int, set[str]]:
    """chain id → resolvable declared spellings, for one scanner.

    Every spelling that reaches construction must be a registry chain; the one
    intentional non-chain alias in the tables ('zksync', declared dropped) is
    tolerated here and must never surface in a scanner's class set.
    """
    chains: dict[int, set[str]] = {}
    for spelling in _declared_spellings(scanner):
        try:
            chain_id = resolve_chain_id(spelling)
        except ValueError:
            assert spelling == 'zksync', (
                f'{scanner}: declared network {spelling!r} is neither a registry '
                f'chain nor a declared-dropped BlockScout alias'
            )
            continue
        chains.setdefault(chain_id, set()).add(spelling)
    return chains


def _construct(scanner: str, network: str | int) -> ChainscanClient:
    """Build a client offline: dummy key, no request, registry resolution only."""
    kwargs: dict[str, Any] = {}
    key = DUMMY_KEYS.get(scanner)
    if key is not None:
        kwargs['api_key'] = key
    return ChainscanClient.from_config(scanner, network, **kwargs)


def _resolve_target(scanner: str, network: str | int) -> Any:
    kwargs: dict[str, Any] = {}
    key = DUMMY_KEYS.get(scanner)
    if key is not None:
        kwargs['api_key'] = key
    return resolve_scanner_target(scanner, network, **kwargs)


def _is_resolvable(network: str) -> bool:
    try:
        resolve_chain_id(network)
    except ValueError:
        return False
    return True


def _url_builder_expected_chain_id(kind: str, network: str) -> int | None:
    """The registry chain id a UrlBuilder (kind, network) row must carry, or
    ``None`` where the row's name is purely per-kind dialect.

    Two row families have a global reading: ``('K', 'main')`` is the mainnet
    of the chain K is named after, and the ``('eth', …)`` rows name ethereum's
    own networks ('main'/'goerli'/'sepolia'/'holesky'). Everything else —
    'goerli' under 'base', 'nova', 'mumbai', 'chiado', V1-era 'test' — is
    dialect with no global chain spelling.
    """
    if network == 'main' and _is_resolvable(kind):
        return resolve_chain_id(kind)
    if kind == 'eth' and _is_resolvable(network):
        return resolve_chain_id(network)
    return None


class TestDeclaredSpellingsResolve:
    """Every network any registry view declares for a scanner must be a chain
    the registry can resolve. A declared-but-unresolvable name is the round-1
    'zksync' bug shape: resolvable in one table, dead in the next."""

    def test_declared_chains_are_non_empty_per_scanner(self) -> None:
        for scanner in SCANNER_RECORDS:
            chains = _declared_chains(scanner)
            assert chains, f'{scanner} declares no resolvable network anywhere'

    def test_class_supported_networks_all_resolve(self) -> None:
        for scanner in SCANNER_RECORDS:
            for network in _scanner_class(scanner).supported_networks:
                assert _is_resolvable(
                    str(network)
                ), f'{scanner}: supported network {network!r} does not resolve'

    def test_all_scanners_are_swept(self) -> None:
        # Public-surface pin: a newly registered scanner must join the sweep
        # (and its declared surface with it), not slip past the guard.
        assert set(SCANNER_RECORDS) == {'etherscan', 'blockscout', 'blockscout_v2', 'nodereal'}


class TestConstructionSweep:
    """THE H2 guard: every scanner x every spelling of every chain it declares
    must construct — string AND int form. Resolution alone cannot catch this
    class of bug (H2 resolved fine and died in ``Scanner.__init__``)."""

    @pytest.mark.parametrize('scanner', sorted(SCANNER_RECORDS))
    async def test_every_declared_spelling_constructs(self, scanner: str) -> None:
        for chain_id, spellings in sorted(_declared_chains(scanner).items()):
            for spelling in sorted(spellings):
                client = _construct(scanner, spelling)
                try:
                    assert (
                        client.chain_id == chain_id
                    ), f'{scanner}/{spelling}: chain_id {client.chain_id} != {chain_id}'
                    # The scanner accepted its dialect name — the check H2 failed.
                    assert client._scanner.network in client._scanner.supported_networks
                finally:
                    await client.close()

    @pytest.mark.parametrize('scanner', sorted(SCANNER_RECORDS))
    async def test_every_declared_chain_constructs_in_int_form(self, scanner: str) -> None:
        for chain_id in sorted(_declared_chains(scanner)):
            client = _construct(scanner, chain_id)
            try:
                assert client.chain_id == chain_id
            finally:
                await client.close()

    async def test_sweep_exercises_the_h2_repro_set(self) -> None:
        # Guard the guard: the aliases that failed before the fix must stay in
        # the swept surface, not silently shrink out of the tables.
        etherscan_chains = _declared_chains('etherscan')
        for alias in ('eth', 'bnb', 'binance', 'matic', 'arb', 'op'):
            chain_id = resolve_chain_id(alias)
            assert alias in etherscan_chains[chain_id], f'{alias} left the etherscan surface'


class TestSpellingIndependence:
    """One chain resolves to ONE construction target per scanner however it is
    spelled — the canonicalization contract that makes the construction sweep
    sound. (The client-facing ``network`` property deliberately keeps the
    caller's spelling; everything the scanner stack consumes must not.)"""

    @pytest.mark.parametrize('scanner', sorted(SCANNER_RECORDS))
    def test_resolver_fields_are_spelling_invariant(self, scanner: str) -> None:
        for chain_id, spellings in sorted(_declared_chains(scanner).items()):
            targets = [_resolve_target(scanner, spelling) for spelling in sorted(spellings)]
            for field in ('api_kind', 'url_network', 'scanner_network', 'chain_id'):
                values = {getattr(target, field) for target in targets}
                assert len(values) == 1, (
                    f'{scanner}: chain {chain_id} resolves field {field!r} to {values} '
                    f'depending on spelling'
                )


class TestMoralisHexRoundTrip:
    """M4 guard: every STANDARD_CHAINS entry's moralis_hex must parse back to
    its own chain id. Two of 32 entries used to fail (arbitrum-sepolia carried
    sepolia's hex with a digit flipped; mode was off by one)."""

    @pytest.mark.parametrize('chain_id', sorted(STANDARD_CHAINS))
    def test_moralis_hex_round_trips(self, chain_id: int) -> None:
        info = STANDARD_CHAINS[chain_id]
        assert 'moralis_hex' in info, f'chain {chain_id} ({info["name"]}) has no moralis_hex'
        hex_value = info['moralis_hex']
        assert isinstance(hex_value, str) and hex_value.startswith('0x')
        assert int(hex_value, 16) == chain_id, (
            f'chain {chain_id} ({info["name"]}): moralis_hex {hex_value!r} '
            f'parses to {int(hex_value, 16)}'
        )


class TestBlockscoutInstanceAdvertisements:
    """M7 guard: a chain advertising a ``blockscout_instance`` must advertise
    a host the registry actually maps AND the blockscout v1 leg must construct
    against exactly that host. Four defunct hosts (goerli, fantom, blast,
    mode) used to be advertised to no scanner at all."""

    def test_advertised_hosts_are_registry_hosts(self) -> None:
        advertised = {
            info['blockscout_instance']
            for info in STANDARD_CHAINS.values()
            if 'blockscout_instance' in info
        }
        assert advertised, 'no chain advertises a blockscout instance — table drifted?'
        unmapped = advertised - set(BLOCKSCOUT_INSTANCE_HOSTS.values())
        assert (
            not unmapped
        ), f'STANDARD_CHAINS advertises hosts no scanner maps: {sorted(unmapped)}'

    async def test_advertised_chains_construct_against_their_host(self) -> None:
        for chain_id, info in sorted(STANDARD_CHAINS.items()):
            if 'blockscout_instance' not in info:
                continue
            client = _construct('blockscout', chain_id)
            try:
                assert client._scanner.instance_domain == info['blockscout_instance']
            finally:
                await client.close()

    def test_get_blockscout_instance_is_honest_for_unadvertised_chains(self) -> None:
        from aiochainscan.chain_registry import get_blockscout_instance

        for chain_id, info in STANDARD_CHAINS.items():
            if 'blockscout_instance' in info:
                assert get_blockscout_instance(chain_id) == info['blockscout_instance']
                continue
            with pytest.raises(ValueError, match='BlockScout not available'):
                get_blockscout_instance(chain_id)


class TestBlockscoutCurrencyParity:
    """M6 guard: for every chain both BlockScout legs serve, the v2 currency
    must equal the v1 currency (v1 derives its UrlBuilder kind per network;
    v2 used to pin the Ethereum kind and answer 'ETH' everywhere). Requests
    are unaffected — v2 builds URLs from its own base table — so the
    profile's currency is the only observable."""

    async def test_v2_currency_equals_v1_currency_per_chain(self) -> None:
        v2_chains = _declared_chains('blockscout_v2')
        checked = 0
        for chain_id in sorted(_declared_chains('blockscout')):
            if chain_id not in v2_chains:
                continue
            client_v1 = _construct('blockscout', chain_id)
            client_v2 = _construct('blockscout_v2', chain_id)
            try:
                assert client_v1.currency == client_v2.currency, (
                    f'chain {chain_id}: v1 currency {client_v1.currency!r} != '
                    f'v2 currency {client_v2.currency!r}'
                )
                checked += 1
            finally:
                await client_v1.close()
                await client_v2.close()
        # Guard the guard: every BlockScout instance chain must be covered —
        # the networks whose currency used to be wrong (bsc, polygon, gnosis)
        # stay in the swept surface.
        assert checked >= 10

    async def test_formerly_wrong_currencies_pin_their_symbols(self) -> None:
        for network, symbol in (('bsc', 'BNB'), ('polygon', 'MATIC'), ('gnosis', 'xDAI')):
            client_v1 = _construct('blockscout', network)
            client_v2 = _construct('blockscout_v2', network)
            try:
                assert (
                    client_v2.currency == symbol
                ), f'{network}: v2 currency {client_v2.currency!r} != {symbol!r}'
                assert client_v1.currency == client_v2.currency
            finally:
                await client_v1.close()
                await client_v2.close()


class TestUrlBuilderChainIdCrossCheck:
    """The UrlBuilder chain-id table must agree with the chain registry where
    both speak unambiguously. UrlBuilder network names are per-kind dialect:
    'main' means *that kind's* mainnet and 'goerli' under the 'base' kind is
    base-goerli, not ethereum's — so only two row families have a global
    chain-spelling reading and only those are cross-checked here."""

    @pytest.mark.parametrize(
        ('kind', 'network'),
        sorted(
            (kind, net)
            for (kind, net) in URL_BUILDER_CHAIN_IDS
            if _url_builder_expected_chain_id(kind, net) is not None
        ),
    )
    def test_chain_id_matches_registry(self, kind: str, network: str) -> None:
        expected = _url_builder_expected_chain_id(kind, network)
        assert expected is not None  # for the type checker
        assert int(URL_BUILDER_CHAIN_IDS[(kind, network)]) == expected

    def test_cross_check_is_not_vacuous(self) -> None:
        # Guard the guard: the two unambiguous row families must exist.
        mains = [kind for (kind, net) in URL_BUILDER_CHAIN_IDS if net == 'main']
        eth_rows = [net for (kind, net) in URL_BUILDER_CHAIN_IDS if kind == 'eth']
        assert len(mains) >= 10
        assert {'main', 'goerli', 'sepolia', 'holesky'} <= set(eth_rows)

    async def test_etherscan_serves_its_url_builder_chains(self) -> None:
        etherscan_rows = {net for (kind, net) in URL_BUILDER_CHAIN_IDS if kind == 'eth'}
        for network in sorted(etherscan_rows):
            if not _is_resolvable(network):
                continue  # config-dialect name of the v1 family, not a chain
            client = _construct('etherscan', network)
            try:
                assert client.chain_id == resolve_chain_id(network)
            finally:
                await client.close()
