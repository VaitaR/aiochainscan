# aiochainscan

**Async Python wrapper for blockchain explorer APIs with unified ChainscanClient interface.**

Provides a single, consistent API for accessing blockchain data across multiple scanners (Etherscan, BlockScout) with typed convenience methods and automatic scanner management.

[![CI/CD](https://github.com/VaitaR/aiochainscan/actions/workflows/ci.yml/badge.svg)](https://github.com/VaitaR/aiochainscan/actions/workflows/ci.yml)

## Features

- **🆕 SmartContract API** - High-level abstraction with automatic ABI fetching, proxy resolution, and decoded event/transaction iteration
- **🆕 ENS Integration** - Native support for ENS name resolution and reverse lookup with caching
- **🆕 Unified ChainscanClient** - Single interface for all blockchain scanners with 30+ typed convenience methods
- **💨 Streaming API** - Memory-efficient iteration over large datasets (~10MB RAM for 1M+ transactions)
- **📊 DataFrame Export** - Built-in Polars DataFrame conversion with auto-pagination
- **🔄 Easy Scanner Switching** - Switch between Etherscan, BlockScout with one config change
- **📡 Real-time Blockchain Data** - Access to 15+ networks including Ethereum, BSC, Polygon, Arbitrum, Optimism, Base
- **⚡ Built-in Rate Limiting** - Automatic throttling with configurable limits and retry policies
- **🎯 Comprehensive API Coverage** - 28 blockchain operations with typed convenience methods
- **🔒 Type-safe Operations** - Typed data transfer objects, method enums, 100% mypy --strict
- **🚀 Optimized Bulk Operations** - Streaming aggregation for `get_all_*` plus `iter_*_streaming` for low-memory processing
- **🧩 Dependency Injection** - Configurable caching, retry policies, and rate limiters
- **⛓️ Rust FFI** - Fast ABI decoding via PyO3 with LRU cache

## Supported Networks

**Etherscan API**: Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, Fantom, Gnosis, and more EVM chains (Base supported via Etherscan V2)
**Blockscout**: Public blockchain explorers (no API key needed) - Ethereum, Sepolia, Gnosis, Polygon, and others

## Installation

```sh
# From GitHub (current method)
pip install git+https://github.com/VaitaR/aiochainscan.git

# Or clone and install
git clone https://github.com/VaitaR/aiochainscan.git
cd aiochainscan
pip install .
```

The dependency footprint is intentionally minimal — only `httpx`, `orjson`,
`tenacity` and `aiolimiter`. Prebuilt wheels bundle the fastabi Rust
extension, so no Rust toolchain is required when installing from wheels.

**Optional extras:**

| Extra | Purpose |
|---|---|
| `data` | Polars DataFrames (`get_transactions_df` and friends) |
| `mcp` | MCP server for AI agents (`aiochainscan.mcp_server`) |
| `http2` | HTTP/2 transport (`http2=True`; off by default — Cloudflare WAF risk) |
| `fallback` | Pure-Python keccak/ABI decoding for environments without fastabi |

```sh
pip install "aiochainscan[data]"   # example
```

**Verify installation:**
```python
import aiochainscan
print(f"aiochainscan v{aiochainscan.__version__}")

from aiochainscan import ChainscanClient
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

The **ChainscanClient** provides a unified interface with **30+ typed convenience methods**:

```python
import asyncio
from aiochainscan import ChainscanClient

async def main():
    # Create client — async context manager handles cleanup
    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        # Account data
        balance = await client.get_balance('0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3')
        print(f"Balance: {int(balance) / 10**18:.6f} ETH")

        txs = await client.get_transactions('0x...')           # single page
        all_txs = await client.get_all_transactions('0x...')    # ALL (streaming aggregation → list)
        tokens = await client.get_token_portfolio('0x...')      # ERC-20 holdings

        # Blocks & transactions
        block = await client.get_block(12345678)
        tx = await client.get_transaction('0xHASH...')
        status = await client.get_transaction_status('0xHASH...')

        # Contracts
        abi = await client.get_contract_abi('0x...')
        source = await client.get_contract_source('0x...')

        # Tokens & gas
        price = await client.get_eth_price()
        gas = await client.get_gas_oracle()

        # Event logs (single page or ALL)
        logs = await client.get_logs('0x...', from_block=0)
        all_logs = await client.get_all_logs('0x...', from_block=0)  # streaming aggregation → list

        # Preferred for large datasets (~10MB RAM for 1M+ txs)
        async for batch in client.iter_transactions_streaming('0x...', batch_size=1000):
            process(batch)

        # DataFrame export (auto-paginates)
        df = await client.get_transactions_df('0x...')

asyncio.run(main())
```

**Switch scanners** — same interface:
```python
# BlockScout V2 (free, no API key)
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

# Etherscan V2 (requires ETHERSCAN_KEY env var)
client = ChainscanClient.from_config('etherscan', 'ethereum')
```

### 4. Legacy API Purge (v0.5+)

Public usage is now **ChainscanClient-only**.

Removed legacy surfaces:
- Top-level facade functions (`get_balance`, `get_block`, etc.)
- Legacy facade/context/url-builder orchestration services
- Older pagination engines replaced by modern streaming aggregation

Use `get_all_*` when you need fully materialized results (it now uses streaming aggregation internally), and prefer `iter_*_streaming` for large datasets.

Migration details: [MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md).

### 5. Bulk Operations & Streaming

**ChainscanClient** provides efficient bulk operations out of the box:

```python
import asyncio
from aiochainscan import ChainscanClient

async def main():
    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        address = '0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3'

        # Get ALL transactions (auto-paginated)
        all_txs = await client.get_all_transactions(address)
        print(f"Total transactions: {len(all_txs)}")

        # Stream for large wallets (~10MB RAM)
        async for batch in client.iter_transactions_streaming(address, batch_size=1000):
            print(f"Processing batch of {len(batch)} txs")

        # Export to Polars DataFrame (auto-paginated)
        df = await client.get_transactions_df(address)
        print(f"DataFrame shape: {df.shape}")

        # Parallel balance lookups
        addresses = ['0x...' for _ in range(100)]
        balances = await asyncio.gather(*[
            client.get_balance(addr) for addr in addresses
        ])
        print(f"Fetched {len(balances)} balances")

asyncio.run(main())
```

## Advanced Usage

### ChainscanClient with Custom Configuration

For advanced use cases with custom rate limiting, retries, and dependency injection:

```python
import asyncio
from aiochainscan import ChainscanClient
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
        # Use typed convenience methods
        balance = await client.get_balance(
            "0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3"
        )

        # Get transaction history (single page)
        transactions = await client.get_transactions(
            "0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3"
        )

        # Or get ALL transactions (auto-paginated)
        all_txs = await client.get_all_transactions(
            "0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3"
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
from aiochainscan import ChainscanClient
from aiochainscan.core.method import Method

async def check_multi_scanner_balance():
    address = "0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3"

    # Same code works with any scanner - just change config!
    scanners = [
        # BlockScout V2 (free, no API key needed)
        ('blockscout_v2', 'ethereum'),

        # BlockScout V1 (free, no API key needed)
        ('blockscout', 'ethereum'),

        # Etherscan (requires API key)
        ('etherscan', 'ethereum'),
    ]

    for scanner_name, network in scanners:
        try:
            client = ChainscanClient.from_config(
                scanner_name=scanner_name,
                network=network
            )

            # Same convenience methods for all scanners!
            balance = await client.get_balance(address)

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

### Multiple Networks with ChainscanClient

```python
import asyncio
from aiochainscan import ChainscanClient

async def check_balances():
    address = "0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3"
    targets = [
        ("blockscout_v2", "ethereum"),
        ("etherscan", "ethereum"),
    ]

    for scanner_name, network in targets:
        async with ChainscanClient.from_config(scanner_name, network) as client:
            balance = await client.get_balance(address)
            print(f"{scanner_name} {network}: {balance} wei")

asyncio.run(check_balances())
```

### Environment Variables

Set API keys as environment variables:

```bash
export ETHERSCAN_KEY="your_etherscan_api_key"
# Blockscout and some networks work without API keys
```

## Configuration Parameters

When using `ChainscanClient.from_config()`, you need to specify three key parameters:

- **scanner_name**: Provider name (`'etherscan'`, `'blockscout'`, `'blockscout_v2'`)
- **scanner_version**: API version (`'v1'`, `'v2'`)
- **network**: Chain name/ID (`'eth'`, `'ethereum'`, `1`, `'base'`, `8453`, etc.)

### Common Configurations:

| Provider | scanner_name | default_version | network | API Key |
|----------|-------------|-----------------|---------|---------|
| **BlockScout V2 Ethereum** | `'blockscout_v2'` | `v2` | `'ethereum'` | ❌ Not required |
| **BlockScout V1 Ethereum** | `'blockscout'` | `v1` | `'ethereum'` | ❌ Not required |
| **Etherscan Ethereum** | `'etherscan'` | `v2` | `'ethereum'` | ✅ `ETHERSCAN_KEY` |
| **Etherscan Base** | `'etherscan'` | `v2` | `'base'` | ✅ `ETHERSCAN_KEY` |

**Network parameter supports both names and chain IDs:**
- `'ethereum'`, `'eth'`, `1` - Ethereum
- `'base'`, `8453` - Base
- `'polygon'`, `'matic'` - Polygon
- `'bsc'`, `'binance'`, `56` - Binance Smart Chain

## Available Interfaces

The public interface is **ChainscanClient**.

### 1. ChainscanClient (Recommended)

The **unified client** provides 30+ typed convenience methods:

```python
from aiochainscan import ChainscanClient

async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
    # Account
    balance = await client.get_balance('0x...')                   # Wei string
    txs     = await client.get_transactions('0x...')              # single page
    all_txs = await client.get_all_transactions('0x...')          # ALL (streaming aggregation → list)
    itxs    = await client.get_internal_transactions('0x...')     # internal txs
    erc20   = await client.get_token_transfers('0x...')           # ERC-20 transfers
    erc721  = await client.get_erc721_transfers('0x...')          # ERC-721 transfers
    erc1155 = await client.get_erc1155_transfers('0x...')         # ERC-1155 transfers
    tokens  = await client.get_token_portfolio('0x...')           # ERC-20 holdings
    nfts    = await client.get_nft_portfolio('0x...')             # NFT holdings

    # Transactions
    tx     = await client.get_transaction('0xHASH...')            # by hash
    status = await client.get_transaction_status('0xHASH...')     # receipt status
    check  = await client.check_transaction_status('0xHASH...')   # execution status

    # Blocks
    block     = await client.get_block(12345678)                  # by number
    reward    = await client.get_block_reward(12345678)           # mining reward
    countdown = await client.get_block_countdown(99999999)        # ETA to block
    by_ts     = await client.get_block_by_timestamp(1609459200)   # nearest block

    # Contracts
    abi     = await client.get_contract_abi('0x...')              # JSON ABI
    source  = await client.get_contract_source('0x...')           # verified source
    created = await client.get_contract_creation(['0x...'])       # creator + tx

    # Tokens
    bal     = await client.get_token_balance('0xWALLET', '0xTOKEN')  # raw units
    supply  = await client.get_token_supply('0xTOKEN')               # total supply
    info    = await client.get_token_info('0xTOKEN')                 # name/symbol/decimals

    # Gas & Stats
    price   = await client.get_eth_price()                        # USD/BTC
    gas     = await client.get_gas_oracle()                       # safe/propose/fast
    est     = await client.get_gas_estimate(2_000_000_000)        # ETA in seconds
    eth_sup = await client.get_eth_supply()                       # total ETH supply

    # Event Logs
    logs     = await client.get_logs('0x...', from_block=0)       # single page
    all_logs = await client.get_all_logs('0x...', from_block=0)   # ALL (streaming aggregation → list)

    # Proxy / JSON-RPC
    result  = await client.eth_call('0xTO', '0xDATA')             # eth_call
    bal_hex = await client.eth_get_balance('0x...')                # hex Wei

    # High-level APIs
    contract = await client.get_contract('0x...')                  # SmartContract
    name    = await client.lookup_address('0x...')                 # ENS reverse
    address = await client.resolve_name('vitalik.eth')             # ENS forward

    # Streaming (constant ~10MB RAM)
    async for batch in client.iter_transactions_streaming('0x...', batch_size=1000):
        process(batch)

    # DataFrame export (auto-paginates)
    df = await client.get_transactions_df('0x...')
```

### 2. Low-level `client.call()` API

For advanced use cases, you can use the `Method` enum directly:

```python
from aiochainscan.core.method import Method

result = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
```

## Error Handling

```python
import asyncio
from aiochainscan import ChainscanClient
from aiochainscan.exceptions import ChainscanClientApiError

async def main():
    try:
        async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
            balance = await client.get_balance('0x...')
            print(balance)
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
