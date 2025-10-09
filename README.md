# aiochainscan

**Async Python wrapper for blockchain explorer APIs with unified ChainscanClient interface.**

Provides a single, consistent API for accessing blockchain data across multiple scanners (Etherscan, BlockScout, Moralis, etc.) with logical method calls and automatic scanner management.

[![CI/CD](https://github.com/VaitaR/aiochainscan/actions/workflows/ci.yml/badge.svg)](https://github.com/VaitaR/aiochainscan/actions/workflows/ci.yml)

## Features

- **🆕 Unified ChainscanClient** - Single interface for all blockchain scanners with logical method calls
- **🔄 Easy Scanner Switching** - Switch between Etherscan, BlockScout, Moralis, etc. with one config change
- **📡 Real-time Blockchain Data** - Access to 15+ networks including Ethereum, BSC, Polygon, Arbitrum, Optimism, Base
- **⚡ Built-in Rate Limiting** - Automatic throttling with configurable limits and retry policies
- **🎯 Comprehensive API Coverage** - 17+ blockchain operations (balance, transactions, logs, blocks, contracts, tokens)
- **🔒 Type-safe Operations** - Typed data transfer objects and method enums for stable API responses
- **🚀 Optimized Bulk Operations** - High-performance range-splitting aggregators for large datasets
- **🧩 Dependency Injection** - Configurable HTTP clients, caching, telemetry, and rate limiters

## Supported Networks

**Etherscan API**: Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, Fantom, Gnosis, and more EVM chains (Base supported via Etherscan V2)
**Blockscout**: Public blockchain explorers (no API key needed) - Sepolia, Gnosis, Polygon, and others
**Moralis**: Multi-chain Web3 API - Ethereum, BSC, Polygon, Arbitrum, Base, Optimism, Avalanche

## Installation

```sh
# From GitHub (current method)
pip install git+https://github.com/VaitaR/aiochainscan.git

# Or clone and install
git clone https://github.com/VaitaR/aiochainscan.git
cd aiochainscan
pip install .
```

**Verify installation:**
```python
import aiochainscan
print(f"aiochainscan v{aiochainscan.__version__}")

from aiochainscan import get_balance, get_block
print("✓ Installation successful!")
```

## Quick Start

### 1. Unified ChainscanClient (Recommended)

The **ChainscanClient** provides a unified interface for all blockchain scanners with logical method calls:

```python
import asyncio
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

async def main():
    # Create client for any scanner using simple config
    client = ChainscanClient.from_config(
        'blockscout',                   # Provider name (version defaults to 'v1')
        'ethereum'                      # Chain name/ID
    )

    # Use logical methods - scanner details hidden under the hood
    balance = await client.call(Method.ACCOUNT_BALANCE, address='0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3')
    print(f"Balance: {balance} wei ({int(balance) / 10**18:.6f} ETH)")

    # Switch to Etherscan easily (requires API key)
    client = ChainscanClient.from_config(
        'etherscan',                    # Provider name (version defaults to 'v2')
        'ethereum'                      # Chain name
    )
    block = await client.call(Method.BLOCK_BY_NUMBER, block_number='latest')
    print(f"Latest block: #{block['number']}")

    # Use Base network through Etherscan (requires ETHERSCAN_KEY)
    client = ChainscanClient.from_config(
        'etherscan',                    # Same provider (version defaults to 'v2')
        'base'                          # Chain name
    )
    balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
    print(f"Base balance: {balance} wei")

    # Same interface for any scanner!
    await client.close()

asyncio.run(main())
```

### 2. Legacy Facade Functions

For simple use cases, you can also use the legacy facade functions (maintained for backward compatibility):

```python
import asyncio
from aiochainscan import get_balance, get_block

async def main():
    # BlockScout (free, no API key needed)
    balance = await get_balance(
        address='0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3',
        api_kind='blockscout_sepolia',
        network='sepolia',
        api_key=''
    )

    # Etherscan (requires API key)
    block = await get_block(
        tag=17000000,
        api_kind='eth',
        network='main',
        api_key='YOUR_ETHERSCAN_API_KEY'
    )

    print(f"Balance: {balance} wei")
    print(f"Block: #{block['block_number']}")

asyncio.run(main())
```

### 2. Optimized Bulk Operations

```python
import asyncio
from aiochainscan import get_all_transactions_optimized

async def main():
    # Fetch all transactions for an address efficiently
    # Uses range splitting and respects rate limits
    transactions = await get_all_transactions_optimized(
        address='0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3',
        api_kind='blockscout_sepolia',  # Works with Blockscout too
        network='sepolia',
        api_key='',
        max_concurrent=5,  # Parallel requests
        max_offset=10000   # Max results per request
    )

    print(f"Found {len(transactions)} transactions")

asyncio.run(main())
```

## Advanced Usage

### ChainscanClient with Custom Configuration

For advanced use cases with custom rate limiting, retries, and dependency injection:

```python
import asyncio
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method
from aiochainscan.adapters.simple_rate_limiter import SimpleRateLimiter
from aiochainscan.adapters.retry_exponential import ExponentialBackoffRetry

async def main():
    # Create custom rate limiter and retry policy
    rate_limiter = SimpleRateLimiter(requests_per_second=1)
    retry_policy = ExponentialBackoffRetry(attempts=3)

    # Create client with custom configuration
    client = ChainscanClient(
        scanner_name='etherscan',      # Provider name
        scanner_version='v2',          # API version
        api_kind='eth',                # Scanner identifier
        network='main',                # Network name
        api_key='YOUR_ETHERSCAN_API_KEY',
        throttler=rate_limiter,        # Custom rate limiter
        retry_options=retry_policy     # Custom retry policy
    )

    try:
        # Use logical methods with automatic routing
        balance = await client.call(
            Method.ACCOUNT_BALANCE,
            address="0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3"
        )

        # Get transaction history
        transactions = await client.call(
            Method.ACCOUNT_TRANSACTIONS,
            address="0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3",
            page=1,
            offset=100
        )

        print(f"Balance: {balance} wei")
        print(f"Recent transactions: {len(transactions)}")

    finally:
        await client.close()

asyncio.run(main())
```

### Easy Scanner Switching with ChainscanClient

The **ChainscanClient** makes it trivial to switch between different blockchain scanners:

```python
import asyncio
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

async def check_multi_scanner_balance():
    address = "0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3"

    # Same code works with any scanner - just change config!
    scanners = [
        # BlockScout (free, no API key needed)
        ('blockscout', 'v1', 'eth', ''),

        # Etherscan (requires API key)
        ('etherscan', 'v2', 'eth', 'YOUR_ETHERSCAN_API_KEY'),

        # Moralis (requires API key)
        ('moralis', 'v1', 'eth', 'YOUR_MORALIS_API_KEY'),
    ]

    for scanner_name, version, network, api_key in scanners:
        try:
            client = ChainscanClient.from_config(
                scanner_name=scanner_name,
                scanner_version=version,
                network=network
            )

            # Same method call for all scanners!
            balance = await client.call(Method.ACCOUNT_BALANCE, address=address)

            if balance and str(balance).isdigit():
                eth_balance = int(balance) / 10**18
                print(f"✅ {scanner_name}: {eth_balance:.6f} ETH")
            else:
                print(f"⚠️  {scanner_name}: {balance}")

            await client.close()

        except Exception as e:
            print(f"❌ {scanner_name}: {e}")

asyncio.run(check_multi_scanner_balance())
```

### Legacy Multiple Networks (Facade Functions)

For simple cases, you can still use the legacy facade functions:

```python
import asyncio
from aiochainscan import get_balance

async def check_balances():
    # Works with multiple scanners using legacy interface
    networks = [
        ('blockscout_sepolia', 'sepolia', ''),          # Blockscout (free)
        ('eth', 'main', 'YOUR_ETHERSCAN_KEY'),          # Etherscan
        ('moralis', 'eth', 'YOUR_MORALIS_KEY'),         # Moralis
    ]

    for api_kind, network, api_key in networks:
        balance = await get_balance(
            address="0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3",
            api_kind=api_kind,
            network=network,
            api_key=api_key
        )
        print(f"{api_kind} {network}: {balance} wei")

asyncio.run(check_balances())
```

### Environment Variables

Set API keys as environment variables:

```bash
export ETHERSCAN_KEY="your_etherscan_api_key"
export MORALIS_API_KEY="your_moralis_api_key"
# Blockscout and some networks work without API keys
```

## Configuration Parameters

When using `ChainscanClient.from_config()`, you need to specify three key parameters:

- **scanner_name**: Provider name (`'etherscan'`, `'blockscout'`, `'moralis'`, etc.)
- **scanner_version**: API version (`'v1'`, `'v2'`)
- **network**: Chain name/ID (`'eth'`, `'ethereum'`, `1`, `'base'`, `8453`, etc.)

### Common Configurations:

| Provider | scanner_name | default_version | network | API Key |
|----------|-------------|-----------------|---------|---------|
| **BlockScout Ethereum** | `'blockscout'` | `v1` | `'ethereum'` | ❌ Not required |
| **BlockScout Polygon** | `'blockscout'` | `v1` | `'polygon'` | ❌ Not required |
| **Etherscan Ethereum** | `'etherscan'` | `v2` | `'ethereum'` | ✅ `ETHERSCAN_KEY` |
| **Etherscan Base** | `'etherscan'` | `v2` | `'base'` | ✅ `ETHERSCAN_KEY` |
| **Moralis Ethereum** | `'moralis'` | `v1` | `'ethereum'` | ✅ `MORALIS_API_KEY` |

**Network parameter supports both names and chain IDs:**
- `'ethereum'`, `'eth'`, `1` - Ethereum
- `'base'`, `8453` - Base
- `'polygon'`, `'matic'` - Polygon
- `'bsc'`, `'binance'`, `56` - Binance Smart Chain

## Available Interfaces

The library provides two main interfaces for accessing blockchain data:

### 1. ChainscanClient (Recommended)

The **unified client** provides a single interface for all blockchain scanners with logical method calls:

```python
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

# Create client for any scanner (versions default automatically)
client = ChainscanClient.from_config('blockscout', 'ethereum')  # v1 default

# Use logical methods - scanner details hidden
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
logs = await client.call(Method.EVENT_LOGS, address='0x...', **params)
block = await client.call(Method.BLOCK_BY_NUMBER, block_number='latest')

# Easy scanner switching - same interface!
client = ChainscanClient.from_config('etherscan', 'ethereum')  # v2 default
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
```

**Key Methods Available:**
- `ACCOUNT_BALANCE` - Get account balance
- `ACCOUNT_TRANSACTIONS` - Get account transaction history
- `ACCOUNT_INTERNAL_TXS` - Get internal transactions
- `BLOCK_BY_NUMBER` - Get block information
- `TX_BY_HASH` - Get transaction details
- `EVENT_LOGS` - Get contract event logs
- `TOKEN_BALANCE` - Get ERC-20 token balance
- `CONTRACT_ABI` - Get contract ABI
- And more methods (17 total for full-featured scanners)

### 2. Legacy Facade Functions

For simple use cases, the library also provides legacy facade functions (maintained for backward compatibility):

- `get_balance()` - Get account balance
- `get_block()` - Get block information
- `get_transaction()` - Get transaction details
- `get_eth_price()` - Get ETH/USD price
- `get_all_transactions_optimized()` - Fetch all transactions efficiently

All interfaces support dependency injection for customizing HTTP clients, rate limiters, retries, and caching.

## Error Handling

```python
import asyncio
from aiochainscan.exceptions import ChainscanClientApiError

async def main():
    try:
        balance = await get_balance(
            address='0x...',
            api_kind='eth',
            network='main',
            api_key='YOUR_API_KEY'
        )
    except ChainscanClientApiError as e:
        print(f"API Error: {e}")

asyncio.run(main())
```
