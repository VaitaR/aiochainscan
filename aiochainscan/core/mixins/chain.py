"""Chain identity mixin for ``ChainscanClient``.

Exposes ``get_chain_info()`` / ``validate_chain()`` over the chain probes in
:mod:`aiochainscan.services.chain_info`: a BlockScout instance is probed via
its JSON-RPC ``eth_chainId`` endpoint, an Etherscan configuration resolves its
chain through the (cached) V2 chainlist registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...exceptions import ChainscanDataError
from ...services.chain_info import ChainInfo

if TYPE_CHECKING:
    from ...network import Network
    from ...ports.cache import Cache
    from ...scanners.base import Scanner

# Module-level shared cache: chain identities and the ~60-network Etherscan
# chainlist are effectively static, so they are fetched at most once per TTL
# window per process — never per client. Dedicated instance + ``chain:``
# key namespace keeps it isolated from the ENS cache and any request cache.
_chain_info_cache: Cache | None = None


def _get_chain_info_cache() -> Cache:
    global _chain_info_cache
    if _chain_info_cache is None:
        from ...adapters.memory_cache import InMemoryCache

        _chain_info_cache = InMemoryCache(max_size=512)
    return _chain_info_cache


def reset_chain_info_cache() -> None:
    """Drop the process-shared chain-info cache (test/diagnostic helper)."""
    global _chain_info_cache
    _chain_info_cache = None


class ChainMixin:
    """Chain identity helpers for the unified client."""

    _scanner: Scanner
    _network: Network
    scanner_name: str
    scanner_version: str
    chain_id: int | None
    _expected_chain_id: int | None

    async def get_chain_info(self) -> ChainInfo:
        """Chain descriptor of the configured instance/provider (cached).

        - BlockScout (v1/v2, including self-hosted): probes
          ``POST {base_url}/api/eth-rpc`` with ``eth_chainId``.
        - Etherscan v2: resolves the configured chain in the keyless
          ``GET https://api.etherscan.io/v2/chainlist`` registry; raises
          :class:`ChainscanDataError` when the provider does not serve the
          configured chain.

        Results are cached for ``CACHE_TTL_CHAIN_INFO_SECONDS`` (1 hour) in a
        process-shared cache, so the chainlist download never repeats.

        Raises:
            ChainscanDataError: Provider does not serve the configured chain.
            ValueError: Scanner/chain combination cannot be probed (e.g.
                nodereal, or etherscan without a known chain id).
        """
        from ...services.chain_info import (
            fetch_blockscout_chain_info,
            fetch_etherscan_chain_info,
        )

        cache = _get_chain_info_cache()

        if self.scanner_name == 'blockscout':
            base_url = self._scanner.base_url
            if not base_url:
                raise ValueError(
                    f'Chain info requires a resolvable {self.scanner_name} instance base URL'
                )
            return await fetch_blockscout_chain_info(self._network, base_url, cache)

        if self.scanner_name == 'etherscan':
            if self.chain_id is None:
                raise ValueError(
                    'chain_id is unknown for this configuration; '
                    'pass expected_chain_id to from_config to record it'
                )
            return await fetch_etherscan_chain_info(self._network, self.chain_id, cache)

        raise ValueError(f'Chain info is not available for scanner {self.scanner_name!r}')

    async def validate_chain(self, expected_chain_id: int | None = None) -> ChainInfo:
        """Validate that the configured instance serves the expected chain.

        Expectation precedence: the explicit argument, then the
        ``expected_chain_id`` given to ``from_config``, then the configured
        chain id. With no expectation at all the probe result is returned
        unchecked.

        Returns:
            The (cached) :class:`ChainInfo` reported by the instance.

        Raises:
            ChainscanDataError: The instance serves a different chain than
                expected.
        """
        expected = expected_chain_id
        if expected is None:
            expected = self._expected_chain_id
        if expected is None:
            expected = self.chain_id

        info = await self.get_chain_info()
        if expected is not None and info.chain_id != expected:
            raise ChainscanDataError(
                f'Chain mismatch for {self._instance_label()}: '
                f'expected {expected}, instance serves {info.chain_id}'
            )
        return info

    async def _validate_expected_chain_once(self) -> None:
        """First-request guard body: fail fast on a chain mismatch.

        Wired into the Network layer by ``ChainscanClient`` when the client
        was constructed with ``expected_chain_id``.
        """
        expected = self._expected_chain_id
        if expected is None:
            return
        info = await self.get_chain_info()
        if info.chain_id != expected:
            raise ChainscanDataError(
                f'Chain mismatch for {self._instance_label()}: '
                f'expected {expected}, instance serves {info.chain_id}'
            )

    def _instance_label(self) -> str:
        """Short human-readable label of the configured instance."""
        version = self.scanner_version.lstrip('v') or self.scanner_version
        if self.scanner_name == 'blockscout' and self._scanner.base_url:
            return f'{self.scanner_name} v{version} at {self._scanner.base_url}'
        return f'{self.scanner_name} v{version}'
