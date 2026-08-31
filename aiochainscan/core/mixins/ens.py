"""ENS helper mixin for ``ChainscanClient``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from ...scanners.base import Scanner
    from ...services.ens_resolver import AddressInfoProvider, ENSResolver


class ENSMixin:
    """ENS convenience methods and lazy resolver."""

    _ens_resolver: ENSResolver | None
    _scanner: Scanner

    @property
    def ens(self) -> ENSResolver:
        if self._ens_resolver is None:
            from ...services.ens_resolver import ENSResolver

            self._ens_resolver = ENSResolver(
                cast(Any, self),
                address_info_scanner=self._ens_address_info_scanner(),
            )
        return self._ens_resolver

    def _ens_address_info_scanner(self) -> AddressInfoProvider | None:
        """Return the scanner that provides full address info, if any.

        This is the single, explicit wiring point for ENS reverse lookup: the
        client (which owns the scanner) decides here whether the scanner can
        serve ``get_address_info``. The resolver receives it as a constructor
        dependency and never reaches through the client's privates.
        """
        from ...services.ens_resolver import AddressInfoProvider

        scanner = self._scanner
        if isinstance(scanner, AddressInfoProvider):
            return scanner
        return None

    async def resolve_name(self, name: str) -> str | None:
        return await self.ens.resolve_name(name)

    async def lookup_address(self, address: str) -> str | None:
        return await self.ens.lookup_address(address)

    async def resolve_names(self, names: list[str]) -> dict[str, str]:
        return await self.ens.resolve_names(names)

    async def lookup_addresses(self, addresses: list[str]) -> dict[str, str]:
        return await self.ens.lookup_addresses(addresses)
