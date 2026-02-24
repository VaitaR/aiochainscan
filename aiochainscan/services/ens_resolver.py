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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.client import ChainscanClient

from ..adapters.memory_cache import InMemoryCache
from ..core.method import Method
from ..exceptions import ChainscanClientApiError

# ENS contract addresses on Ethereum mainnet
ENS_REGISTRY_ADDRESS = '0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e'
ENS_PUBLIC_RESOLVER = '0x4976fb03C32e5B8cfe2b6cCB31c09Ba78EBaBa41'

# Common ENS names (pre-warm cache)
COMMON_ENS_NAMES = {
    'vitalik.eth': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
    'nick.eth': '0xb8c2C29ee19D8307cb7255e1Cd9CbDE883A267d5',
}


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
        client: ChainscanClient,
        cache_ttl: int = 3600,
        enable_cache: bool = True,
    ):
        """
        Initialize ENS resolver.

        Args:
            client: ChainscanClient instance
            cache_ttl: Cache TTL in seconds (default: 1 hour)
            enable_cache: Enable caching (default: True)
        """
        self.client = client
        self.cache_ttl = cache_ttl
        self.enable_cache = enable_cache

        # Initialize cache
        self._cache: InMemoryCache | None = None
        if enable_cache:
            self._cache = InMemoryCache(max_size=5000)
            # Pre-warm with common names
            asyncio.create_task(self._prewarm_cache())

    async def _prewarm_cache(self) -> None:
        """Pre-warm cache with common ENS names."""
        if not self._cache:
            return

        for name, address in COMMON_ENS_NAMES.items():
            # Cache both forward and reverse
            await self._cache.set(f'name:{name}', address, ttl_seconds=self.cache_ttl)
            await self._cache.set(f'addr:{address.lower()}', name, ttl_seconds=self.cache_ttl)

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

        if not name or not name.endswith('.eth'):
            return None

        name = name.lower().strip()

        # Check cache
        if self._cache:
            cached = await self._cache.get(f'name:{name}')
            if cached:
                return str(cached)

        # Try scanner-specific resolution
        address = await self._resolve_via_scanner(name)

        # Cache result if found
        if address and self._cache:
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

        if not address or not address.startswith('0x'):
            return None

        address = address.lower().strip()

        # Check cache
        if self._cache:
            cached = await self._cache.get(f'addr:{address}')
            if cached:
                return str(cached)

        # Try scanner-specific reverse lookup
        name = await self._reverse_lookup_via_scanner(address)

        # Cache result if found
        if name and self._cache:
            await self._cache.set(f'addr:{address}', name, ttl_seconds=self.cache_ttl)
            # Also cache forward lookup
            await self._cache.set(f'name:{name.lower()}', address, ttl_seconds=self.cache_ttl)

        return name

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
        if not self._is_ens_supported():
            return {}

        # Resolve in parallel
        tasks = [self.resolve_name(name) for name in names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dict (only successful resolutions)
        return {
            name: address
            for name, address in zip(names, results, strict=False)
            if isinstance(address, str) and address is not None
        }

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
        if not self._is_ens_supported():
            return {}

        # Lookup in parallel
        tasks = [self.lookup_address(addr) for addr in addresses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dict (only successful lookups)
        return {
            addr: name
            for addr, name in zip(addresses, results, strict=False)
            if isinstance(name, str) and name is not None
        }

    async def _resolve_via_scanner(self, name: str) -> str | None:
        """
        Resolve ENS name using scanner-specific methods.

        Strategy:
        1. BlockScout V2: Try to search for the address via API
        2. Etherscan: Use ENS contract calls (fallback)
        """
        # For BlockScout V2, we can't directly resolve names to addresses
        # but we can try the reverse: if we have a cached address, verify it
        # For now, fall back to ENS contract calls

        return await self._resolve_via_ens_contract(name)

    async def _reverse_lookup_via_scanner(self, address: str) -> str | None:
        """
        Reverse lookup using scanner-specific methods.

        Strategy:
        1. BlockScout V2: Use address info endpoint (returns ens_domain_name)
        2. Etherscan: Use ENS contract calls (fallback)
        """
        if self.client.scanner_name == 'blockscout' and self.client.scanner_version == 'v2':
            try:
                # Use the scanner's get_address_info method to get ens_domain_name
                # Only BlockScoutV2Scanner has this method, so use getattr for type safety
                get_address_info = getattr(self.client._scanner, 'get_address_info', None)
                if get_address_info is not None and callable(get_address_info):
                    info = await get_address_info(address)
                    ens_name = info.get('ens_domain_name')
                    if ens_name:
                        return str(ens_name)
            except (ChainscanClientApiError, AttributeError, KeyError, Exception):
                # Fall through to ENS contract fallback
                # Catch all exceptions including 422 errors for invalid addresses
                pass

        # Fallback to ENS contract reverse lookup
        return await self._reverse_lookup_via_ens_contract(address)

    async def _resolve_via_ens_contract(self, name: str) -> str | None:
        """
        Resolve ENS name using direct ENS contract calls.

        Uses the ENS registry and resolver contracts via eth_call.
        """
        try:
            # Calculate namehash for the ENS name
            node = self._namehash(name)

            # Step 1: Get resolver address from ENS registry
            # resolver(bytes32 node) returns address
            resolver_data = f'0x0178b8bf{node}'  # resolver(bytes32)

            resolver_result = await self.client.call(
                Method.PROXY_ETH_CALL,
                to=ENS_REGISTRY_ADDRESS,
                data=resolver_data,
            )

            if not resolver_result or resolver_result == '0x' or len(resolver_result) < 66:
                return None

            # Extract resolver address (last 40 chars of 64-char hex)
            resolver_address = '0x' + resolver_result[-40:]

            if resolver_address == '0x' + '0' * 40:
                return None  # No resolver set

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
            resolver_data = f'0x0178b8bf{node}'  # resolver(bytes32)

            resolver_result = await self.client.call(
                Method.PROXY_ETH_CALL,
                to=ENS_REGISTRY_ADDRESS,
                data=resolver_data,
            )

            if not resolver_result or resolver_result == '0x' or len(resolver_result) < 66:
                return None

            resolver_address = '0x' + resolver_result[-40:]

            if resolver_address == '0x' + '0' * 40:
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
        from eth_hash.auto import keccak

        if not name:
            return '0' * 64

        node = b'\x00' * 32

        if name:
            labels = name.split('.')
            for label in reversed(labels):
                label_hash = keccak(label.encode('utf-8'))
                node = keccak(node + label_hash)

        return node.hex()

    def _to_checksum_address(self, address: str) -> str:
        """
        Convert address to EIP-55 checksum format.

        Args:
            address: Ethereum address (with or without 0x)

        Returns:
            Checksummed address
        """
        from eth_hash.auto import keccak

        addr = address[2:].lower() if address.startswith('0x') else address.lower()
        hash_result = keccak(addr.encode('utf-8')).hex()

        checksum_addr = '0x'
        for i, char in enumerate(addr):
            if char in '0123456789':
                checksum_addr += char
            else:
                # Use hash to determine if letter should be uppercase
                checksum_addr += char.upper() if int(hash_result[i], 16) >= 8 else char

        return checksum_addr

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

            if length == 0 or length > 1000:  # Sanity check
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
        if self._cache:
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
