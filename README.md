# aiochainscan

**Async Python wrapper for blockchain explorer APIs with unified ChainscanClient interface.**

Provides a single, consistent API for accessing blockchain data across multiple scanners (Etherscan, BlockScout, Moralis, etc.) with logical method calls and automatic scanner management.

[![CI/CD](https://github.com/VaitaR/aiochainscan/actions/workflows/ci.yml/badge.svg)](https://github.com/VaitaR/aiochainscan/actions/workflows/ci.yml)

## Features

- **🆕 SmartContract API** - High-level abstraction with automatic ABI fetching, proxy resolution, and decoded event/transaction iteration
- **🆕 ENS Integration** - Native support for ENS name resolution and reverse lookup with caching
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

### 1. SmartContract API (✨ NEW in v0.4.0)

The **SmartContract API** provides the easiest way to interact with smart contracts - automatically fetching ABIs, resolving proxies, and decoding events/transactions:

```python
import asyncio
from aiochainscan import ChainscanClient

async def main():
    # Create client
    client = ChainscanClient.from_config('etherscan', 'ethereum')

    # Get contract - automatically fetches ABI and resolves proxy
    usdt = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")

    print(f"Is Proxy: {usdt.is_proxy}")  # True - USDT is a proxy!
    print(f"Implementation: {usdt.implementation_address}")

    # Iterate through decoded Transfer events - so easy!
    async for event in usdt.iter_events("Transfer", limit=10):
        from_addr = event.args['from'][:10]
        to_addr = event.args['to'][:10]
        value = event.args['value'] / 1e6  # USDT has 6 decimals
        print(f"Block {event.block_number}: {from_addr}... → {to_addr}... ${value:,.2f}")

    # Iterate through decoded transactions
    async for tx in usdt.iter_transactions(limit=5):
        print(f"Function: {tx.function_name}()")
        print(f"  Args: {tx.args}")
        print(f"  From: {tx.from_address[:10]}...")

    await client.close()

asyncio.run(main())
```

**See [SmartContract API Documentation](docs/SMART_CONTRACT_API.md) for complete guide!**

### 2. ENS Integration (✨ NEW in v0.4.0)

**ENS (Ethereum Name Service)** integration makes it easy to resolve names to addresses and vice versa:

```python
import asyncio
from aiochainscan import ChainscanClient

async def main():
    # Create client (ENS only works on Ethereum mainnet)
    # Use BlockScout V2 for reverse lookup (no API key required)
    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Reverse lookup: address → name (works with BlockScout V2)
    name = await client.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    print(f"vitalik's address → {name}")
    # Output: vitalik's address → vitalik.eth

    # Batch reverse lookup (parallel)
    names = await client.lookup_addresses([
        "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        "0xb8c2C29ee19D8307cb7255e1Cd9CbDE883A267d5"
    ])
    print(f"Found {len(names)} ENS names")
    # Output: Found 2 ENS names

    # Note: Forward resolution (name → address) requires Etherscan
    # because BlockScout V2 doesn't expose eth_call needed for ENS contracts

    # For forward resolution, use Etherscan (requires API key)
    client_etherscan = ChainscanClient.from_config('etherscan', 'ethereum')
    address = await client_etherscan.resolve_name("vitalik.eth")
    print(f"vitalik.eth → {address}")
    # Output: vitalik.eth → 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045

    # Integrate with SmartContract API
    # Enrich event data with ENS names
    usdt = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")
    async for event in usdt.iter_events("Transfer", limit=5):
        # Lookup ENS names for addresses in Transfer events
        from_name = await client.lookup_address(event.args['from'])
        to_name = await client.lookup_address(event.args['to'])
        print(f"Transfer: {from_name or event.args['from'][:10]+'...'} → {to_name or event.args['to'][:10]+'...'}")

    await client.close()

asyncio.run(main())
```

**Features:**
- Reverse lookup (address → name) with `lookup_address()` - works with BlockScout V2 (no API key)
- Forward resolution (name → address) with `resolve_name()` - requires Etherscan (API key needed)
- Batch operations with `resolve_names()` and `lookup_addresses()`
- Automatic caching with configurable TTL
- Seamless integration with SmartContract API

**See [ENS Integration Documentation](docs/ENS_INTEGRATION.md) for complete guide!**

### 3. Unified ChainscanClient (Recommended)

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

### 4. ⚠️ Legacy Facade Functions (Deprecated)

**WARNING**: Facade functions are deprecated in v0.4.0 and will be removed in v0.5.0 due to critical connection pooling issues.

<details>
<summary>Why are facade functions deprecated? (Click to expand)</summary>

**The Problem**: Each facade function call creates and destroys an HTTP client, preventing connection pooling:

```python
# ❌ AVOID - Creates 100 separate HTTP clients (very slow!)
balances = await asyncio.gather(*[
    get_balance(address=addr, api_kind='eth', network='main', api_key=key)
    for addr in addresses  # 100 addresses
])
```

This causes:
- 100 TCP connection establishments
- 100 TLS handshakes
- Loss of HTTP/2 multiplexing
- High CPU load and API rate limits

**The Solution**: Use `ChainscanClient` which maintains a persistent connection pool (see examples above).

</details>

For simple use cases, you can still use facade functions (but expect deprecation warnings):

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

**Migration Path**: See [MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md) for detailed migration instructions.

### 5. Optimized Bulk Operations

**Important**: For bulk operations, always use `ChainscanClient` to benefit from connection pooling:

```python
import asyncio
from aiochainscan import ChainscanClient
from aiochainscan.core.method import Method

async def main():
    addresses = ['0x...' for _ in range(100)]  # 100 addresses

    # ✅ Efficient - Shares connection pool across all requests
    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
    try:
        balances = await asyncio.gather(*[
            client.call(Method.ACCOUNT_BALANCE, address=addr)
            for addr in addresses
        ])
        print(f"Fetched {len(balances)} balances efficiently!")
    finally:
        await client.close()

asyncio.run(main())
```

### 6. Legacy Optimized Functions (Also Deprecated)

The library also provides optimized aggregation functions (also being deprecated):

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

## Development Setup

### For Contributors

```bash
# Clone the repository
git clone https://github.com/VaitaR/aiochainscan.git
cd aiochainscan

# Run setup script (installs deps + git hooks)
chmod +x scripts/setup-dev.sh
./scripts/setup-dev.sh
```

This sets up:
- ✅ All dependencies via `uv`
- ✅ Pre-commit hooks (format, lint, import tests)
- ✅ Pre-push hooks (type checking, tests)
- ✅ Automatic quality checks on every commit

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guide.

### Quality Gates

We have **3 levels** of protection:
1. **Pre-commit** (5s) - Format, lint, import tests
2. **Pre-push** (30s) - Type checking, quick tests
3. **CI/CD** (5min) - Full test suite, wheel building

Import tests catch circular dependencies **before commit**! See [docs/QUALITY_GATES.md](docs/QUALITY_GATES.md).

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Code style guidelines
- Testing requirements
- Pull request process

Quick checklist:
- [ ] Run `./scripts/setup-dev.sh` first
- [ ] All import tests pass (`pytest tests/test_imports.py`)
- [ ] All pre-commit hooks pass
- [ ] Type checking passes (`mypy --strict aiochainscan`)
- [ ] All tests pass (`pytest -v`)
