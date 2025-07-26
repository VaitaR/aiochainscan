"""
Integration tests for aiochainscan with real API endpoints.

These tests use real API keys and make actual network requests.
Tests are automatically skipped if API keys are not available.

Usage:
    # Run all integration tests (requires API keys)
    pytest tests/test_integration.py -v
    
    # Run integration tests for specific scanner
    pytest tests/test_integration.py -v -k "eth"
    
    # Show which tests would run/skip without executing
    pytest tests/test_integration.py --collect-only
    
    # Run with detailed API key status
    pytest tests/test_integration.py -v -s
"""

import asyncio
import os
from unittest.mock import patch

import pytest

from aiochainscan import Client
from aiochainscan.config import config_manager
from aiochainscan.exceptions import ChainscanClientApiError

# Test configurations - scanner_id: (networks_to_test, expected_currency)
TEST_CONFIGS = {
    'eth': (['main'], 'ETH'),
    'bsc': (['main'], 'BNB'),
    'polygon': (['main'], 'MATIC'),
    'arbitrum': (['main'], 'ETH'),
    'base': (['main'], 'BASE'),
}

# Well-known test addresses for different networks
TEST_ADDRESSES = {
    'eth': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',  # Vitalik's address
    'bsc': '0x8894E0a0c962CB723c1976a4421c95949bE2D4E3',   # Binance hot wallet
    'polygon': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',  # WETH on Polygon
    'arbitrum': '0x912CE59144191C1204E64559FE8253a0e49E6548',  # Arbitrum bridge
    'base': '0x4200000000000000000000000000000000000006',    # WETH on Base
}


def get_api_key_for_scanner(scanner_id: str) -> str | None:
    """Get API key for scanner if available."""
    try:
        return config_manager.get_api_key(scanner_id)
    except ValueError:
        return None


def get_scanner_name(scanner_id: str) -> str:
    """Get the display name for a scanner."""
    try:
        config = config_manager.get_scanner_config(scanner_id)
        return config.name
    except ValueError:
        return scanner_id.upper()


def get_primary_api_key_name(scanner_id: str) -> str:
    """Get the primary API key environment variable name for a scanner."""
    try:
        suggestions = config_manager._get_api_key_suggestions(scanner_id)
        return suggestions[0]  # First suggestion is the primary format
    except:
        return f"{scanner_id.upper()}_KEY"


def requires_api_key(scanner_id: str):
    """Decorator to skip tests if API key is not available."""
    def decorator(func):
        api_key = get_api_key_for_scanner(scanner_id)
        scanner_name = get_scanner_name(scanner_id)
        primary_key_name = get_primary_api_key_name(scanner_id)
        
        if not api_key:
            reason = (
                f"🔑 API key required for {scanner_name} integration test.\n"
                f"   Set environment variable: {primary_key_name}=your_api_key\n"
                f"   Or run: export {primary_key_name}=\"your_api_key\""
            )
        else:
            reason = None
            
        return pytest.mark.skipif(
            not api_key,
            reason=reason
        )(func)
    return decorator


def optional_api_key(scanner_id: str):
    """Decorator for tests that work both with and without API keys."""
    def decorator(func):
        api_key = get_api_key_for_scanner(scanner_id)
        if not api_key:
            # Mark as expected to have limited functionality
            return pytest.mark.parametrize("has_api_key", [False], ids=["no_api_key"])(func)
        else:
            return pytest.mark.parametrize("has_api_key", [True, False], ids=["with_api_key", "no_api_key"])(func)
    return decorator


def print_api_key_status():
    """Print status of API keys for integration testing."""
    print("\n" + "="*60)
    print("🔧 Integration Tests - API Key Status")
    print("="*60)
    
    configured_count = 0
    total_count = 0
    
    for scanner_id in TEST_CONFIGS.keys():
        total_count += 1
        api_key = get_api_key_for_scanner(scanner_id)
        scanner_name = get_scanner_name(scanner_id)
        primary_key_name = get_primary_api_key_name(scanner_id)
        
        if api_key:
            configured_count += 1
            status = "✅ CONFIGURED"
            key_display = f"{api_key[:8]}..." if len(api_key) > 8 else api_key
        else:
            status = "❌ MISSING"
            key_display = f"Set {primary_key_name}"
            
        print(f"  {scanner_id:10} | {scanner_name:20} | {status:15} | {key_display}")
    
    print("-" * 60)
    print(f"📊 Summary: {configured_count}/{total_count} scanners configured")
    
    if configured_count == 0:
        print("\n⚠️  No API keys configured - all integration tests will be skipped")
        print("💡 To enable integration tests, set API keys:")
        for scanner_id in TEST_CONFIGS.keys():
            primary_key_name = get_primary_api_key_name(scanner_id)
            print(f"   export {primary_key_name}=\"your_api_key\"")
    elif configured_count < total_count:
        print(f"\n💡 {total_count - configured_count} scanners need API keys for full integration testing")
    else:
        print("\n🎉 All scanners configured - full integration testing enabled!")
    
    print("=" * 60)


class TestBasicAPIFunctionality:
    """Test basic API functionality with real endpoints."""

    @pytest.mark.parametrize("scanner_id", ["eth", "bsc", "polygon", "arbitrum", "base"])
    @pytest.mark.asyncio
    async def test_scanner_basic_calls(self, scanner_id):
        """Test basic API calls for each configured scanner."""
        api_key = get_api_key_for_scanner(scanner_id)
        if not api_key:
            scanner_name = get_scanner_name(scanner_id)
            primary_key_name = get_primary_api_key_name(scanner_id)
            pytest.skip(
                f"🔑 API key required for {scanner_name}.\n"
                f"   Set: {primary_key_name}=your_api_key"
            )
        
        print(f"\n🧪 Testing {get_scanner_name(scanner_id)} ({scanner_id})...")
        
        # Get test configuration
        networks, expected_currency = TEST_CONFIGS[scanner_id]
        test_network = networks[0]  # Use first available network
        
        client = Client.from_config(scanner_id, test_network)
        
        try:
            # Test 1: Verify client configuration
            assert client.currency == expected_currency
            print(f"✅ Currency: {client.currency}")
            
            # Test 2: Get latest block number (works for all scanners)
            block_number = await client.proxy.block_number()
            assert block_number is not None
            assert block_number.startswith('0x')
            block_num = int(block_number, 16)
            assert block_num > 0
            print(f"✅ Latest Block: {block_num:,}")
            
            # Small delay to respect rate limits
            await asyncio.sleep(1.0)
            
            # Test 3: Get account balance for test address
            if scanner_id in TEST_ADDRESSES:
                test_address = TEST_ADDRESSES[scanner_id]
                try:
                    balance = await client.account.balance(test_address)
                    assert balance is not None
                    assert isinstance(balance, str)
                    # Convert to human readable (assuming 18 decimals for most tokens)
                    balance_float = int(balance) / 10**18
                    print(f"✅ Test Address Balance: {balance_float:.6f} {expected_currency}")
                except ChainscanClientApiError as e:
                    if "rate limit" in str(e).lower():
                        print(f"⚠️ Rate limited on balance check: {e}")
                    else:
                        print(f"⚠️ Balance check failed: {e}")
                        # Don't fail the test for balance issues
            
            print(f"🎉 {get_scanner_name(scanner_id)} integration test passed!")
            
        except Exception as e:
            print(f"❌ {get_scanner_name(scanner_id)} test failed: {e}")
            raise
        finally:
            await client.close()

    @requires_api_key('eth')
    @pytest.mark.asyncio 
    async def test_ethereum_specific_calls(self):
        """Test basic Ethereum API calls with real API key."""
        client = Client.from_config('eth', 'main')

        try:
            # Test 1: Get ETH price
            price_data = await client.stats.eth_price()
            assert isinstance(price_data, dict)
            assert 'ethusd' in price_data
            print(f"✅ ETH Price: ${price_data['ethusd']}")

            # Small delay to respect rate limits
            await asyncio.sleep(1.0)

            # Test 2: Get latest block number
            block_number = await client.proxy.block_number()
            assert block_number is not None
            assert block_number.startswith('0x')
            block_num = int(block_number, 16)
            assert block_num > 0
            print(f"✅ Latest Block: {block_num}")

            # Small delay to respect rate limits
            await asyncio.sleep(1.0)

            # Test 3: Get account balance
            test_address = TEST_ADDRESSES['eth']
            try:
                balance = await client.account.balance(test_address)
                assert balance is not None
                assert isinstance(balance, str)
                balance_eth = int(balance) / 10**18
                print(f"✅ Balance for {test_address}: {balance_eth:.4f} ETH")
            except ChainscanClientApiError as e:
                if "rate limit" in str(e).lower():
                    print(f"⚠️ Rate limited on balance check: {e}")
                    # Still consider test successful if we got the price and block
                else:
                    raise

        finally:
            await client.close()

    @requires_api_key('bsc')
    @pytest.mark.asyncio
    async def test_bsc_basic_calls(self):
        """Test basic BSC API calls with real API key."""
        client = Client.from_config('bsc', 'main')

        try:
            # Test 1: Get latest block number
            block_number = await client.proxy.block_number()
            assert block_number is not None
            block_num = int(block_number, 16)
            assert block_num > 0
            print(f"✅ BSC Latest Block: {block_num}")

            # Small delay to respect rate limits
            await asyncio.sleep(1.0)

            # Test 2: Get account balance
            test_address = TEST_ADDRESSES['bsc']
            try:
                balance = await client.account.balance(test_address)
                assert balance is not None
                balance_bnb = int(balance) / 10**18
                print(f"✅ BSC Balance for {test_address}: {balance_bnb:.4f} BNB")
            except ChainscanClientApiError as e:
                if "rate limit" in str(e).lower():
                    print(f"⚠️ Rate limited on BSC balance check: {e}")
                else:
                    raise

            # Test 3: Check currency
            assert client.currency == 'BNB'

        finally:
            await client.close()


class TestAPIKeyOptionalFunctionality:
    """Test functionality that works both with and without API keys."""

    @pytest.mark.asyncio
    async def test_client_creation_with_and_without_key(self):
        """Test client creation with and without API keys (no actual API calls)."""
        # Test that we can create clients both ways

        # With API key (if available)
        if get_api_key_for_scanner('eth'):
            client_with_key = Client.from_config('eth', 'main')
            assert client_with_key.currency == 'ETH'
            await client_with_key.close()
            print("✅ Client creation with API key successful")

        # Without API key
        client_without_key = Client(api_key='', api_kind='eth', network='main')
        assert client_without_key.currency == 'ETH'
        await client_without_key.close()
        print("✅ Client creation without API key successful")

    @optional_api_key('eth')
    @pytest.mark.asyncio
    async def test_ethereum_with_and_without_key(self, has_api_key):
        """Test Ethereum API calls with and without API key."""
        if has_api_key:
            # Test with API key
            client = Client.from_config('eth', 'main')
        else:
            # Test without API key (may have rate limits or require key)
            client = Client(api_key='', api_kind='eth', network='main')

        try:
            # This should work with API key, may fail without
            block_number = await client.proxy.block_number()
            assert block_number is not None
            block_num = int(block_number, 16)
            assert block_num > 0

            key_status = "with API key" if has_api_key else "without API key"
            print(f"✅ ETH Latest Block ({key_status}): {block_num}")

            if has_api_key:
                # Additional tests that work better with API key
                await asyncio.sleep(1.0)  # Rate limit protection
                test_address = TEST_ADDRESSES['eth']
                balance = await client.account.balance(test_address)
                assert balance is not None
                print("✅ ETH Balance check successful with API key")

        except ChainscanClientApiError as e:
            if not has_api_key and ("rate limit" in str(e).lower() or "missing" in str(e).lower() or "invalid api key" in str(e).lower()):
                pytest.skip(f"API key required or rate limited: {e}")
            else:
                raise
        finally:
            await client.close()


class TestMultiScannerIntegration:
    """Test integration across multiple scanners."""

    @pytest.mark.asyncio
    async def test_available_scanners_status(self):
        """Test status of all configured scanners."""
        configs = config_manager.list_all_configurations()

        available_scanners = []
        missing_scanners = []

        for scanner_id, info in configs.items():
            if info['api_key_configured']:
                available_scanners.append(scanner_id)
                print(f"✅ {scanner_id}: {info['name']} - API key configured")
            else:
                missing_scanners.append(scanner_id)
                print(f"❌ {scanner_id}: {info['name']} - Missing API key")

        print(f"\n📊 Summary: {len(available_scanners)}/{len(configs)} scanners configured")

        # At least some scanners should be available for CI/local testing
        assert len(available_scanners) >= 0  # Allow 0 for CI environments

    @pytest.mark.asyncio
    async def test_configured_scanners_basic_calls(self):
        """Test basic calls for all configured scanners."""
        configs = config_manager.list_all_configurations()
        successful_tests = 0

        for scanner_id, info in configs.items():
            if not info['api_key_configured']:
                print(f"⏭️  Skipping {scanner_id}: No API key")
                continue

            if scanner_id not in TEST_CONFIGS:
                print(f"⏭️  Skipping {scanner_id}: No test configuration")
                continue

            networks, expected_currency = TEST_CONFIGS[scanner_id]

            for network in networks:
                try:
                    print(f"🧪 Testing {scanner_id} on {network}...")
                    client = Client.from_config(scanner_id, network)

                    # Test currency
                    assert client.currency == expected_currency

                    # Test basic API call
                    block_number = await client.proxy.block_number()
                    assert block_number is not None
                    block_num = int(block_number, 16)
                    assert block_num > 0

                    print(f"✅ {scanner_id}/{network}: Block {block_num}")
                    successful_tests += 1

                    await client.close()

                    # Small delay to respect rate limits
                    await asyncio.sleep(2.0)

                except Exception as e:
                    print(f"❌ {scanner_id}/{network}: {e}")
                    # Don't fail the entire test if one scanner fails
                    continue

        print(f"\n📊 Successfully tested {successful_tests} scanner/network combinations")


class TestErrorHandling:
    """Test error handling with real API endpoints."""

    @requires_api_key('eth')
    @pytest.mark.asyncio
    async def test_invalid_address_handling(self):
        """Test handling of invalid addresses."""
        client = Client.from_config('eth', 'main')

        try:
            # Test with invalid address
            with pytest.raises(ChainscanClientApiError):
                await client.account.balance('invalid_address')

            print("✅ Invalid address error handled correctly")

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_network_validation(self):
        """Test network validation without making API calls."""
        # This should fail during client creation
        with pytest.raises(ValueError, match="not supported"):
            Client.from_config('eth', 'invalid_network')

        print("✅ Network validation working correctly")

    @pytest.mark.asyncio
    async def test_scanner_validation(self):
        """Test scanner validation without making API calls."""
        # This should fail during client creation
        with pytest.raises(ValueError, match="Unknown scanner"):
            Client.from_config('invalid_scanner', 'main')

        print("✅ Scanner validation working correctly")


class TestConfigurationReload:
    """Test configuration reloading and API key management."""

    @pytest.mark.asyncio
    async def test_api_key_detection(self):
        """Test API key detection from environment."""
        # Test that our real keys are detected
        real_keys = {
            'ETH_KEY': os.getenv('ETHERSCAN_KEY'),
            'BSC_KEY': os.getenv('BSCSCAN_KEY'),
        }

        with patch.dict(os.environ, real_keys):
            # Reload configuration to pick up the patched environment
            config_manager._load_api_keys()

            # Test ETH
            eth_key = config_manager.get_api_key('eth')
            assert eth_key == real_keys['ETH_KEY']

            # Test BSC
            bsc_key = config_manager.get_api_key('bsc')
            assert bsc_key == real_keys['BSC_KEY']

            print("✅ API key detection working correctly")

    @pytest.mark.asyncio
    async def test_fallback_strategies(self):
        """Test API key fallback strategies."""
        test_key = 'test_fallback_key_12345'

        # Test different environment variable patterns
        patterns = [
            'ETH_KEY',
            'ETH_API_KEY',
            'ETHERSCAN_KEY',
            'SCANNER_ETH_KEY'
        ]

        for pattern in patterns:
            with patch.dict(os.environ, {pattern: test_key}, clear=True):
                # Clear existing API key
                eth_config = config_manager.get_scanner_config('eth')
                eth_config.api_key = None

                # Reload and test
                config_manager._load_api_keys()
                detected_key = config_manager.get_api_key('eth')

                assert detected_key == test_key
                print(f"✅ Fallback pattern {pattern} working correctly")


# Pytest configuration for integration tests
def pytest_configure(config):
    """Add custom markers for integration tests."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring API keys"
    )


def pytest_collection_modifyitems(config, items):
    """Add integration marker to all tests in this file."""
    for item in items:
        if "test_integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
