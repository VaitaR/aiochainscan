"""
Demonstration of the new unified ChainscanClient architecture.

This example shows how the new architecture provides a single interface
for accessing different blockchain scanner APIs with logical method calls.
"""

import asyncio
import os

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method


async def demo_unified_client():
    """
    Demonstrate the unified client functionality.
    """
    print("🚀 Unified ChainscanClient Architecture Demo\n")

    # Demo 1: Show available scanners and their capabilities
    print("📋 Available Scanner Implementations:")
    capabilities = ChainscanClient.list_scanner_capabilities()

    for scanner_id, info in capabilities.items():
        print(f"  {scanner_id}:")
        print(f"    Name: {info['name']} v{info['version']}")
        print(f"    Networks: {', '.join(info['networks'])}")
        print(f"    Authentication: {info['auth_mode']} ({info['auth_field']})")
        print(f"    Methods: {info['method_count']} supported")
        print()

    # Demo 2: Create clients for different scanners using config system
    print("🔑 Creating Clients via Configuration System:")

    # Check if we have API keys available
    eth_key = os.getenv('ETHERSCAN_KEY')

    if eth_key:
        print("✅ Creating Etherscan client...")
        try:
            eth_client = ChainscanClient.from_config(
                scanner_name='etherscan',
                scanner_version='v1',
                scanner_id='eth',
                network='main'
            )
            print(f"   {eth_client}")
            print(f"   Currency: {eth_client.currency}")
            print(f"   Supported methods: {len(eth_client.get_supported_methods())}")

            # Demo method call
            print("   Testing ACCOUNT_BALANCE method...")
            try:
                # Use a known address with balance
                balance = await eth_client.call(
                    Method.ACCOUNT_BALANCE,
                    address='0x742d35Cc6634C0532925a3b8D9Fa7a3D91'
                )
                print(f"   ✅ Balance: {balance} wei")
            except Exception as e:
                print(f"   ⚠️  API call failed (expected in demo): {e}")

            await eth_client.close()

        except Exception as e:
            print(f"   ❌ Failed to create Etherscan client: {e}")
    else:
        print("❌ ETHERSCAN_KEY not found - skipping Etherscan demo")

    # Demo 3: Show method compatibility across scanners
    print("\n🔍 Method Support Comparison:")

    test_methods = [
        Method.ACCOUNT_BALANCE,
        Method.ACCOUNT_TRANSACTIONS,
        Method.TX_BY_HASH,
        Method.BLOCK_BY_NUMBER,
        Method.CONTRACT_ABI,
        Method.TOKEN_BALANCE,
        Method.GAS_ORACLE,
        Method.EVENT_LOGS,
    ]

    print(f"{'Method':<25} {'Etherscan v1':<15} {'OKLink v1':<15}")
    print("-" * 55)

    for method in test_methods:
        etherscan_support = "✅" if method in capabilities.get('etherscan_v1', {}).get('supported_methods', []) else "❌"
        oklink_support = "✅" if method in capabilities.get('oklink_v1', {}).get('supported_methods', []) else "❌"

        method_name = str(method).replace('Method.', '')
        print(f"{method_name:<25} {etherscan_support:<15} {oklink_support:<15}")

    # Demo 4: Direct client instantiation
    print("\n🔧 Direct Client Instantiation:")
    print("You can also create clients directly without the config system:")
    print("""
    client = ChainscanClient(
        scanner_name='etherscan',
        scanner_version='v1',
        api_kind='eth',
        network='main',
        api_key='your_api_key_here'
    )
    """)

    # Demo 5: Show unified method calling pattern
    print("📡 Unified Method Calling Pattern:")
    print("""
    # Same method call works across different scanners:

    # Etherscan format
    balance = await eth_client.call(Method.ACCOUNT_BALANCE, address='0x...')

    # OKLink format (parameters automatically mapped)
    balance = await oklink_client.call(Method.ACCOUNT_BALANCE, address='0x...')

    # Different scanners, same logical operation, same client code!
    """)

    print("✨ Demo completed! The unified architecture provides:")
    print("  • Single interface for multiple scanner APIs")
    print("  • Automatic parameter mapping and response parsing")
    print("  • Type-safe method definitions")
    print("  • Integration with existing configuration system")
    print("  • Backward compatibility with legacy Client class")


async def demo_method_enum():
    """Demonstrate Method enum functionality."""
    print("\n📚 Method Enum Demonstration:")

    print("Available logical methods:")
    for method in Method:
        print(f"  {method.name:<25} → {str(method)}")

    print(f"\nTotal methods defined: {len(Method)}")


async def demo_error_handling():
    """Demonstrate error handling in the unified client."""
    print("\n⚠️  Error Handling Demonstration:")

    try:
        # Try to create client with unknown scanner
        ChainscanClient(
            scanner_name='unknown_scanner',
            scanner_version='v1',
            api_kind='eth',
            network='main',
            api_key='fake_key'
        )
    except ValueError as e:
        print(f"✅ Caught expected error for unknown scanner: {e}")

    try:
        # Try to create Etherscan client with unsupported network
        ChainscanClient(
            scanner_name='etherscan',
            scanner_version='v1',
            api_kind='eth',
            network='unsupported_network',
            api_key='fake_key'
        )
    except ValueError as e:
        print(f"✅ Caught expected error for unsupported network: {e}")


if __name__ == "__main__":
    asyncio.run(demo_unified_client())
    asyncio.run(demo_method_enum())
    asyncio.run(demo_error_handling())
