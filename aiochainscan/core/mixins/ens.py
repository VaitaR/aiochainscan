"""ENS helper mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..host import ClientHost

if TYPE_CHECKING:
    from ...services.ens_resolver import AddressInfoProvider, ENSResolver


class ENSMixin:
    """ENS convenience methods and lazy resolver."""

    @property
    def ens(self: ClientHost) -> ENSResolver:
        return _get_ens_resolver(self)

    async def resolve_name(self: ClientHost, name: str) -> str | None:
        return await _get_ens_resolver(self).resolve_name(name)

    async def lookup_address(self: ClientHost, address: str) -> str | None:
        return await _get_ens_resolver(self).lookup_address(address)

    async def resolve_names(self: ClientHost, names: list[str]) -> dict[str, str]:
        return await _get_ens_resolver(self).resolve_names(names)

    async def lookup_addresses(self: ClientHost, addresses: list[str]) -> dict[str, str]:
        return await _get_ens_resolver(self).lookup_addresses(addresses)


def _get_ens_resolver(host: ClientHost) -> ENSResolver:
    """Lazily construct and cache the host's :class:`ENSResolver`.

    Module-level (not a mixin method) so it can take ``host: ClientHost``
    without also needing ``self.ens`` visible on the protocol: every
    ``ENSMixin`` method that needs the resolver calls this directly instead
    of going through the ``ens`` property, which is itself a thin wrapper
    over it for the public ``client.ens`` surface.
    """
    resolver = host._ens_resolver
    if resolver is None:
        from ...adapters.memory_cache import InMemoryCache
        from ...services.ens_resolver import ENSResolver

        resolver = ENSResolver(
            host,
            address_info_scanner=_ens_address_info_scanner(host),
            cache=InMemoryCache(max_size=5000),
        )
        host._ens_resolver = resolver
    return resolver


def _ens_address_info_scanner(host: ClientHost) -> AddressInfoProvider | None:
    """Return the scanner that provides full address info, if any.

    This is the single, explicit wiring point for ENS reverse lookup: the
    client (which owns the scanner) decides here whether the scanner can
    serve ``get_address_info``. The resolver receives it as a constructor
    dependency and never reaches through the client's privates.
    """
    from ...services.ens_resolver import AddressInfoProvider

    scanner = host._scanner
    if isinstance(scanner, AddressInfoProvider):
        return scanner
    return None
