# aiochainscan

Async Python wrapper for blockchain explorer APIs (Etherscan, Blockscout, Moralis, etc.).

[![CI/CD](https://github.com/VaitaR/aiochainscan/actions/workflows/ci.yml/badge.svg)](https://github.com/VaitaR/aiochainscan/actions/workflows/ci.yml)

## Features

- **Async/await support** - Built for modern Python async applications
- **Multiple blockchain support** - Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, and 10+ more networks
- **Built-in rate limiting** - Automatic throttling with configurable limits and retry policies
- **Comprehensive API coverage** - All major blockchain explorer endpoints supported
- **Type-safe DTOs** - Typed data transfer objects for stable API responses
- **Optimized bulk operations** - High-performance range-splitting aggregators for large datasets
- **Dependency injection** - Configurable HTTP clients, caching, telemetry, and rate limiters

## Supported Networks

**Etherscan API**: Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, Fantom, Gnosis, and more
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

### 1. Basic Usage

```python
import asyncio
from aiochainscan import get_balance, get_block, get_eth_price

async def main():
    # Get ETH balance (Blockscout - no API key needed)
    balance = await get_balance(
        address='0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3',
        api_kind='blockscout_sepolia',
        network='sepolia',
        api_key=''  # Not required for Blockscout
    )

    # Get block info (Etherscan - requires API key)
    block = await get_block(
        tag=17000000,
        full=False,
        api_kind='eth',
        network='main',
        api_key='YOUR_ETHERSCAN_API_KEY'
    )

    # Get ETH price
    price = await get_eth_price(
        api_kind='eth',
        network='main',
        api_key='YOUR_ETHERSCAN_API_KEY'
    )

    print(f"Balance: {balance} wei")
    print(f"Block: #{block['block_number']}")
    print(f"ETH Price: ${price['eth_usd']}")

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

### Rate Limiting & Dependency Injection

```python
import asyncio
from aiochainscan import (
    open_default_session,
    get_balance,
    SimpleRateLimiter,
    ExponentialBackoffRetry
)

async def main():
    # Open reusable session with custom rate limiting
    rate_limiter = SimpleRateLimiter(requests_per_second=1)
    retry_policy = ExponentialBackoffRetry(attempts=3)

    session = await open_default_session()
    try:
        # Use custom rate limiting
        balance = await get_balance(
            address="0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3",
            api_kind="eth",
            network="main",
            api_key="YOUR_API_KEY",
            rate_limiter=rate_limiter,
            retry=retry_policy,
            http=session.http,
            endpoint_builder=session.endpoint,
        )
        print(f"Balance: {balance}")
    finally:
        await session.aclose()

asyncio.run(main())
```

### Multiple Networks

```python
import asyncio
from aiochainscan import get_balance

async def check_balances():
    # Works with multiple scanners
    networks = [
        ('eth', 'main', 'YOUR_ETHERSCAN_KEY'),           # Etherscan
        ('blockscout_sepolia', 'sepolia', ''),          # Blockscout (free)
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

## Available Functions

The library provides simple facade functions for common operations:

- `get_balance()` - Get account balance
- `get_block()` - Get block information
- `get_transaction()` - Get transaction details
- `get_token_balance()` - Get ERC-20 token balance
- `get_eth_price()` - Get ETH/USD price
- `get_all_transactions_optimized()` - Fetch all transactions efficiently
- `get_all_logs_optimized()` - Fetch all logs with range splitting

All functions support dependency injection for customizing HTTP clients, rate limiters, retries, and caching.

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
