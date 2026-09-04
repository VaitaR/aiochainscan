"""``ClientHost`` — the one declared contract every domain mixin's ``self`` needs.

Both :class:`~aiochainscan.core.client.ChainscanClient` and
:class:`~aiochainscan.core.pool.ChainscanPool` are statically asserted to
satisfy this protocol (see the ``TYPE_CHECKING``-guarded assertions at the
bottom of ``core/client.py`` / ``core/pool.py``): removing a member from
either host is a ``mypy --strict`` failure, not a runtime ``AttributeError``.

Read-only members are declared as ``@property`` rather than plain
annotations: a plain mutable attribute on ``ChainscanClient`` and a
read-only forwarding property on ``ChainscanPool`` both satisfy a read-only
protocol property structurally. ``_ens_resolver`` is the one exception — it
is declared as a plain (mutable) attribute because :class:`ENSMixin.ens`
assigns it, and both hosts already provide a setter.

This is the *host* contract, not a registry of mixin-private helpers —
``ChainMixin._instance_label`` and ``ENSMixin._ens_address_info_scanner``
are module-level functions taking a ``ClientHost`` instead (see ``chain.py``
/ ``ens.py``), since a bare-function receiver has no attribute access to a
mixin method.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from ..domain.method import Method
from .streaming import SupportsStreaming

if TYPE_CHECKING:
    from ..network import Network
    from ..scanners.base import Scanner
    from ..services.ens_resolver import ENSResolver


class ClientHost(SupportsStreaming, Protocol):
    """The host surface every domain mixin needs from ``self``."""

    async def call(self, method: Method, **params: Any) -> Any: ...

    def supports_method(self, method: Method) -> bool: ...

    @property
    def scanner_name(self) -> str: ...

    @property
    def scanner_version(self) -> str: ...

    @property
    def network(self) -> str: ...

    @property
    def chain_id(self) -> int | None: ...

    @property
    def _scanner(self) -> Scanner: ...

    @property
    def _network(self) -> Network: ...

    @property
    def _expected_chain_id(self) -> int | None: ...

    _ens_resolver: ENSResolver | None
