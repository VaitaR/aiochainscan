# aiochainscan

Async Python wrapper for blockchain explorer APIs (Etherscan, BSCScan, PolygonScan, etc.).

[![CI/CD](https://github.com/VaitaR/aiochainscan/actions/workflows/ci.yml/badge.svg)](https://github.com/VaitaR/aiochainscan/actions/workflows/ci.yml)

## Features

- **Async/await support** - Built for modern Python async applications
- **Multiple blockchain support** - Ethereum, BSC, Polygon, Arbitrum, Optimism, and 10+ more
- **Built-in throttling** - Respect API rate limits automatically
- **Comprehensive API coverage** - All major API endpoints supported
- **Type hints** - Full type safety with Python type hints
- **Configuration management** - Easy setup with environment variables
- **Robust HTTP client** - aiohttp backend with built-in retries and throttling
- **🚀 Fast ABI decoding** - High-performance Rust backend with Python fallback

### Telemetry fields

All high-level facades/services emit telemetry events via the `Telemetry` port (default adapter: `StructlogTelemetry`). Common attributes are standardized:

- api_kind: provider family (e.g., etherscan, blockscout, routscan)
- network: network key (e.g., eth, bsc)
- duration_ms: integer latency for the HTTP operation
- items: for list responses, the number of items returned

You can inject your own `Telemetry` implementation into facade calls or use `open_default_session()` for DI.

## Supported Blockchains

| Blockchain | Scanner | Networks | API Key Required |
|------------|---------|----------|------------------|
| Ethereum | Etherscan | main, goerli, sepolia, test | ✅ |
| BSC | BscScan | main, test | ✅ |
| Polygon | PolygonScan | main, mumbai, test | ✅ |
| Arbitrum | Arbiscan | main, nova, goerli, test | ✅ |
| Optimism | Optimism Etherscan | main, goerli, test | ✅ |
| Fantom | FtmScan | main, test | ✅ |
| Gnosis | GnosisScan | main, chiado | ✅ |
| Base | BaseScan | main, goerli, sepolia | ✅ |
| Linea | LineaScan | main, test | ✅ |
| Blast | BlastScan | main, sepolia | ✅ |
| X Layer | OKLink | main | ✅ |
| Flare | Flare Explorer | main, test | ❌ |
| Wemix | WemixScan | main, test | ✅ |
| Chiliz | ChilizScan | main, test | ✅ |
| Mode | Mode Network | main | ✅ |

## Installation

### For users
```sh
pip install -U aiochainscan
```

### Fast ABI Decoding (Optional)

For significantly faster ABI decoding performance, you can install the optional Rust backend:

```sh
# Option 1: Install with fast decoding support
pip install -U "aiochainscan[fast]"

# Option 2: If you have Rust toolchain installed
maturin develop --manifest-path aiochainscan/fastabi/Cargo.toml
```

**Performance Benefits:**
- 🚀 **10-100× faster** ABI decoding compared to pure Python
- 🔄 **Automatic fallback** to Python implementation if Rust backend unavailable
- 📦 **Drop-in replacement** - no code changes required
- 🔧 **Battle-tested** - uses ethers-rs for robust ABI parsing

### For development
```sh
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/VaitaR/aiochainscan.git
cd aiochainscan

# Install dependencies and create virtual environment
uv sync --dev

# Activate the virtual environment
source .venv/bin/activate  # On Unix/macOS
# .venv\Scripts\activate    # On Windows
```

## Quick Start

### 1. Set up API Keys

First, get API keys from the blockchain explorers you want to use:
- [Etherscan](https://etherscan.io/apis)
- [BSCScan](https://bscscan.com/apis)
- [PolygonScan](https://polygonscan.com/apis)
- [Arbiscan](https://docs.arbiscan.io/getting-started/endpoint-urls)
- [FtmScan](https://docs.ftmscan.com/getting-started/endpoint-urls)

Then set them as environment variables:

```bash
export ETHERSCAN_KEY="your_etherscan_api_key"
export BSCSCAN_KEY="your_bscscan_api_key"
export POLYGONSCAN_KEY="your_polygonscan_api_key"
# ... etc
```

Or create a `.env` file:
```env
ETHERSCAN_KEY=your_etherscan_api_key
BSCSCAN_KEY=your_bscscan_api_key
POLYGONSCAN_KEY=your_polygonscan_api_key
```

### 2. Basic Usage (Typed facades – recommended)

```python
import asyncio
from aiochainscan import (
  get_block_typed,
  get_transaction_typed,
  get_logs_typed,
  get_token_balance_typed,
  get_gas_oracle_typed,
  get_eth_price_typed,
)

async def main():
    block = await get_block_typed(tag=17000000, full=False, api_kind='eth', network='main', api_key='YOUR_API_KEY')
    tx = await get_transaction_typed(txhash='0x...', api_kind='eth', network='main', api_key='YOUR_API_KEY')
    logs = await get_logs_typed(start_block=17000000, end_block=17000100, address='0x...', api_kind='eth', network='main', api_key='YOUR_API_KEY')
    tb = await get_token_balance_typed(holder='0x...', token_contract='0x...', api_kind='eth', network='main', api_key='YOUR_API_KEY')
    gas = await get_gas_oracle_typed(api_kind='eth', network='main', api_key='YOUR_API_KEY')
    price = await get_eth_price_typed(api_kind='eth', network='main', api_key='YOUR_API_KEY')
    print(block['block_number'], tb['balance_wei'], gas['propose_gas_price_wei'], price['eth_usd'])

if __name__ == '__main__':
    asyncio.run(main())
```

### 3. Multiple Blockchains (typed)

```python
import asyncio
from aiochainscan import get_eth_price_typed

async def check_prices():
    networks = [('eth','main'), ('bsc','main'), ('polygon','main')]
    for scanner, network in networks:
        price = await get_eth_price_typed(api_kind=scanner, network=network, api_key='YOUR_API_KEY')
        print(f"{scanner.upper()} ETH price: {price}")

asyncio.run(check_prices())
```

### 4. Configuration Management

```python
from aiochainscan import Client

# Check available scanners
print("Available scanners:", Client.get_supported_scanners())

# Check networks for a specific scanner
print("Ethereum networks:", Client.get_scanner_networks('eth'))

# Check configuration status
configs = Client.list_configurations()
for scanner, info in configs.items():
    status = "✓ READY" if info['api_key_configured'] else "✗ MISSING API KEY"
    print(f"{scanner}: {status}")
```

## Advanced Usage

### Custom Throttling and Retries

```python
import asyncio
from aiohttp_retry import ExponentialRetry
from asyncio_throttle import Throttler
from aiochainscan import Client

async def main():
    # Custom rate limiting and retry logic
    throttler = Throttler(rate_limit=1, period=6.0)  # 1 request per 6 seconds
    retry_options = ExponentialRetry(attempts=3)

    client = Client.from_config(
        'eth', 'main',
        throttler=throttler,
        retry_options=retry_options
    )

    try:
        # Your API calls here
        balance = await client.account.balance('0x123...')
        print(f"Balance: {balance}")
    finally:
        await client.close()

asyncio.run(main())
```

### Legacy Usage (Manual API Keys)

```python
import asyncio
from aiochainscan import Client

async def main():
    # Old way - manual API key specification
    client = Client(
        api_key='your_etherscan_api_key',
        api_kind='eth',
        network='main'
    )

    try:
        # Your API calls
        price = await client.stats.eth_price()
        print(f"ETH price: {price}")
    finally:
        await client.close()

asyncio.run(main())
```

### Bulk Operations
### Facades + DI

Facades can be used with dependency injection for reusing HTTP sessions and adapters:

```python
import asyncio
from aiochainscan import open_default_session, get_balance, get_token_balance

async def main():
    session = await open_default_session()
    try:
        # Reuse the same session for multiple calls
        bal = await get_balance(
            address="0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3",
            api_kind="eth",
            network="main",
            api_key="YOUR_API_KEY",
            http=session.http,
            endpoint_builder=session.endpoint,
            telemetry=session.telemetry,
        )
        usdt = await get_token_balance(
            holder="0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3",
            token_contract="0xdAC17F958D2ee523a2206206994597C13D831ec7",
            api_kind="eth",
            network="main",
            api_key="YOUR_API_KEY",
            http=session.http,
            endpoint_builder=session.endpoint,
            telemetry=session.telemetry,
        )
        print(bal, usdt)
    finally:
        await session.aclose()

asyncio.run(main())
```

### Optimized fetch-all (range-splitting aggregator)

For high-volume endpoints that support block ranges (e.g., normal transactions, internal transactions, logs), the library provides optimized facades powered by a generic aggregator that performs dynamic range splitting, concurrency control, retries, and deduplication.

- Normal transactions:
  ```python
  from aiochainscan import get_all_transactions_optimized

  txs = await get_all_transactions_optimized(
      address="0x...",
      api_kind="blockscout_eth",  # works for etherscan-family incl. Blockscout (no API key)
      network="eth",
      api_key="",
      max_concurrent=5,
      max_offset=10_000,
      # tuning (optional)
      min_range_width=1_000,
      max_attempts_per_range=3,
  )
  ```

- Internal transactions:
  ```python
  from aiochainscan import get_all_internal_transactions_optimized

  internals = await get_all_internal_transactions_optimized(
      address="0x...",
      api_kind="eth",
      network="main",
      api_key="YOUR_API_KEY",
      max_concurrent=5,
      max_offset=10_000,
  )
  ```

- Logs (with topics):
  ```python
  from aiochainscan import get_all_logs_optimized

  logs = await get_all_logs_optimized(
      address="0x...",
      api_kind="eth",
      network="main",
      api_key="YOUR_API_KEY",
      topics=["0xddf252ad..."],
      max_concurrent=3,
      max_offset=1_000,
  )
  ```

Notes:
- The aggregator respects rate limits via the RateLimiter port and supports retries via RetryPolicy.
- You can pass an optional `stats` dict to collect execution metrics (ranges processed/split/retries, item counts).
- Typed variant for normal transactions is available as `get_all_transactions_optimized_typed`.

### Fetch-all engine (paged/sliding)

The library also provides a universal fetch-all paging engine designed for explorer-style APIs.

- Core API (module `aiochainscan.services.paging_engine`):
  - `FetchSpec`: what/how to load (page fetcher, dedup key, order key, page size, end-block resolver)
  - `ProviderPolicy`: how to page (mode: `paged` or `sliding`, `prefetch`, optional `window_cap`, `rps_key`)
  - `fetch_all_generic(...)`: engine that orchestrates paging with RPS, retries, telemetry and stats
  - `resolve_policy_for_provider(api_kind, network, max_concurrent)`: sensible defaults per provider family

- Policies (defaults):
  - Etherscan (`api_kind='eth'`): `mode='sliding'`, `window_cap=10000`, `prefetch=1`
  - Blockscout (`api_kind` startswith `blockscout_`): `mode='paged'`, `prefetch=max_concurrent`
  - Others: `mode='paged'`, `prefetch=1`

- Engine behavior:
  - `paged`: fetch batches of pages in parallel; stop on empty page or `len(items) < offset`
  - `sliding`: always `page=1`; advance `start_block = last_block + 1`; same stop conditions
  - RPS via `RateLimiter.acquire(policy.rps_key)`, retries via `RetryPolicy.run`, telemetry via `Telemetry`
  - End-block snapshot via proxy `eth_blockNumber` (fallback `99_999_999`)
  - Dedup by spec.key_fn; stable sort by spec.order_fn (safe hex/str→int)

- Telemetry events emitted by the engine:
  - `paging.duration`, `paging.page_ok` (page, items), `paging.ok` (total)
  - `paging.error` on fatal errors

- Stats (optional):
  - `pages_processed`, `items_total`, `mode`, `prefetch`, `start_block`, `end_block`

Convenience wrappers in `aiochainscan/services/fetch_all.py` expose a stable public API for common data types:

- `fetch_all_transactions_basic/fast`
- `fetch_all_internal_basic/fast`
- `fetch_all_logs_basic/fast`

Wrappers select the right policy for the provider (`eth` → sliding; `blockscout_*` → paged) and ensure no duplicates or gaps while respecting provider windows and RPS.

### Normalizers/DTO

For many responses, helpers are provided to normalize provider-shaped payloads into light DTOs, e.g. `normalize_block`, `normalize_transaction`, `normalize_token_balance`, `normalize_gas_oracle`, and stats daily series (e.g. `normalize_daily_transaction_count`). These are pure helpers and can be composed with your own caching or telemetry.

```python
import asyncio
from aiochainscan import Client

async def main():
    client = Client.from_config('eth', 'main')

    try:
        # Use utility functions for bulk operations
        async for transfer in client.utils.token_transfers_generator(
            address='0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2',
            start_block=16734850,
            end_block=16734860
        ):
            print(f"Transfer: {transfer}")
    finally:
        await client.close()

asyncio.run(main())
```

### Typed DTO facades (non-breaking)

Typed variants of common facades are provided in parallel and return normalized DTOs. These are additive and do not break existing APIs. Use them when you want a stable, typed shape regardless of provider quirks.

```python
import asyncio
from aiochainscan import (
  get_block_typed,
  get_transaction_typed,
  get_logs_typed,
  get_token_balance_typed,
  get_gas_oracle_typed,
  get_eth_price_typed,
)

async def main():
    block = await get_block_typed(tag=17000000, full=False, api_kind='eth', network='main', api_key='YOUR_API_KEY')
    tx = await get_transaction_typed(txhash='0x...', api_kind='eth', network='main', api_key='YOUR_API_KEY')
    logs = await get_logs_typed(start_block=17000000, end_block=17000100, address='0x...', api_kind='eth', network='main', api_key='YOUR_API_KEY')
    tb = await get_token_balance_typed(holder='0x...', token_contract='0x...', api_kind='eth', network='main', api_key='YOUR_API_KEY')
    gas = await get_gas_oracle_typed(api_kind='eth', network='main', api_key='YOUR_API_KEY')
    price = await get_eth_price_typed(api_kind='eth', network='main', api_key='YOUR_API_KEY')
    print(block['block_number'], tb['balance_wei'], gas['propose_gas_price_wei'], price['eth_usd'])

asyncio.run(main())
```

### Deprecation note (modules/*)

Legacy modules (e.g., `client.account`, `client.block`, etc.) now route through facades internally. You can force facade-only mode by setting `AIOCHAINSCAN_FORCE_FACADES=1` in your environment to catch regressions early. Public signatures remain unchanged; full removal of legacy modules is planned for 2.0 with a deprecation window.

## API Reference

The client provides access to all major blockchain explorer APIs:

- `client.account` - Account-related operations (balance, transactions, etc.)
- `client.block` - Block information
- `client.contract` - Smart contract interactions
- `client.transaction` - Transaction details
- `client.token` - Token information and transfers
- `client.stats` - Network statistics and prices
- `client.gas_tracker` - Gas price tracking
- `client.logs` - Event logs
- `client.proxy` - JSON-RPC proxy methods
- `client.utils` - Utility functions for bulk operations

## CLI Tools

The new system includes a powerful command-line interface for configuration management:

### Installation and Basic Usage

```bash
# Install in development mode to get CLI access
pip install -e .

# Check available commands
aiochainscan --help
```

### Available CLI Commands

```bash
# List all supported scanners and their status
aiochainscan list

# Check current configuration status
aiochainscan check

# Generate .env template file
aiochainscan generate-env

# Generate custom .env file
aiochainscan generate-env --output .env.production

# Test a specific scanner configuration
aiochainscan test eth
aiochainscan test bsc --network test

# Add a custom scanner
aiochainscan add-scanner mychain \
  --name "My Custom Chain" \
  --domain "mychainscan.io" \
  --currency "MYTOKEN" \
  --networks "main,test"

# Export current configuration to JSON
aiochainscan export config.json
```

### Configuration Management Workflow

```bash
# 1. Generate .env template
aiochainscan generate-env

# 2. Copy and edit with your API keys
cp .env.example .env
# Edit .env with your actual API keys

# 3. Verify configuration
aiochainscan check

# 4. Test specific scanners
aiochainscan test eth
aiochainscan test bsc
```

## Error Handling

```python
import asyncio
from aiochainscan import Client
from aiochainscan.exceptions import ChainscanClientApiError

async def main():
    client = Client.from_config('eth', 'main')

    try:
        balance = await client.account.balance('invalid_address')
    except ChainscanClientApiError as e:
        print(f"API Error: {e}")
    except ValueError as e:
        print(f"Configuration Error: {e}")
    finally:
        await client.close()

asyncio.run(main())
```

## Development

### Running tests
```sh
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=aiochainscan

# Run linting
uv run ruff check
uv run ruff format --check

# Run type checking (strict)
uv run mypy --strict aiochainscan

# Auto-fix linting issues
uv run ruff check --fix
uv run ruff format
```

> **Dependency note:** The SDK relies on third-party async HTTP utilities (``aiohttp``, ``aiohttp_retry``,
> ``asyncio_throttle``). Ensure they are installed before running tests locally, e.g. ``uv pip install .[dev]``
> or ``pip install -e '.[dev]'`` with network access to PyPI.

### CI Note
- CI now enforces strict static typing with mypy. Run `uv run mypy --strict aiochainscan` locally before pushing to ensure the type check gate passes.

### Adding dependencies
```sh
# Add a production dependency
uv add package_name

# Add a development dependency
uv add --dev package_name
```

## Testing

The library includes comprehensive test suites for different use cases:

### Quick Testing

```bash
# Run unit tests (no API keys required)
make test-unit

# Run integration tests with real API calls (requires API keys)
make test-integration

# Run all tests
make test-all
```

### CI note on facades routing

In CI, a smoke job can set the environment variable `AIOCHAINSCAN_FORCE_FACADES=1` to ensure legacy modules route through facades only. All tests must pass under this mode.

### Setting Up API Keys for Testing

```bash
# Method 1: Use setup script
source setup_test_env.sh
python -m pytest tests/test_integration.py -v

# Method 2: Set environment variables
export ETHERSCAN_KEY="your_etherscan_api_key"
export BSCSCAN_KEY="your_bscscan_api_key"
python -m pytest tests/test_integration.py -v

# Method 3: Use .env file
aiochainscan generate-env
cp .env.example .env
# Edit .env with your API keys
python -m pytest tests/test_integration.py -v
```

### Test Categories

- **Unit Tests**: Configuration system, client creation, validation (no API keys needed)
- **Integration Tests**: Real API calls with blockchain explorers (requires API keys)
- **Error Handling**: Invalid inputs, rate limiting, network errors
- **Multi-Scanner**: Cross-chain functionality testing

See [TESTING.md](TESTING.md) for comprehensive testing documentation.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Changelog

### v0.2.0 (Latest)
- ✅ **Advanced Configuration System**: Professional-grade configuration management
- ✅ **Multi-Scanner Support**: Unified interface for 15+ blockchain scanners
- ✅ **Smart API Key Management**: Multiple fallback strategies and .env file support
- ✅ **CLI Tools**: `aiochainscan` command-line interface for configuration
- ✅ **Dynamic Scanner Registration**: Add custom scanners via JSON or code
- ✅ **Enhanced Client Factory**: `Client.from_config()` method for easy setup
- ✅ **Network Validation**: Automatic validation of scanner/network combinations
- ✅ **Backward Compatibility**: Existing code continues to work unchanged

### v0.1.0
- Initial release with basic functionality
- Support for multiple blockchain networks
- Async/await API design
- Built-in throttling and retry mechanisms
