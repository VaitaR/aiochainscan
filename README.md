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
- **Flexible HTTP backends** - Support for both aiohttp and curl_cffi
- **🚀 Fast ABI decoding** - High-performance Rust backend with Python fallback

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

### 2. Basic Usage

```python
import asyncio
from aiochainscan import Client

async def main():
    # Create client using configuration system
    client = Client.from_config('eth', 'main')  # Uses ETHERSCAN_KEY
    
    try:
        # Get ETH price
        price = await client.stats.eth_price()
        print(f"ETH price: ${price}")
        
        # Get block information
        block = await client.block.block_reward(12345678)
        print(f"Block reward: {block}")
        
        # Get account balance
        balance = await client.account.balance('0x123...')
        print(f"Balance: {balance}")
        
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())
```

### 3. Multiple Blockchains

```python
import asyncio
from aiochainscan import Client

async def check_prices():
    """Check ETH price on multiple networks."""
    
    networks = [
        ('eth', 'main'),
        ('bsc', 'main'), 
        ('polygon', 'main'),
    ]
    
    for scanner, network in networks:
        try:
            client = Client.from_config(scanner, network)
            price = await client.stats.eth_price()
            print(f"{scanner.upper()} ETH price: {price}")
            await client.close()
        except ValueError as e:
            print(f"Skipping {scanner}: {e}")

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

# Auto-fix linting issues
uv run ruff check --fix
uv run ruff format
```

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
