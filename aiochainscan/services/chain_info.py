"""Chain identity probing and validation for explorer instances.

Answers "which chain does this instance actually serve?" for self-hosted /
custom deployments:

- BlockScout (v1/v2): ``POST {base_url}/api/eth-rpc`` with the standard
  JSON-RPC ``eth_chainId`` method. Works on any BlockScout instance and needs
  no API key.
- Etherscan v2: ``GET https://api.etherscan.io/v2/chainlist`` — the keyless
  registry of chains the V2 multichain API serves (one entry per chainid).
  The full list (~60 networks) is fetched at most once per TTL window.

Both results are cached through the :class:`~aiochainscan.ports.cache.Cache`
port with a dedicated cache instance and ``chain:``-prefixed keys, so the
chainlist download is never repeated within a process and the probes do not
pollute any request-level cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..exceptions import ChainscanDataError
from ..ports.cache import Cache
from .constants import CACHE_TTL_CHAIN_INFO_SECONDS

__all__ = ['ChainInfo', 'ChainProbeTransport']

#: Keyless Etherscan V2 registry of served chains (``{"result": [...]}``).
ETHERSCAN_CHAINLIST_URL = 'https://api.etherscan.io/v2/chainlist'

#: Cache key for the (process-shared) Etherscan chainlist payload.
CHAINLIST_CACHE_KEY = 'chain:etherscan:chainlist'

#: Cache key prefix for per-instance BlockScout chain probes.
BLOCKSCOUT_CHAIN_CACHE_PREFIX = 'chain:blockscout:'


@dataclass(frozen=True)
class ChainInfo:
    """Chain descriptor reported by the configured provider instance."""

    chain_id: int
    """Numeric chain id served by the instance (EIP-155)."""

    name: str | None = None
    """Human-readable chain name, when the provider reports one."""

    explorer_url: str | None = None
    """Frontend/base URL of the explorer, when known."""

    api_url: str | None = None
    """API endpoint for this chain, when the provider reports one."""


@runtime_checkable
class ChainProbeTransport(Protocol):
    """Transport port for chain probes — satisfied by :class:`Network`."""

    async def request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any] | str:
        """Perform an HTTP request with pooling, rate limiting and retries."""
        ...


def _hex_chain_id(value: Any) -> int | None:
    """Convert a JSON-RPC ``eth_chainId`` result (``"0x1"``) to an int."""
    if not isinstance(value, str) or not value.startswith('0x'):
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


async def fetch_blockscout_chain_info(
    transport: ChainProbeTransport,
    base_url: str,
    cache: Cache,
) -> ChainInfo:
    """Probe a BlockScout instance (self-hosted or public) for its chain id.

    Uses the standard JSON-RPC ``eth_chainId`` via the instance's
    ``/api/eth-rpc`` endpoint. Result is cached per base URL for
    ``CACHE_TTL_CHAIN_INFO_SECONDS``.
    """
    key = f'{BLOCKSCOUT_CHAIN_CACHE_PREFIX}{base_url}'
    cached = await cache.get(key)
    if isinstance(cached, ChainInfo):
        return cached

    result = await transport.request(
        method='POST',
        url=f'{base_url}/api/eth-rpc',
        json_data={'jsonrpc': '2.0', 'method': 'eth_chainId', 'params': [], 'id': 1},
        headers={'Content-Type': 'application/json'},
    )
    chain_id = _hex_chain_id(result)
    if chain_id is None:
        raise ValueError(f'BlockScout instance {base_url} returned a malformed eth_chainId result')

    info = ChainInfo(chain_id=chain_id, explorer_url=base_url)
    await cache.set(key, info, ttl_seconds=CACHE_TTL_CHAIN_INFO_SECONDS)
    return info


async def fetch_etherscan_chainlist(
    transport: ChainProbeTransport, cache: Cache
) -> list[dict[str, Any]]:
    """Fetch the Etherscan V2 chainlist, cached once per TTL window.

    The chainlist is the keyless authority on which chains the V2 multichain
    API serves; downloading ~60 entries must not repeat within a process.
    """
    cached = await cache.get(CHAINLIST_CACHE_KEY)
    if isinstance(cached, list):
        return list(cached)

    result = await transport.request(method='GET', url=ETHERSCAN_CHAINLIST_URL)
    entries = result.get('result') if isinstance(result, dict) else result
    if not isinstance(entries, list):
        raise ValueError(f'Malformed chainlist response from {ETHERSCAN_CHAINLIST_URL}')

    await cache.set(CHAINLIST_CACHE_KEY, list(entries), ttl_seconds=CACHE_TTL_CHAIN_INFO_SECONDS)
    return list(entries)


async def fetch_etherscan_chain_info(
    transport: ChainProbeTransport,
    chain_id: int,
    cache: Cache,
) -> ChainInfo:
    """Resolve a chainid to its Etherscan V2 chainlist entry (cached).

    Raises:
        ChainscanDataError: The chainlist does not include *chain_id* — the
            provider does not serve this chain.
    """
    entries = await fetch_etherscan_chainlist(transport, cache)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get('chainid')) == str(chain_id):
            return ChainInfo(
                chain_id=chain_id,
                name=entry.get('chainname'),
                explorer_url=entry.get('blockexplorer'),
                api_url=entry.get('apiurl'),
            )
    raise ChainscanDataError(
        f'Etherscan V2 chainlist does not include chain {chain_id}; '
        'the provider does not serve this chain'
    )
