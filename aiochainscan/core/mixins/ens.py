"""ENS helper mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from ...services.ens_resolver import ENSResolver


class ENSMixin:
    """ENS convenience methods and lazy resolver."""

    _ens_resolver: ENSResolver | None

    @property
    def ens(self) -> ENSResolver:
        if self._ens_resolver is None:
            from ...services.ens_resolver import ENSResolver

            self._ens_resolver = ENSResolver(cast(Any, self))
        return self._ens_resolver

    async def resolve_name(self, name: str) -> str | None:
        return await self.ens.resolve_name(name)

    async def lookup_address(self, address: str) -> str | None:
        return await self.ens.lookup_address(address)

    async def resolve_names(self, names: list[str]) -> dict[str, str]:
        return await self.ens.resolve_names(names)

    async def lookup_addresses(self, addresses: list[str]) -> dict[str, str]:
        return await self.ens.lookup_addresses(addresses)
