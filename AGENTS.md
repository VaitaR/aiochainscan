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
- `Client`: Main client class with module instances (legacy - maintained for backward compatibility)
- `ChainscanClient`: **NEW** unified client for cross-scanner logical method calls
- `Network`: HTTP handling with throttling and error management
- `UrlBuilder`: URL construction for different blockchain APIs
- `BaseModule`: Abstract base for all API modules
- `Scanner`: **NEW** abstract base for scanner implementations

## Supported Networks

### Primary Scanner Providers
- **Etherscan API**: Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, and other EVM chains
- **Blockscout**: Public blockchain explorers (no API key required) - Sepolia, Gnosis, Polygon, and others
- **Moralis**: Multi-chain Web3 API - Ethereum, BSC, Polygon, Arbitrum, Base, Optimism, Avalanche

### Key Features by Provider
- **Etherscan**: Full API coverage, requires API keys, supports most EVM networks
- **Blockscout**: Free public APIs, GraphQL support for some operations, good for development
- **Moralis**: Rich metadata, modern REST API, requires API key, excellent multi-chain support

## Module Structure
```
aiochainscan/
├── __init__.py        # Main exports and facade functions
├── client.py          # Legacy Client class (backward compatibility)
├── core/              # Unified architecture components
│   ├── client.py      # ChainscanClient - unified interface
│   ├── method.py      # Method enum - logical operations
│   └── endpoint.py    # EndpointSpec - endpoint configuration
├── scanners/          # Scanner implementations
│   ├── base.py        # Scanner abstract base class
│   ├── etherscan_v2.py # Etherscan API v2
│   ├── blockscout_v1.py # BlockScout implementation
│   └── moralis_v1.py   # Moralis Web3 API
├── adapters/          # Hexagonal architecture adapters
│   ├── aiohttp_client.py
│   ├── simple_rate_limiter.py
│   └── structlog_telemetry.py
├── services/          # Business logic services
│   ├── account.py      # Account operations
│   ├── block.py        # Block operations
│   └── stats.py        # Network statistics
├── domain/            # Domain models and DTOs
│   ├── models.py       # Value objects (Address, TxHash, etc.)
│   └── dto.py          # Data transfer objects
├── network.py         # HTTP client with throttling
├── exceptions.py      # Custom exceptions
└── config.py          # Configuration management
```

## Key Features

### Simple Facade API
```python
# Simple async functions for common operations
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

### Dependency Injection
```python
# Customizable rate limiting, retries, and HTTP clients
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

The project uses hexagonal architecture with clear separation of concerns:

- **Domain**: Pure business models and value objects
- **Ports**: Interfaces for external dependencies (HTTP, cache, telemetry)
- **Services**: Business logic implementing use cases
- **Adapters**: Concrete implementations of ports (aiohttp, in-memory cache)
- **Facade**: Public API composition layer

This architecture enables easy testing, flexible dependency injection, and technology swapping.

## 🆕 **Moralis Web3 Data API Integration**

Successfully integrated Moralis Web3 Data API as a modern multi-chain scanner with RESTful endpoints and rich metadata support.

## Hexagonal Architecture Migration Guide (Phase 1)

This section is the authoritative, living guide for migrating to a Hexagonal Architecture without breaking the public API. Keep it concise and update as we progress.

- **Intent**: Improve testability, evolvability, and LLM-friendly edits via clear layering and ports/adapters. Zero breaking changes in this phase.
- **Canonical choices**: `aiohttp` for HTTP; first use-case: address balance; introduce import-linter contracts.

### Layering and dependency rules
- **domain**: pure entities/value-objects/rules. No I/O, no logging, no env access.
- **ports**: Protocol/ABC for external deps (HTTP, cache, telemetry, rate-limits, endpoint builder later).
- **services**: use-cases/orchestration; compose domain through ports.
- **adapters**: concrete implementations of ports (e.g., `aiohttp`). Mapping DTO ↔ domain.
- **facade (public API)**: stable exports via `aiochainscan.__init__` (re-exports).
- Dependency direction: `domain -> ports -> services -> adapters -> facade` (no cycles; only rightward imports).
