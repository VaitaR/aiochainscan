"""
ENS (Ethereum Name Service) resolver with multi-scanner support.

Provides forward (name → address) and reverse (address → name) resolution
with automatic caching and fallback strategies.

Features:
- BlockScout V2 integration (leverages ens_domain_name in responses)
- Direct ENS contract calls for Etherscan and other scanners
- Aggressive caching with TTL (default 1 hour)
- Batch resolution with parallel requests
- Graceful handling of unsupported networks

Example:
    ```python
    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Forward resolution
    address = await client.resolve_name("vitalik.eth")
    # Returns: "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

    # Reverse lookup
    name = await client.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    # Returns: "vitalik.eth"

    # Batch operations
    addresses = await client.resolve_names(["vitalik.eth", "uniswap.eth"])
    ```
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, Protocol, runtime_checkable

from ..constants import BATCH_DEFAULT_CONCURRENCY, ENS_MAX_NAME_LENGTH
from ..domain.method import Method
from ..domain.models import Address
from ..ports.cache import Cache

# ENS contract addresses on Ethereum mainnet
ENS_REGISTRY_ADDRESS = '0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e'
ENS_PUBLIC_RESOLVER = '0x4976fb03C32e5B8cfe2b6cCB31c09Ba78EBaBa41'


def _normalize_ens_name(value: Any) -> str | None:
    """Return a bounded ``.eth`` name, or ``None`` for untrusted input."""
    if not isinstance(value, str):
        return None
    name = value.strip().lower()
    if not name or len(name) > ENS_MAX_NAME_LENGTH or not name.endswith('.eth'):
        return None
    return name


def _name_input_key(name: str) -> str:
    """Dedup key for batch forward inputs (case/whitespace-insensitive)."""
    return name.strip().lower() if isinstance(name, str) else str(name)


def _address_input_key(address: str) -> str:
    """Dedup key for batch reverse inputs (checksum-normalized address)."""
    if isinstance(address, str):
        try:
            return str(Address(address)).lower()
        except ValueError:
            return address
    return str(address)


@runtime_checkable
class AddressInfoProvider(Protocol):
    """Scanner-port subset the resolver needs for ENS reverse lookup.

    A scanner satisfying this port can fetch full address info (including
    ``ens_domain_name``) for an address. Satisfied by
    :class:`~aiochainscan.scanners.blockscout_v2.BlockScoutV2Scanner` via its
    ``get_address_info`` method, which exists precisely to serve ENS reverse
    resolution. The concrete scanner is injected at construction by the client
    (see ``ENSMixin.ens``) — the resolver never reaches through the client.
    """

    async def get_address_info(self, address: str) -> dict[str, Any]:
        """Fetch full address information for ``address``."""
        ...


class ENSClient(Protocol):
    """Client capabilities required by the ENS resolver.

    Structurally a subset of ``aiochainscan.core.host.ClientHost`` — kept as
    a separate declaration here, rather than importing that protocol, per
    ``AGENTS.md``'s dependency rule ("Only downward. Never upward.").
    ``ClientHost`` is the authority; keep this subset in sync with it by
    hand. Both members are read-only properties on ``ClientHost`` (a plain
    mutable attribute on ``ChainscanClient`` and a read-only forward on
    ``ChainscanPool`` both satisfy that), so they are declared the same way
    here rather than as plain attributes.
    """

    @property
    def chain_id(self) -> int | None: ...

    @property
    def network(self) -> str: ...

    async def call(self, method: Method, **params: Any) -> Any: ...


class ENSResolver:
    """
    ENS resolver with multi-scanner support and caching.

    Implements:
    - Forward resolution: name → address
    - Reverse lookup: address → name
    - Batch operations for parallel resolution
    - Automatic caching with TTL
    - Fallback strategies for different scanners
    """

    def __init__(
        self,
        client: ENSClient,
        cache_ttl: int = 3600,
        enable_cache: bool = True,
        *,
        address_info_scanner: AddressInfoProvider | None = None,
        cache: Cache | None = None,
    ):
        """
        Initialize ENS resolver.

        Args:
            client: ChainscanClient instance (used for chain/network checks and
                ENS contract calls via ``PROXY_ETH_CALL``)
            cache_ttl: Cache TTL in seconds (default: 1 hour)
            enable_cache: Enable caching (default: True)
            address_info_scanner: Optional scanner satisfying
                :class:`AddressInfoProvider` (e.g. BlockScout V2) used to
                reverse-resolve addresses via ``ens_domain_name``. Injected by
                the client at construction; never discovered through the
                client's privates.
            cache: Optional cache adapter. If caching is enabled without an
                injected cache, resolution remains uncached.
        """
        self.client = client
        self.cache_ttl = cache_ttl
        self.enable_cache = enable_cache
        self._address_info_scanner = address_info_scanner

        # Initialize cache (entries populate lazily on first live lookup)
        self._cache: Cache | None = cache if enable_cache else None

    def _is_ens_supported(self) -> bool:
        """Check if ENS is supported on the current network."""
        # ENS is only on Ethereum mainnet (chain_id = 1)
        return self.client.chain_id == 1

    async def resolve_name(self, name: str) -> str | None:
        """
        Resolve ENS name to Ethereum address.

        Args:
            name: ENS name (e.g., "vitalik.eth")

        Returns:
            Ethereum address or None if not found

        Raises:
            ValueError: If ENS is not supported on this network

        Example:
            ```python
            address = await resolver.resolve_name("vitalik.eth")
            print(address)  # "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
            ```
        """
        if not self._is_ens_supported():
            raise ValueError(
                f'ENS is only supported on Ethereum mainnet. '
                f'Current network: {self.client.network} (chain_id={self.client.chain_id})'
            )

        normalized_name = _normalize_ens_name(name)
        if normalized_name is None:
            return None
        name = normalized_name

        # Check cache
        if self._cache is not None:
            cached = await self._cache.get(f'name:{name}')
            if cached:
                return str(cached)

        # Resolve via direct ENS contract calls
        address = await self._resolve_via_ens_contract(name)

        # Cache result if found
        if address and self._cache is not None:
            await self._cache.set(f'name:{name}', address, ttl_seconds=self.cache_ttl)
            # Also cache reverse lookup
            await self._cache.set(f'addr:{address.lower()}', name, ttl_seconds=self.cache_ttl)

        return address

    async def lookup_address(self, address: str) -> str | None:
        """
        Reverse lookup: Ethereum address to ENS name.

        Args:
            address: Ethereum address (e.g., "0xd8dA...")

        Returns:
            ENS name or None if not found

        Raises:
            ValueError: If ENS is not supported on this network

        Example:
            ```python
            name = await resolver.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
            print(name)  # "vitalik.eth"
            ```
        """
        if not self._is_ens_supported():
            raise ValueError(
                f'ENS is only supported on Ethereum mainnet. '
                f'Current network: {self.client.network} (chain_id={self.client.chain_id})'
            )

        if not isinstance(address, str):
            return None
        try:
            normalized_address = Address(address)
        except ValueError:
            return None
        address = str(normalized_address)
        address_key = address.lower()

        # Check cache
        if self._cache is not None:
            cached = await self._cache.get(f'addr:{address_key}')
            if cached:
                return str(cached)

        # Try scanner-specific reverse lookup
        name = await self._reverse_lookup_via_scanner(address)

        # Cache result if found
        if name and self._cache is not None:
            await self._cache.set(f'addr:{address_key}', name, ttl_seconds=self.cache_ttl)
            # Also cache forward lookup
            await self._cache.set(f'name:{name.lower()}', address, ttl_seconds=self.cache_ttl)

        return name

    async def _safe_resolve(self, name: str) -> str | None:
        """Resolve a single name, returning None on failure."""
        try:
            return await self.resolve_name(name)
        except Exception:  # noqa: BLE001
            return None

    async def _safe_lookup(self, address: str) -> str | None:
        """Look up a single address, returning None on failure."""
        try:
            return await self.lookup_address(address)
        except Exception:  # noqa: BLE001
            return None

    async def _resolve_batch(
        self,
        inputs: list[str],
        *,
        resolve_one: Callable[[str], Coroutine[Any, Any, str | None]],
        input_key: Callable[[str], str],
    ) -> dict[str, str]:
        """Chunked TaskGroup fan-out shared by the batch methods.

        Inputs sharing a normalized ``input_key`` collapse to one live
        lookup (``resolve_one`` on the first spelling); a string result is
        replicated to every spelling of that key, while failures (``None``)
        are omitted from the result.
        """
        if not self._is_ens_supported():
            return {}

        resolved: dict[str, str] = {}
        spellings_by_key: dict[str, list[str]] = {}
        for value in inputs:
            spellings_by_key.setdefault(input_key(value), []).append(value)

        spellings = list(spellings_by_key.values())
        for start in range(0, len(spellings), BATCH_DEFAULT_CONCURRENCY):
            chunk = spellings[start : start + BATCH_DEFAULT_CONCURRENCY]
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(resolve_one(group[0])) for group in chunk]
            for aliases, task in zip(chunk, tasks, strict=True):
                result = task.result()
                if isinstance(result, str):
                    for alias in aliases:
                        resolved[alias] = result
        return resolved

    async def resolve_names(self, names: list[str]) -> dict[str, str]:
        """
        Batch resolve multiple ENS names to addresses.

        Args:
            names: List of ENS names

        Returns:
            Dict mapping names to addresses (only successful resolutions)

        Example:
            ```python
            result = await resolver.resolve_names(["vitalik.eth", "uniswap.eth"])
            # {"vitalik.eth": "0xd8dA...", "uniswap.eth": "0x1f98..."}
            ```
        """
        return await self._resolve_batch(
            names, resolve_one=self._safe_resolve, input_key=_name_input_key
        )

    async def lookup_addresses(self, addresses: list[str]) -> dict[str, str]:
        """
        Batch reverse lookup multiple addresses to ENS names.

        Args:
            addresses: List of Ethereum addresses

        Returns:
            Dict mapping addresses to names (only successful lookups)

        Example:
            ```python
            result = await resolver.lookup_addresses([
                "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"
            ])
            # {"0xd8dA...": "vitalik.eth", "0x1f98...": "uniswap.eth"}
            ```
        """
        return await self._resolve_batch(
            addresses, resolve_one=self._safe_lookup, input_key=_address_input_key
        )

    async def _reverse_lookup_via_scanner(self, address: str) -> str | None:
        """
        Reverse lookup using scanner-specific methods.

        Strategy:
        1. Injected ``AddressInfoProvider`` scanner (BlockScout V2): use the
           address info endpoint (returns ``ens_domain_name``)
        2. Etherscan and others: ENS contract calls (fallback)
        """
        if self._address_info_scanner is not None:
            try:
                info = await self._address_info_scanner.get_address_info(address)
                if isinstance(info, dict):
                    ens_name = _normalize_ens_name(info.get('ens_domain_name'))
                    if ens_name is not None:
                        return ens_name
            except Exception:
                # Fall through to ENS contract fallback
                # Catch all exceptions including 422 errors for invalid addresses
                pass

        # Fallback to ENS contract reverse lookup
        return await self._reverse_lookup_via_ens_contract(address)

    async def _registry_resolver_address(self, node: str) -> str | None:
        """Ask the ENS registry for the resolver of ``node``.

        Shared first step of both contract paths: eth_call the registry's
        ``resolver(bytes32)`` and return the resolver address, or ``None``
        when the call fails to produce a word or the registry maps the node
        to the zero address (no resolver set).
        """
        resolver_data = f'0x0178b8bf{node}'  # resolver(bytes32)

        resolver_result = await self.client.call(
            Method.PROXY_ETH_CALL,
            to=ENS_REGISTRY_ADDRESS,
            data=resolver_data,
        )

        if not resolver_result or resolver_result == '0x' or len(resolver_result) < 66:
            return None

        # Extract resolver address (last 40 chars of 64-char hex)
        resolver_address = '0x' + str(resolver_result[-40:])

        if resolver_address == '0x' + '0' * 40:
            return None  # No resolver set

        return resolver_address

    async def _resolve_via_ens_contract(self, name: str) -> str | None:
        """
        Resolve ENS name using direct ENS contract calls.

        Uses the ENS registry and resolver contracts via eth_call.
        """
        try:
            # Calculate namehash for the ENS name
            node = self._namehash(name)

            # Step 1: Get resolver address from ENS registry
            resolver_address = await self._registry_resolver_address(node)
            if resolver_address is None:
                return None

            # Step 2: Get address from resolver
            # addr(bytes32 node) returns address
            addr_data = f'0x3b3b57de{node}'  # addr(bytes32)

            addr_result = await self.client.call(
                Method.PROXY_ETH_CALL,
                to=resolver_address,
                data=addr_data,
            )

            if not addr_result or addr_result == '0x' or len(addr_result) < 66:
                return None

            # Extract address (last 40 chars)
            address = '0x' + addr_result[-40:]

            if address == '0x' + '0' * 40:
                return None  # No address set

            # Checksum the address
            return self._to_checksum_address(address)

        except Exception:
            # If ENS contract calls fail, return None
            return None

    async def _reverse_lookup_via_ens_contract(self, address: str) -> str | None:
        """
        Reverse lookup using ENS reverse registrar.

        Uses addr.reverse format (e.g., "d8da...045.addr.reverse")
        """
        try:
            # Remove 0x prefix and convert to lowercase
            addr_clean = address[2:].lower() if address.startswith('0x') else address.lower()

            # Create reverse node (e.g., "d8da...045.addr.reverse")
            reverse_name = f'{addr_clean}.addr.reverse'
            node = self._namehash(reverse_name)

            # Step 1: Get resolver from ENS registry
            resolver_address = await self._registry_resolver_address(node)
            if resolver_address is None:
                return None

            # Step 2: Get name from resolver
            # name(bytes32 node) returns string
            name_data = f'0x691f3431{node}'  # name(bytes32)

            name_result = await self.client.call(
                Method.PROXY_ETH_CALL,
                to=resolver_address,
                data=name_data,
            )

            if not name_result or name_result == '0x':
                return None

            # Decode string from ABI encoding
            # String format: 0x + offset(32bytes) + length(32bytes) + data
            name = self._decode_string(name_result)

            if name and name.endswith('.eth'):
                return name

            return None

        except Exception:
            return None

    def _namehash(self, name: str) -> str:
        """
        Calculate ENS namehash for a name.

        Algorithm:
        1. Split name by '.'
        2. Start with zero hash (32 bytes)
        3. For each label (right to left), hash = keccak256(hash + keccak256(label))

        Args:
            name: ENS name (e.g., "vitalik.eth")

        Returns:
            32-byte namehash as hex string (without 0x prefix)
        """
        from aiochainscan.crypto import keccak256

        if not name:
            return '0' * 64

        node = b'\x00' * 32

        if name:
            labels = name.split('.')
            for label in reversed(labels):
                label_hash = keccak256(label.encode('utf-8'))
                node = keccak256(node + label_hash)

        return node.hex()

    def _to_checksum_address(self, address: str) -> str:
        """
        Convert address to EIP-55 checksum format.

        Args:
            address: Ethereum address (with or without 0x)

        Returns:
            Checksummed address
        """
        from aiochainscan.crypto import to_checksum_address

        addr = address[2:] if address.startswith('0x') else address
        return to_checksum_address(f'0x{addr}')

    def _decode_string(self, data: str) -> str | None:
        """
        Decode ABI-encoded string from eth_call result.

        Format: 0x + offset(32bytes) + length(32bytes) + string_data(padded to 32-byte chunks)

        Args:
            data: Hex string with 0x prefix

        Returns:
            Decoded string or None
        """
        try:
            if not data or data == '0x':
                return None

            # Remove 0x prefix
            hex_data = data[2:]

            # Skip offset (first 64 chars)
            if len(hex_data) < 128:
                return None

            # Get length (next 64 chars, convert to int)
            length_hex = hex_data[64:128]
            length = int(length_hex, 16)

            if length == 0 or length > ENS_MAX_NAME_LENGTH:  # Sanity check
                return None

            # Get string data (starts at char 128)
            string_hex = hex_data[128 : 128 + length * 2]

            # Convert hex to bytes to string
            string_bytes = bytes.fromhex(string_hex)
            return string_bytes.decode('utf-8')

        except Exception:
            return None

    async def clear_cache(self) -> None:
        """Clear the ENS resolution cache."""
        if self._cache is not None:
            await self._cache.clear()

    def __str__(self) -> str:
        """String representation."""
        status = 'enabled' if self.enable_cache else 'disabled'
        return f'ENSResolver(cache={status}, network={self.client.network})'

    def __repr__(self) -> str:
        """Detailed representation."""
        return (
            f'ENSResolver(client={self.client!r}, '
            f'cache_ttl={self.cache_ttl}, '
            f'enable_cache={self.enable_cache})'
        )
