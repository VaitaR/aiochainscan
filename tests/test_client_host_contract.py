"""Conformance tests for the ``ClientHost`` contract (C13).

``ClientHost`` (``aiochainscan/core/host.py``) is the one declared host
surface every domain mixin's ``self`` needs. These tests prove it is not
vacuous:

- every member of ``ClientHost`` is actually readable off a real
  ``ChainscanPool`` — including ``network``, added to the pool by this
  change — where it previously raised ``AttributeError``;
- the ``ENSResolver`` unsupported-network message carries the real network
  string for a pool host, proving the ``getattr(self.client, 'network',
  None)`` workaround revert did not just move the ``None`` elsewhere.
"""

from __future__ import annotations

import pytest

from aiochainscan.chain_registry import resolve_scanner_target
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.host import ClientHost
from aiochainscan.core.pool import ChainscanPool
from aiochainscan.domain.method import Method
from aiochainscan.exceptions import ChainscanClientError
from aiochainscan.services.ens_resolver import ENSResolver

# ``ClientHost`` members from the brief's table (async ``call`` excluded —
# it is exercised elsewhere; calling it here would issue HTTP).
_SYNC_CLIENT_HOST_MEMBERS = (
    'supports_method',
    'scanner_name',
    'scanner_version',
    'network',
    'chain_id',
    '_scanner',
    '_network',
    '_expected_chain_id',
    '_ens_resolver',
)

# ``SupportsStreaming`` methods ``ClientHost`` composes rather than restates.
_STREAMING_MEMBERS = (
    'iter_transactions',
    'iter_logs',
    'iter_transactions_streaming',
    'iter_internal_transactions_streaming',
    'iter_token_transfers_streaming',
    'iter_logs_streaming',
    'iter_token_holders_streaming',
    'iter_transactions_normalized',
    'iter_internal_transactions_normalized',
    'iter_token_transfers_normalized',
    'iter_logs_normalized',
)


def _make_pool() -> ChainscanPool:
    etherscan = ChainscanClient(
        resolve_scanner_target('etherscan', 'ethereum', api_key='test_key')
    )
    blockscout = ChainscanClient(resolve_scanner_target('blockscout_v2', 'ethereum'))
    return ChainscanPool([etherscan, blockscout])


class TestClientHostReadableOnPool:
    """Every declared ``ClientHost`` member must be readable off the pool."""

    def test_every_member_readable(self) -> None:
        pool = _make_pool()
        for name in _SYNC_CLIENT_HOST_MEMBERS:
            # getattr must not raise AttributeError; the presence check
            # (not the value) is the contract being proven here.
            getattr(pool, name)

    def test_network_specifically(self) -> None:
        """``network`` is the member this brief added to the pool."""
        pool = _make_pool()
        assert pool.network == pool._active_client.network

    def test_streaming_members_present(self) -> None:
        pool = _make_pool()
        for name in _STREAMING_MEMBERS:
            assert callable(getattr(pool, name))

    def test_pool_is_a_client_host(self) -> None:
        """Runtime mirror of the static ``_assert_client_host`` check."""
        pool: ClientHost = _make_pool()
        assert pool.scanner_name
        assert pool.network


class TestEnsResolverNetworkMessageNonVacuous:
    """``ENSResolver``'s unsupported-network message must name the real network.

    Before the revert, ``self.client.network`` was read via
    ``getattr(self.client, 'network', None)``; a pool host's ``network``
    only exists after this brief's change, so on ``base`` this message
    silently degraded to ``None`` instead of raising or naming the network.
    """

    @pytest.mark.asyncio
    async def test_resolve_name_message_names_real_network(self) -> None:
        # blockscout_v2 on 'polygon' resolves to a non-mainnet chain_id (not
        # Ethereum mainnet's 1), so ENS support is refused and the message
        # is built.
        client = ChainscanClient(resolve_scanner_target('blockscout_v2', 'polygon'))
        pool = ChainscanPool([client])
        resolver = ENSResolver(pool)  # type: ignore[arg-type]

        with pytest.raises(ValueError) as exc_info:
            await resolver.resolve_name('vitalik.eth')

        message = str(exc_info.value)
        assert 'None' not in message
        assert pool.network in message

    @pytest.mark.asyncio
    async def test_lookup_address_message_names_real_network(self) -> None:
        client = ChainscanClient(resolve_scanner_target('blockscout_v2', 'polygon'))
        pool = ChainscanPool([client])
        resolver = ENSResolver(pool)  # type: ignore[arg-type]

        with pytest.raises(ValueError) as exc_info:
            await resolver.lookup_address('0x0000000000000000000000000000000000000000')

        message = str(exc_info.value)
        assert 'None' not in message
        assert pool.network in message

    def test_str_names_real_network(self) -> None:
        client = ChainscanClient(resolve_scanner_target('blockscout_v2', 'polygon'))
        pool = ChainscanPool([client])
        resolver = ENSResolver(pool)  # type: ignore[arg-type]

        text = str(resolver)
        assert 'None' not in text
        assert pool.network in text


class TestClientCloseKeepsOneErrorShape:
    """``close()`` used to drop the client's ``Network`` reference while the
    scanner kept the same (closed) object, so a post-close call raised an
    ``AttributeError`` or a clean error depending on which seam it reached."""

    async def test_request_after_close_raises_the_closed_network_error(self) -> None:
        client = ChainscanClient(resolve_scanner_target('blockscout_v2', 'ethereum'))
        await client.close()
        await client.close()  # idempotent

        with pytest.raises(ChainscanClientError, match='Network is closed'):
            await client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')

        with pytest.raises(ChainscanClientError, match='Network is closed'):
            await client.fetch_page(Method.ACCOUNT_TRANSACTIONS, {'address': '0x0'})
