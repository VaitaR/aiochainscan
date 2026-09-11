"""Opt-in registry sync: alias rule, additive registration, live agreement."""

from __future__ import annotations

from typing import Any

import pytest

from aiochainscan import ChainscanClient, chain_registry
from aiochainscan.adapters.memory_cache import InMemoryCache
from aiochainscan.registry_sync import chainlist_alias, sync_etherscan_chains


class _StubTransport:
    """Serves one canned chainlist payload."""

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.entries = entries
        self.calls = 0

    async def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {'result': self.entries}


@pytest.fixture
def registry_snapshot():
    """Restore every table the sync mutates, so tests cannot leak into each other."""
    chains = dict(chain_registry.STANDARD_CHAINS)
    aliases = dict(chain_registry.SCANNER_NETWORK_ALIASES['etherscan'])
    networks = set(chain_registry.ETHERSCAN_SCANNER_NETWORKS)
    yield
    chain_registry.STANDARD_CHAINS.clear()
    chain_registry.STANDARD_CHAINS.update(chains)
    chain_registry.SCANNER_NETWORK_ALIASES['etherscan'].clear()
    chain_registry.SCANNER_NETWORK_ALIASES['etherscan'].update(aliases)
    chain_registry.ETHERSCAN_SCANNER_NETWORKS.clear()
    chain_registry.ETHERSCAN_SCANNER_NETWORKS.update(networks)


class TestChainlistAlias:
    @pytest.mark.parametrize(
        ('chain_name', 'expected'),
        [
            ('Ethereum Mainnet', 'ethereum'),
            ('Celo Sepolia Testnet', 'celo-sepolia'),
            ('BitTorrent Chain Mainnet', 'bittorrent-chain'),
            ('OP Sepolia Testnet', 'op-sepolia'),
            ('Hoodi Testnet', 'hoodi'),  # the role word is all there is left
        ],
    )
    def test_role_suffix_is_dropped(self, chain_name: str, expected: str) -> None:
        assert chainlist_alias(chain_name) == expected

    def test_static_table_spells_chains_the_same_way(self) -> None:
        # The static entries were generated with this rule; a caller's network
        # string must not depend on whether the sync ran.
        for chain_name, chain_id in [('Mantle Mainnet', 5000), ('Celo Mainnet', 42220)]:
            assert chain_registry.STANDARD_CHAINS[chain_id]['name'] == chainlist_alias(chain_name)


class TestSync:
    async def test_registers_a_chain_the_static_table_lacks(self, registry_snapshot) -> None:  # noqa: ARG002
        transport = _StubTransport(
            [{'chainid': '424242', 'chainname': 'Nonesuch Mainnet', 'status': 1}]
        )
        added = await sync_etherscan_chains(transport=transport, cache=InMemoryCache(max_size=4))

        assert added == frozenset({'nonesuch'})
        client = ChainscanClient.from_config('etherscan', 'nonesuch', api_key='k')
        assert client.chain_id == 424242

    async def test_is_idempotent_and_leaves_known_chains_alone(self, registry_snapshot) -> None:  # noqa: ARG002
        entries = [
            {'chainid': '424242', 'chainname': 'Nonesuch Mainnet', 'status': 1},
            # Ethereum ships as 'ethereum' with its own alias list; a sync must
            # not replace it with a bare chainlist-derived entry.
            {'chainid': '1', 'chainname': 'Ethereum Mainnet', 'status': 1},
        ]
        first = await sync_etherscan_chains(
            transport=_StubTransport(entries), cache=InMemoryCache(max_size=4)
        )
        second = await sync_etherscan_chains(
            transport=_StubTransport(entries), cache=InMemoryCache(max_size=4)
        )

        assert first == frozenset({'nonesuch'})
        assert second == frozenset()
        assert 'eth' in chain_registry.STANDARD_CHAINS[1]['aliases']

    async def test_offline_chains_are_skipped(self, registry_snapshot) -> None:  # noqa: ARG002
        added = await sync_etherscan_chains(
            transport=_StubTransport(
                [{'chainid': '424242', 'chainname': 'Nonesuch Mainnet', 'status': 0}]
            ),
            cache=InMemoryCache(max_size=4),
        )
        assert added == frozenset()

    async def test_a_taken_name_is_never_repointed(self, registry_snapshot) -> None:  # noqa: ARG002
        # A caller who resolved 'ethereum' must not silently start getting
        # another chain's data because a provider reused the name.
        await sync_etherscan_chains(
            transport=_StubTransport(
                [{'chainid': '424242', 'chainname': 'Ethereum Mainnet', 'status': 1}]
            ),
            cache=InMemoryCache(max_size=4),
        )
        assert chain_registry.resolve_chain_id('ethereum') == 1
