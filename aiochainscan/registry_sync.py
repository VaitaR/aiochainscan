"""Opt-in refresh of the chain registry from a provider's own chain list.

The static tables in :mod:`aiochainscan.chain_registry` remain the shipped
truth: they are what a fresh install resolves with, offline and without a
request. This module is the escape hatch for the gap between a provider adding
a chain and this library releasing it — call it and every chain the provider
currently serves becomes constructible.

    from aiochainscan.registry_sync import sync_etherscan_chains

    added = await sync_etherscan_chains()   # network names now constructible

Only Etherscan is synced. Its chains all route through one unified endpoint,
so "listed" and "reachable" are the same fact. A BlockScout instance is a
separate host per chain, and the instance directory lists hosts that 404, only
redirect, or serve a partial surface -- measured, not assumed -- so registering
from it would trade a missing chain for a broken one. BlockScout instances
stay live-probed and static.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .chain_registry import register_etherscan_chain
from .services.chain_info import fetch_etherscan_chainlist

if TYPE_CHECKING:
    from .ports.cache import Cache
    from .services.chain_info import ChainProbeTransport

__all__ = ['chainlist_alias', 'sync_etherscan_chains']

#: Chainlist names carry the network's role as a trailing word; the alias keeps
#: the chain, not the role ('Celo Sepolia Testnet' -> 'celo-sepolia').
_ROLE_SUFFIXES = ('mainnet', 'testnet')

_NON_SLUG = re.compile(r'[^a-z0-9]+')


def chainlist_alias(chain_name: str) -> str:
    """Network name for a chainlist entry's ``chainname``.

    The same rule produced the static entries, so a synced chain and a shipped
    one are spelled identically -- a caller's network string must not depend on
    whether the sync ran.
    """
    words = _NON_SLUG.sub(' ', chain_name.lower()).split()
    while len(words) > 1 and words[-1] in _ROLE_SUFFIXES:
        words.pop()
    return '-'.join(words)


async def sync_etherscan_chains(
    *, transport: ChainProbeTransport | None = None, cache: Cache | None = None
) -> frozenset[str]:
    """Register every chain the live Etherscan v2 chainlist serves.

    Additive and idempotent (see :func:`register_etherscan_chain`): a chain
    already in the static tables keeps its declared spelling, and a name
    already taken is left pointing where it points. Entries the chainlist marks
    offline (``status`` 0) are skipped -- the endpoint would accept the chainid
    and answer nothing.

    Args:
        transport: Chain-probe transport; a plain :class:`Network` by default.
        cache: Cache for the downloaded list; a private in-memory one by
            default, so a sync never evicts a client's chain-info entries.

    Returns:
        The network names this call made constructible (empty when the static
        tables were already current).
    """
    own_transport = transport is None
    if transport is None:
        from .core.url_builder import UrlBuilder
        from .network import Network

        # The chainlist URL is absolute and keyless; the builder is only the
        # transport's required collaborator, never consulted for this request.
        transport = Network(UrlBuilder('', 'eth', 'main'))
    if cache is None:
        from .adapters.memory_cache import InMemoryCache

        cache = InMemoryCache(max_size=8)

    try:
        entries = await fetch_etherscan_chainlist(transport, cache)
    finally:
        if own_transport:
            await transport.close()  # type: ignore[attr-defined]

    added: set[str] = set()
    for entry in entries:
        chain_id = _chain_id(entry)
        name = entry.get('chainname') if isinstance(entry, dict) else None
        if chain_id is None or not isinstance(name, str) or not name:
            continue
        if entry.get('status') == 0:
            continue
        alias = chainlist_alias(name)
        if alias and register_etherscan_chain(chain_id, alias):
            added.add(alias)
    return frozenset(added)


def _chain_id(entry: Any) -> int | None:
    if not isinstance(entry, dict):
        return None
    try:
        return int(str(entry.get('chainid')))
    except (TypeError, ValueError):
        return None
