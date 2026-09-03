"""
Tests for ENS (Ethereum Name Service) resolver.

Tests:
- Forward resolution (name → address)
- Reverse lookup (address → name)
- Batch operations
- Caching behavior
- BlockScout V2 integration
- ENS contract fallback
- Error handling
"""

import asyncio
import warnings
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aiochainscan import ChainscanClient
from aiochainscan.adapters.memory_cache import InMemoryCache
from aiochainscan.constants import BATCH_DEFAULT_CONCURRENCY, ENS_MAX_NAME_LENGTH
from aiochainscan.crypto import to_checksum_address
from aiochainscan.domain.method import Method
from aiochainscan.services.ens_resolver import ENS_PUBLIC_RESOLVER, ENSResolver


class UnitENSClient:
    chain_id = 1
    network = 'ethereum'

    def __init__(self) -> None:
        self.call = AsyncMock(return_value='0x')


class UnitAddressInfoScanner:
    def __init__(self, metadata: object) -> None:
        self.metadata = metadata
        self.get_address_info = AsyncMock(return_value={'ens_domain_name': metadata})


def stub_ens_contract_calls(client: UnitENSClient, *, resolved_address: str) -> None:
    """Answer the forward-resolution eth_call dance with a fixed address.

    A registry ``resolver(bytes32)`` call (selector ``0x0178b8bf``) answers
    the public resolver; any other call — the resolver's ``addr(bytes32)`` —
    answers ``resolved_address``.
    """
    zero_pad = '0' * 24

    async def call(method: Method, **params: Any) -> str:
        data = str(params.get('data', ''))
        if data.startswith('0x0178b8bf'):
            return f'0x{zero_pad}{ENS_PUBLIC_RESOLVER[2:].lower()}'
        return f'0x{zero_pad}{resolved_address[2:].lower()}'

    client.call = AsyncMock(side_effect=call)


class TestENSResolver:
    """Test ENS resolution functionality."""

    @pytest.mark.asyncio
    async def test_ens_only_supported_on_ethereum_mainnet(self):
        """ENS should only work on Ethereum mainnet (chain_id=1)."""
        # Create client for Polygon (not supported)
        client = ChainscanClient.from_config('blockscout_v2', 'polygon')

        with pytest.raises(ValueError, match='ENS is only supported on Ethereum mainnet'):
            await client.resolve_name('vitalik.eth')

        with pytest.raises(ValueError, match='ENS is only supported on Ethereum mainnet'):
            await client.lookup_address('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Forward resolution requires PROXY_ETH_CALL which BlockScout V2 doesn't support"
    )
    async def test_resolve_name_forward(self):
        """Test forward resolution: name → address."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Resolve vitalik.eth
        address = await client.resolve_name('vitalik.eth')

        assert address is not None
        assert address.startswith('0x')
        assert len(address) == 42
        # Vitalik's well-known address
        assert address.lower() == '0xd8da6bf26964af9d7eed9e03e53415d37aa96045'

    @pytest.mark.asyncio
    async def test_resolve_name_invalid(self):
        """Test resolution with invalid name."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Invalid names should return None
        assert await client.resolve_name('') is None
        assert await client.resolve_name('invalid') is None
        assert await client.resolve_name('not-ens-name.com') is None

    @pytest.mark.asyncio
    async def test_lookup_address_reverse(self):
        """Test reverse lookup: address → name."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Reverse lookup vitalik's address
        name = await client.lookup_address('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')

        # BlockScout V2 should return ens_domain_name from address info
        assert name is not None
        assert name.endswith('.eth')
        assert name.lower() == 'vitalik.eth'

    @pytest.mark.asyncio
    async def test_lookup_address_invalid(self):
        """Test reverse lookup with invalid address."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Invalid addresses should return None (or handle gracefully)
        assert await client.lookup_address('') is None
        assert await client.lookup_address('invalid') is None
        # Note: Short addresses like 0x123 cause API errors, which we handle gracefully
        result = await client.lookup_address('0x123')
        # Should either return None or handle the error
        assert result is None or isinstance(result, str)

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Forward resolution requires PROXY_ETH_CALL which BlockScout V2 doesn't support"
    )
    async def test_caching_forward_resolution(self):
        """Test that forward resolution uses cache."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # First resolution (cache miss)
        address1 = await client.resolve_name('vitalik.eth')

        # Second resolution (cache hit - should be instant)
        address2 = await client.resolve_name('vitalik.eth')

        assert address1 == address2
        assert address1 is not None

    @pytest.mark.asyncio
    async def test_caching_reverse_lookup(self):
        """Test that reverse lookup uses cache."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        addr = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

        # First lookup (cache miss)
        name1 = await client.lookup_address(addr)

        # Second lookup (cache hit)
        name2 = await client.lookup_address(addr)

        assert name1 == name2
        assert name1 is not None

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Forward resolution requires PROXY_ETH_CALL which BlockScout V2 doesn't support"
    )
    async def test_caching_bidirectional(self):
        """Test that caching works bidirectionally."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Resolve forward
        address = await client.resolve_name('vitalik.eth')
        assert address is not None

        # Reverse lookup should hit cache
        name = await client.lookup_address(address)
        assert name == 'vitalik.eth'

        # Forward resolution should still hit cache
        address2 = await client.resolve_name('vitalik.eth')
        assert address2 == address

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Forward resolution requires PROXY_ETH_CALL which BlockScout V2 doesn't support"
    )
    async def test_batch_resolve_names(self):
        """Test batch resolution of multiple names."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        names = ['vitalik.eth', 'uniswap.eth', 'invalid.eth']
        result = await client.resolve_names(names)

        # Should get dict with successful resolutions
        assert isinstance(result, dict)
        assert 'vitalik.eth' in result
        assert result['vitalik.eth'].startswith('0x')

        # Invalid names might not be in result
        # (depends on whether they exist)

    @pytest.mark.asyncio
    async def test_batch_lookup_addresses(self):
        """Test batch reverse lookup of multiple addresses."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        addresses = [
            '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',  # vitalik.eth
            '0x0000000000000000000000000000000000000000',  # zero address
        ]
        result = await client.lookup_addresses(addresses)

        # Should get dict with successful lookups
        assert isinstance(result, dict)
        # At least vitalik should be found
        assert any('vitalik' in name.lower() for name in result.values())

    @pytest.mark.asyncio
    async def test_ens_property_lazy_initialization(self):
        """Test that ENS resolver is lazy-initialized."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Should be None initially
        assert client._ens_resolver is None

        # Access property should initialize it
        resolver = client.ens
        assert resolver is not None
        assert isinstance(resolver, ENSResolver)

        # Second access should return same instance
        resolver2 = client.ens
        assert resolver2 is resolver

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Forward resolution requires PROXY_ETH_CALL which BlockScout V2 doesn't support"
    )
    async def test_ens_cache_disable(self):
        """Test ENS resolver with caching disabled."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Create resolver with caching disabled
        from aiochainscan.services.ens_resolver import ENSResolver

        resolver = ENSResolver(client, enable_cache=False)
        assert resolver._cache is None

        # Should still work, just without caching
        address = await resolver.resolve_name('vitalik.eth')
        assert address is not None

    @pytest.mark.asyncio
    async def test_ens_cache_clear(self):
        """Test clearing ENS cache."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Populate cache via reverse lookup (which works)
        await client.lookup_address('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')

        # Clear cache
        await client.ens.clear_cache()

        # Should still work (will fetch again)
        name = await client.lookup_address('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
        assert name is not None

    @pytest.mark.asyncio
    async def test_namehash_calculation(self):
        """Test ENS namehash calculation."""
        from aiochainscan.services.ens_resolver import ENSResolver

        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
        resolver = ENSResolver(client)

        # Test known namehash
        # vitalik.eth namehash (can be verified independently)
        namehash = resolver._namehash('vitalik.eth')
        assert len(namehash) == 64  # 32 bytes as hex
        assert all(c in '0123456789abcdef' for c in namehash)

        # Empty name should give zero hash
        zero_hash = resolver._namehash('')
        assert zero_hash == '0' * 64

    @pytest.mark.asyncio
    async def test_checksum_address(self):
        """Test EIP-55 checksum address conversion."""
        from aiochainscan.services.ens_resolver import ENSResolver

        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
        resolver = ENSResolver(client)

        # Test known checksum address
        lowercase = '0xd8da6bf26964af9d7eed9e03e53415d37aa96045'
        checksum = resolver._to_checksum_address(lowercase)

        # Should have mixed case
        assert checksum != lowercase
        assert checksum.lower() == lowercase
        assert checksum.startswith('0x')

        # Should be EIP-55 compliant (vitalik.eth)
        assert checksum == '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

    @pytest.mark.asyncio
    async def test_string_decode(self):
        """Test ABI string decoding."""
        from aiochainscan.services.ens_resolver import ENSResolver

        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
        resolver = ENSResolver(client)

        # Test decoding valid string response
        # Format: offset(32) + length(32) + data
        # "vitalik.eth" = 11 bytes
        hex_str = '0x' + '0' * 64  # offset
        hex_str += '000000000000000000000000000000000000000000000000000000000000000b'  # length=11
        hex_str += '766974616c696b2e657468'  # "vitalik.eth"
        hex_str += '0' * (64 - 22)  # padding

        decoded = resolver._decode_string(hex_str)
        assert decoded == 'vitalik.eth'

        # Test empty string
        assert resolver._decode_string('0x') is None

        # Test invalid format
        assert resolver._decode_string('0x1234') is None

    def test_sync_construction_has_no_background_coroutine(self):
        client = UnitENSClient()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            resolver = ENSResolver(client, cache=InMemoryCache())

        assert resolver._cache is not None
        assert not [warning for warning in caught if issubclass(warning.category, RuntimeWarning)]

    @pytest.mark.asyncio
    async def test_cold_cache_resolve_name_uses_live_contract_calls(self):
        """A completely cold cache resolves via live contract calls alone."""
        stubbed = to_checksum_address('0x1111111111111111111111111111111111111111')
        client = UnitENSClient()
        stub_ens_contract_calls(client, resolved_address=stubbed)
        resolver = ENSResolver(client, cache=InMemoryCache())

        assert await resolver.resolve_name('vitalik.eth') == stubbed
        # Exactly the two eth_calls the contract path makes: registry + resolver.
        assert client.call.await_count == 2

    @pytest.mark.asyncio
    async def test_batch_resolves_case_variants_with_one_lookup_each(self):
        """Case-variant spellings dedup to one live lookup; every spelling answered."""
        stubbed = to_checksum_address('0x2222222222222222222222222222222222222222')
        client = UnitENSClient()
        stub_ens_contract_calls(client, resolved_address=stubbed)
        resolver = ENSResolver(client, enable_cache=False)

        result = await resolver.resolve_names(['vitalik.eth', 'VITALIK.eth', 'uniswap.eth'])

        # Two unique names x (registry + resolver) eth_calls — one lookup per name.
        assert client.call.await_count == 4
        assert result == {
            'vitalik.eth': stubbed,
            'VITALIK.eth': stubbed,
            'uniswap.eth': stubbed,
        }

    @pytest.mark.asyncio
    async def test_batch_resolve_is_deduplicated_and_bounded(self, monkeypatch):
        resolver = ENSResolver(UnitENSClient(), enable_cache=False)
        active = 0
        maximum = 0
        calls: list[str] = []

        async def resolve(name: str) -> str:
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            calls.append(name)
            await asyncio.sleep(0)
            active -= 1
            return f'address:{name}'

        monkeypatch.setattr(resolver, '_safe_resolve', resolve)
        names = [f'name-{index}.eth' for index in range(BATCH_DEFAULT_CONCURRENCY + 2)]
        names.extend([names[0], names[1]])

        result = await resolver.resolve_names(names)

        assert len(calls) == BATCH_DEFAULT_CONCURRENCY + 2
        assert maximum <= BATCH_DEFAULT_CONCURRENCY
        assert result[names[0]] == f'address:{names[0]}'

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'name',
        ['', 'not-ens-name.com', 'a' * (ENS_MAX_NAME_LENGTH + 1) + '.eth'],
    )
    async def test_overlong_or_invalid_name_does_not_call_provider(self, name):
        client = UnitENSClient()
        resolver = ENSResolver(client, enable_cache=False)

        assert await resolver.resolve_name(name) is None
        client.call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_address_does_not_build_reverse_lookup(self):
        client = UnitENSClient()
        scanner = UnitAddressInfoScanner('valid.eth')
        resolver = ENSResolver(client, address_info_scanner=scanner, enable_cache=False)

        assert await resolver.lookup_address('0x123') is None
        scanner.get_address_info.assert_not_awaited()
        client.call.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'metadata', ['not-an-ens-name', 'a' * (ENS_MAX_NAME_LENGTH + 1) + '.eth']
    )
    async def test_invalid_scanner_metadata_is_ignored(self, metadata):
        client = UnitENSClient()
        scanner = UnitAddressInfoScanner(metadata)
        resolver = ENSResolver(client, address_info_scanner=scanner, enable_cache=False)

        result = await resolver.lookup_address('0x1111111111111111111111111111111111111111')

        assert result is None
        scanner.get_address_info.assert_awaited_once()
        client.call.assert_awaited()


@pytest.mark.integration
class TestENSIntegration:
    """Integration tests requiring actual API calls."""

    @pytest.mark.asyncio
    async def test_blockscout_v2_ens_integration(self):
        """Test ENS integration with BlockScout V2."""
        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Test reverse lookup via BlockScout V2 address info
        name = await client.lookup_address('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')

        # Should get vitalik.eth from BlockScout
        assert name is not None
        assert name.lower() == 'vitalik.eth'

    @pytest.mark.asyncio
    @pytest.mark.skip(reason='Requires Etherscan API key and eth_call support')
    async def test_etherscan_ens_fallback(self):
        """Test ENS contract fallback with Etherscan."""
        # This test requires PROXY_ETH_CALL support
        client = ChainscanClient.from_config('etherscan', 'ethereum')

        # Should use ENS contract calls as fallback
        address = await client.resolve_name('vitalik.eth')
        assert address is not None
        assert address.lower() == '0xd8da6bf26964af9d7eed9e03e53415d37aa96045'


@pytest.mark.benchmark
class TestENSPerformance:
    """Performance tests for ENS resolver."""

    @pytest.mark.asyncio
    async def test_batch_resolution_performance(self):
        """Test batch resolution is faster than sequential."""
        import time

        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        names = ['vitalik.eth', 'uniswap.eth', 'ens.eth']

        # Clear cache first
        await client.ens.clear_cache()

        # Batch resolution
        start = time.time()
        result = await client.resolve_names(names)
        batch_time = time.time() - start

        print(f'Batch resolution took {batch_time:.2f}s')
        print(f'Resolved {len(result)} names')

        # Should complete in reasonable time
        assert batch_time < 30  # 30 seconds max for 3 names

    @pytest.mark.asyncio
    async def test_cache_performance(self):
        """Test that cache significantly improves performance."""
        import time

        client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

        # Clear cache
        await client.ens.clear_cache()

        # First resolution (cache miss)
        start = time.time()
        await client.resolve_name('vitalik.eth')
        first_time = time.time() - start

        # Second resolution (cache hit)
        start = time.time()
        await client.resolve_name('vitalik.eth')
        cached_time = time.time() - start

        print(f'First resolution: {first_time:.4f}s')
        print(f'Cached resolution: {cached_time:.4f}s')

        # Cached should be much faster (at least 10x)
        assert cached_time < first_time / 10
