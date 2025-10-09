# aiochainscan Project Overview

Async Python wrapper for blockchain explorer APIs with hexagonal architecture and dependency injection support. Provides unified interface for querying blockchain data across multiple networks and scanner providers.

## Project Purpose
Async Python wrapper for blockchain explorer APIs (Etherscan, BSCScan, PolygonScan, etc.). Provides unified interface for querying blockchain data across multiple networks with both legacy and modern unified architectures.

## Architecture

### Core Components
- **Facade Functions**: Simple async functions for common operations (`get_balance`, `get_block`, etc.)
- **Hexagonal Architecture**: Clean layered architecture with ports/adapters pattern
- **Dependency Injection**: Configurable HTTP clients, rate limiters, retries, caching, and telemetry
- **Optimized Aggregators**: High-performance range-splitting for bulk operations
- **Multiple Scanner Support**: Etherscan, Blockscout, Moralis, and custom scanners

### Key Classes
- `ChainscanClient`: **PRIMARY** unified client for cross-scanner logical method calls (recommended interface)
- `Client`: Main client class with module instances (legacy - maintained for backward compatibility)
- `Network`: HTTP handling with throttling and error management
- `UrlBuilder`: URL construction for different blockchain APIs
- `BaseModule`: Abstract base for all API modules
- `Scanner`: Abstract base for scanner implementations

## Supported Networks

### Primary Scanner Providers
- **Etherscan API**: Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, Fantom, Gnosis, and more EVM chains (Base supported via Etherscan V2)
- **BlockScout**: Public blockchain explorers (no API key required) - Ethereum, Sepolia, Gnosis, Polygon, Optimism, Arbitrum, Base, Scroll, Linea, and others
- **Moralis**: Multi-chain Web3 API - Ethereum, BSC, Polygon, Arbitrum, Base, Optimism, Avalanche, and more
- **RoutScan**: Mode network explorer

### Key Features by Provider
- **Etherscan**: Full API coverage, requires API keys, supports most EVM networks
- **Blockscout**: Free public APIs, GraphQL support for some operations, good for development
- **Moralis**: Rich metadata, modern REST API, requires API key, excellent multi-chain support

## Module Structure
```
aiochainscan/
├── __init__.py        # Main exports and facade functions (legacy + new)
├── client.py          # Legacy Client class (backward compatibility)
├── core/              # Unified architecture components
│   ├── client.py      # ChainscanClient - primary unified interface
│   ├── method.py      # Method enum - logical operations
│   └── endpoint.py    # EndpointSpec - endpoint configuration
├── scanners/          # Scanner implementations
│   ├── base.py        # Scanner abstract base class
│   ├── _etherscan_like.py # Shared Etherscan-style implementation
│   ├── etherscan_v2.py    # Etherscan API v2
│   ├── blockscout_v1.py   # BlockScout implementation
│   ├── moralis_v1.py      # Moralis Web3 API
│   └── routscan_v1.py     # RoutScan implementation
├── adapters/          # Hexagonal architecture adapters
│   ├── aiohttp_client.py
│   ├── aiohttp_graphql_client.py
│   ├── blockscout_graphql_builder.py
│   ├── endpoint_builder_urlbuilder.py
│   ├── memory_cache.py
│   ├── noop_telemetry.py
│   ├── retry_exponential.py
│   ├── simple_provider_federator.py
│   ├── simple_rate_limiter.py
│   └── structlog_telemetry.py
├── services/          # Business logic services
│   ├── account.py      # Account operations
│   ├── block.py        # Block operations
│   ├── contract.py     # Contract operations
│   ├── gas.py         # Gas operations
│   ├── logs.py        # Log operations
│   ├── proxy.py       # Proxy operations
│   ├── stats.py       # Network statistics
│   ├── token.py       # Token operations
│   ├── transaction.py # Transaction operations
│   └── ...           # Additional services
├── domain/            # Domain models and DTOs
│   ├── models.py       # Value objects (Address, TxHash, etc.)
│   └── dto.py          # Data transfer objects
├── modules/           # Legacy module-based API
│   ├── account.py      # Account module
│   ├── block.py        # Block module
│   ├── contract.py     # Contract module
│   ├── gas_tracker.py  # Gas tracker module
│   ├── logs.py        # Logs module
│   ├── proxy.py       # Proxy module
│   ├── stats.py       # Stats module
│   ├── token.py       # Token module
│   └── transaction.py # Transaction module
├── network.py         # HTTP client with throttling
├── exceptions.py      # Custom exceptions
├── config.py          # Configuration management
└── ...               # Additional utilities
```

## Key Features

### Unified ChainscanClient (Primary Interface)
```python
# Unified client for all blockchain scanners
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

# Create client for any scanner using simple config
client = ChainscanClient.from_config('blockscout', 'v1', 'blockscout_eth', 'eth')

# Use logical methods - scanner details hidden under the hood
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
logs = await client.call(Method.EVENT_LOGS, address='0x...', **params)

# Easy scanner switching - same interface for all!
client = ChainscanClient.from_config('etherscan', 'v2', 'eth', 'main')
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')

# Use Base network through Etherscan V2 (chain_id 8453)
client = ChainscanClient.from_config('etherscan', 'v2', 'base', 'main')
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
```

### Legacy Facade API (Backward Compatibility)
```python
# Simple async functions for common operations (legacy interface)
from aiochainscan import get_balance, get_block, get_all_transactions_optimized

# Get balance (works with Blockscout - no API key needed)
balance = await get_balance(
    address='0x...',
    api_kind='blockscout_sepolia',
    network='sepolia',
    api_key=''
)

# Get block info (Etherscan - requires API key)
block = await get_block(
    tag=17000000,
    full=False,
    api_kind='eth',
    network='main',
    api_key='YOUR_API_KEY'
)

# Optimized bulk operations with range splitting
transactions = await get_all_transactions_optimized(
    address='0x...',
    api_kind='eth',
    network='main',
    api_key='YOUR_API_KEY',
    max_concurrent=5
)
```

### Dependency Injection with ChainscanClient
```python
# Customizable rate limiting, retries, and HTTP clients
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method
from aiochainscan.adapters.simple_rate_limiter import SimpleRateLimiter
from aiochainscan.adapters.retry_exponential import ExponentialBackoffRetry

rate_limiter = SimpleRateLimiter(requests_per_second=1)
retry_policy = ExponentialBackoffRetry(attempts=3)

client = ChainscanClient(
    scanner_name='etherscan',
    scanner_version='v2',
    api_kind='eth',
    network='main',
    api_key='YOUR_API_KEY',
    throttler=rate_limiter,
    retry_options=retry_policy
)

balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
await client.close()
```

### Legacy Dependency Injection
```python
# Legacy interface with dependency injection
from aiochainscan import get_balance, SimpleRateLimiter, ExponentialBackoffRetry

rate_limiter = SimpleRateLimiter(requests_per_second=1)
retry_policy = ExponentialBackoffRetry(attempts=3)

balance = await get_balance(
    address='0x...',
    api_kind='eth',
    network='main',
    api_key='YOUR_API_KEY',
    rate_limiter=rate_limiter,
    retry=retry_policy
)
```

## Why ChainscanClient is the Primary Interface

The **ChainscanClient** is the recommended interface because it provides:

### 🎯 **Universal Scanner Support**
- Single interface for all blockchain scanners (Etherscan, BlockScout, Moralis, etc.)
- Automatic method routing based on scanner capabilities
- Consistent API regardless of underlying scanner implementation

### 🔧 **Logical Method Calls**
- Use logical operations (`Method.ACCOUNT_BALANCE`, `Method.EVENT_LOGS`) instead of API-specific parameters
- Scanner details (URLs, authentication, parameter mapping) hidden under the hood
- Type-safe method enum for better IDE support

### 🚀 **Easy Scanner Switching**
```python
# Switch from BlockScout to Etherscan with one line change
client = ChainscanClient.from_config('blockscout', 'v1', 'blockscout_eth', 'eth')
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')

# Same code works with Etherscan
client = ChainscanClient.from_config('etherscan', 'v2', 'eth', 'main')
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
```

### 📊 **Method Discovery**
- `client.get_supported_methods()` - see what methods are available
- `client.supports_method(Method.EVENT_LOGS)` - check method support
- `ChainscanClient.list_scanner_capabilities()` - view all scanner capabilities

### 🏗️ **Production Ready**
- Comprehensive error handling
- Dependency injection support
- Real-world tested with multiple scanners
- Consistent response formats

## Configuration

### Environment Variables
```bash
# API Keys (set as needed)
ETHERSCAN_KEY=your_etherscan_api_key
MORALIS_API_KEY=your_moralis_api_key
# Blockscout works without API keys

## Development Guidelines

### Code Quality Standards
- **Linting**: `ruff check` and `ruff format`
- **Type Safety**: `mypy --strict` compatibility
- **Testing**: `pytest` with comprehensive coverage
- **Documentation**: Google-style docstrings for public APIs

## Adding New Scanners

The library supports adding new blockchain scanners through a plugin system. See the scanner implementations in `aiochainscan/scanners/` for examples of how to add support for new APIs.

## Hexagonal Architecture

The project implements hexagonal architecture with clear separation of concerns:

- **Domain**: Pure business models and value objects (`domain/` module)
- **Ports**: Protocol interfaces for external dependencies (`ports/` module)
- **Services**: Business logic implementing use cases (`services/` module)
- **Adapters**: Concrete implementations of ports (`adapters/` module)
- **Facade**: Public API composition layer (`__init__.py` and `core/` modules)

This architecture enables:
- Easy testing through dependency injection
- Flexible technology swapping (HTTP client, cache, telemetry)
- Clean separation of business logic from infrastructure concerns
- LLM-friendly code structure for maintainability

## 🆕 **Moralis Web3 Data API Integration**

Successfully integrated Moralis Web3 Data API as a modern multi-chain scanner with RESTful endpoints and rich metadata support.

## Hexagonal Architecture Implementation Status

The hexagonal architecture has been successfully implemented with clear separation of concerns:

### ✅ **Completed Layers**
- **Domain**: Pure value objects and business models in `domain/` module
- **Ports**: Protocol interfaces in `ports/` module for external dependencies
- **Services**: Business logic in `services/` module implementing use cases
- **Adapters**: Concrete implementations in `adapters/` module
- **Facade**: Public API in `__init__.py` and `core/` modules

### ✅ **Architecture Benefits Achieved**
- **Testability**: Dependency injection enables comprehensive testing
- **Flexibility**: Easy swapping of HTTP clients, caches, telemetry backends
- **Maintainability**: Clear separation of business logic from infrastructure
- **Extensibility**: Adding new scanners or features follows established patterns

### 🔄 **Migration Status**
- **Phase 1**: ✅ Core hexagonal architecture implemented
- **Phase 2**: ✅ ChainscanClient as primary unified interface
- **Phase 3**: ✅ Legacy interfaces maintained for backward compatibility
- **Future**: Enhanced type safety and performance optimizations

### 📋 **Dependency Rules**
- **Domain** → **Ports** → **Services** → **Adapters** → **Facade**
- No cycles allowed; only rightward dependencies
- Clean interfaces between layers enable technology swapping
