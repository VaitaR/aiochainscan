# aiochainscan Project Overview

## Project Purpose
Async Python wrapper for blockchain explorer APIs (Etherscan, BSCScan, PolygonScan, etc.). Provides unified interface for querying blockchain data across multiple networks with both legacy and modern unified architectures.

## Architecture

### Core Components
- **Legacy Client**: Original module-based entry point for backward compatibility
- **Network**: HTTP client with throttling, retries, and dual backend support (aiohttp/curl_cffi)
- **UrlBuilder**: Constructs API URLs for different blockchain networks
- **Modules**: API endpoint implementations (account, block, contract, transaction, etc.)

### 🆕 **Unified Scanner Architecture (Production Ready)**
- **ChainscanClient**: Unified client providing logical method calls across different scanner APIs
- **Method Enum**: Type-safe logical operations (ACCOUNT_BALANCE, TX_BY_HASH, etc.)
- **Scanner Registry**: Plugin system for different blockchain explorer implementations
- **EndpointSpec**: Declarative endpoint configuration with parameter mapping and response parsing
- **5 Working Scanner Implementations**: EtherscanV1, EtherscanV2, BaseScanV1, BlockScoutV1, RoutScanV1

### Key Classes
- `Client`: Main client class with module instances (legacy - maintained for backward compatibility)
- `ChainscanClient`: **NEW** unified client for cross-scanner logical method calls
- `Network`: HTTP handling with throttling and error management
- `UrlBuilder`: URL construction for different blockchain APIs
- `BaseModule`: Abstract base for all API modules
- `Scanner`: **NEW** abstract base for scanner implementations

## Supported Scanners & Networks

### Production Ready Scanners (6 implementations):
1. **EtherscanV1** - Standard Etherscan API format
   - Networks: Ethereum (main, goerli, sepolia), BSC, Polygon, etc.
   - Methods: 17 (full feature set)
   - Auth: API key via query parameter

2. **EtherscanV2** - Multichain Etherscan format
   - Networks: Ethereum, BSC, Polygon, Arbitrum, Optimism, etc.
   - Methods: 7 (core methods)
   - Auth: API key via query parameter

3. **BaseScanV1** - Base network scanner (inherits from EtherscanV1)
   - Networks: Base (main, goerli, sepolia)
   - Methods: 17 (inherited)
   - Auth: API key via query parameter

4. **BlockScoutV1** - Public blockchain explorer (inherits from EtherscanV1)
   - Networks: Sepolia, Gnosis, Polygon, and many others
   - Methods: 17 (inherited)
   - Auth: Optional API key (works without)

5. **RoutScanV1** - Mode network explorer
   - Networks: Mode (chain ID 34443)
   - Methods: 7 (core methods)
   - Auth: Optional API key (works without)

6. **MoralisV1** - Moralis Web3 Data API (NEW)
   - Networks: Ethereum, BSC, Polygon, Arbitrum, Base, Optimism, Avalanche
   - Methods: 7 (core Web3 methods)
   - Auth: API key via X-API-Key header (required)
   - Features: RESTful API, multi-chain support, rich metadata

### Legacy Module Support
- Ethereum (etherscan.io)
- BSC (bscscan.com)
- Polygon (polygonscan.com)
- Optimism, Arbitrum, Fantom, Gnosis, Flare, Wemix, Chiliz, Mode, Linea, Blast, Base

## Module Structure
```
aiochainscan/
├── client.py          # Legacy Client class (backward compatibility)
├── core/              # ✅ Unified architecture components
│   ├── client.py      # ChainscanClient - unified interface
│   ├── method.py      # Method enum - logical operations
│   ├── endpoint.py    # EndpointSpec - endpoint configuration
│   └── __init__.py
├── scanners/          # ✅ Scanner implementations (5 working)
│   ├── base.py        # Scanner abstract base class
│   ├── etherscan_v1.py # Etherscan API v1 (17 methods)
│   ├── etherscan_v2.py # Etherscan API v2 (7 methods)
│   ├── basescan_v1.py  # BaseScan (inherits EtherscanV1)
│   ├── blockscout_v1.py # BlockScout (public API)
│   ├── routscan_v1.py  # RoutScan (Mode network)
│   └── __init__.py    # Scanner registry system
├── network.py         # HTTP client with throttling
├── url_builder.py     # URL construction logic
├── exceptions.py      # Custom exceptions
├── config.py          # Advanced configuration system
├── common.py          # Chain features and utilities
└── modules/           # Legacy API modules
    ├── account.py, block.py, contract.py, etc.
    └── extra/
        ├── links.py   # Explorer link generation
        └── utils.py   # Utility functions
```

## Key Features

### Unified Interface
```python
# Same code works with any scanner
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

# Etherscan
client = ChainscanClient.from_config('etherscan', 'v1', 'eth', 'main')
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')

# BlockScout (no API key needed)
client = ChainscanClient.from_config('blockscout', 'v1', 'blockscout_sepolia', 'sepolia')
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')

# RoutScan (Mode network)
client = ChainscanClient.from_config('routscan', 'v1', 'routscan_mode', 'mode')
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')

# Moralis (multi-chain Web3 API) - NEW
client = ChainscanClient(
    scanner_name='moralis', scanner_version='v1',
    api_kind='moralis', network='eth', api_key='YOUR_MORALIS_KEY'
)
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
tokens = await client.call(Method.TOKEN_BALANCE, address='0x...')
```

### Backward Compatibility
```python
# Legacy API still works
from aiochainscan import Client

client = Client("YOUR_API_KEY", "eth", "main")
balance = await client.account.balance("0x...")
```

## Configuration System

### Environment Variables
```bash
# API Keys
ETHERSCAN_KEY=your_etherscan_api_key
BASESCAN_KEY=your_basescan_api_key
MORALIS_API_KEY=your_moralis_api_key
# BlockScout and RoutScan work without API keys

# Configuration
AIOCHAINSCAN_CONFIG_PATH=/path/to/config.json
```

### Config File Support
```json
{
  "scanners": {
    "custom_scanner": {
      "name": "Custom Scanner",
      "base_domain": "api.custom.com",
      "currency": "CUSTOM",
      "supported_networks": ["main", "testnet"],
      "requires_api_key": true
    }
  }
}
```

## Development Guidelines

### Code Quality Standards
- **Linting**: All code must pass `ruff check` (297 tests pass)
- **Type Safety**: Full type hints with `mypy --strict` compatibility
- **Testing**: Comprehensive test coverage with `pytest`
- **Documentation**: Google-style docstrings for all public APIs

### Testing Strategy
- **Unit Tests**: All core components and scanner implementations
- **Integration Tests**: Real API calls with multiple scanners
- **Mocking**: Network calls mocked for reliable CI/CD
- **Error Handling**: Comprehensive error scenarios covered
 - **Typing**: CI enforces `mypy --strict` on `aiochainscan/`. Run locally via `uv run mypy --strict aiochainscan`.

---

## 📋 Guide: Adding New Scanner Implementations

This guide is based on successful implementation of 5 different scanner types during development.

### 🎯 Scanner Implementation Approaches

#### **Approach 1: Inheritance (RECOMMENDED for Etherscan-compatible APIs)**
**Use when**: New scanner has identical API structure to existing scanner
**Example**: BaseScan (identical to Etherscan)

**Pros**: ✅ Minimal code (25 lines), automatic updates, zero maintenance
**Cons**: ⚠️ Limited to identical APIs

```python
# ✅ BaseScan implementation (successful)
@register_scanner
class BaseScanV1(EtherscanV1):
    name = "basescan"
    version = "v1"
    supported_networks = {"main", "goerli", "sepolia"}
    # All SPECS and logic inherited from EtherscanV1
```

#### **Approach 2: Custom URL Handling (for similar APIs with different URL structure)**
**Use when**: API is Etherscan-compatible but uses different URL patterns
**Example**: BlockScout (different instances per network)

**Pros**: ✅ Reuses most logic, handles URL variations
**Cons**: ⚠️ Requires custom `__init__` and `call` methods

```python
# ✅ BlockScout implementation (successful)
@register_scanner
class BlockScoutV1(EtherscanV1):
    name = "blockscout"
    supported_networks = {"sepolia", "gnosis", "polygon", ...}

    def __init__(self, api_key: str, network: str, url_builder: UrlBuilder):
        # Custom initialization for network-specific instances
        super().__init__(api_key, network, url_builder)

    async def call(self, method: Method, **params):
        # Custom URL building for BlockScout instances
        # Uses aiohttp directly, bypasses standard Network class
```

#### **Approach 3: Complete Custom Implementation (for unique APIs)**
**Use when**: API has completely different structure
**Example**: RoutScan (chain ID in URL path), OKLink (removed - was problematic)

**Pros**: ✅ Full control, handles any API structure
**Cons**: ⚠️ Most code, requires maintenance

```python
# ✅ RoutScan implementation (successful)
@register_scanner
class RoutScanV1(Scanner):
    name = "routscan"
    NETWORK_CHAIN_IDS = {"mode": "34443"}

    async def call(self, method: Method, **params):
        # Completely custom URL building
        base_url = f"https://api.routescan.io/v2/network/mainnet/evm/{self.chain_id}"
        full_url = base_url + spec.path
        # Direct aiohttp usage
```

### 📝 Step-by-Step Implementation Process

#### **Step 1: Research & Planning**
1. **API Documentation**: Study target API structure thoroughly
2. **Compare with Existing**: Identify similarity to EtherscanV1/V2
3. **Choose Approach**: Inheritance → Custom URL → Complete Custom
4. **Network Mapping**: Document supported networks and their identifiers

#### **Step 2: Configuration Setup**
Add scanner configuration to `aiochainscan/config.py`:

```python
# ✅ Add to BUILTIN_SCANNERS
'new_scanner': ScannerConfig(
    name='New Scanner',
    base_domain='api.newscanner.com',
    currency='TOKEN',
    supported_networks={'main', 'testnet'},
    requires_api_key=True,  # or False for public APIs
    special_config={'custom_field': 'value'} if needed
),
```

#### **Step 3: URL Builder Updates**
Add to `aiochainscan/url_builder.py`:

```python
# ✅ Add to _API_KINDS
'new_scanner': ('api.newscanner.com', 'TOKEN'),

# ✅ Handle special URL structure in _get_api_url() if needed
elif self._api_kind == 'new_scanner':
    prefix = 'custom-prefix'  # or None for direct /api
```

#### **Step 4: Scanner Implementation**
Create `aiochainscan/scanners/new_scanner_v1.py`:

```python
@register_scanner
class NewScannerV1(Scanner):  # or inherit from EtherscanV1
    name = "new_scanner"
    version = "v1"
    supported_networks = {"main", "testnet"}
    auth_mode = "query"  # or "header"
    auth_field = "apikey"  # or custom field name

    SPECS = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method="GET",
            path="/api",  # or custom path
            query={"module": "account", "action": "balance"},
            param_map={"address": "address"},  # map generic → specific
            parser=PARSERS['etherscan'],  # or custom parser
        ),
        # ... more method specifications
    }
```

#### **Step 5: Registry Integration**
Add import to `aiochainscan/scanners/__init__.py`:

```python
# ✅ Add import (at bottom to avoid circular imports)
from .new_scanner_v1 import NewScannerV1  # noqa: E402

# ✅ Add to __all__
__all__ = [
    # ... existing scanners
    'NewScannerV1',
]
```

#### **Step 6: Testing Strategy**

**Create test file** `test_new_scanner.py`:
```python
#!/usr/bin/env python3
"""Test new scanner implementation."""

import asyncio
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

async def test_new_scanner():
    client = ChainscanClient(
        scanner_name='new_scanner',
        scanner_version='v1',
        api_kind='new_scanner',
        network='main',
        api_key='test_key'
    )

    # Test basic functionality
    result = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
    print(f"Result: {result}")

    await client.close()

if __name__ == "__main__":
    asyncio.run(test_new_scanner())
```

**Run comprehensive testing**:
```bash
# ✅ Code quality
python3 -m ruff check . --fix
python3 -m pytest tests/ -v

# ✅ Integration test
python3 test_new_scanner.py
```

### 🚀 What Worked (Successful Patterns)

#### **✅ Inheritance for Compatible APIs**
- **BaseScan**: 25 lines of code, zero maintenance
- **BlockScout**: Inherited 17 methods, custom URL handling only

#### **✅ Direct aiohttp for Custom URLs**
- **BlockScout**: Bypassed Network class for instance-specific URLs
- **RoutScan**: Used aiohttp directly for non-standard URL patterns

#### **✅ Gradual Feature Addition**
- Start with 1-2 core methods (ACCOUNT_BALANCE, ACCOUNT_TRANSACTIONS)
- Add more methods incrementally
- Test each method individually

#### **✅ Proper Error Handling**
- Custom error messages with scanner context
- Graceful handling of API-specific error formats
- Rate limiting detection and reporting

#### **✅ Configuration-Driven Design**
- Scanner settings in `config.py`
- Environment variable integration
- Network validation through configuration

### ⚠️ What Didn't Work (Lessons Learned)

#### **❌ OKLink Integration Challenges (removed)**
**Issues encountered**:
- Complex parameter mapping (chainShortName requirements)
- Header-based authentication vs query-based
- Non-standard response formats
- Risk control blocking with certain addresses
- API restrictions for "scam" addresses

**Lessons**:
- Research API restrictions thoroughly
- Test with multiple addresses
- Understand API's risk management policies
- Consider API stability and access policies

#### **❌ Over-Engineering Initial Implementations**
**Mistakes**:
- Trying to handle all edge cases initially
- Complex parameter transformation logic
- Premature optimization

**Better approach**:
- Start simple, add complexity gradually
- Focus on core methods first
- Iterate based on real usage

#### **❌ Insufficient URL Structure Research**
**Problems**:
- Wrong assumptions about URL patterns
- Missing chain ID requirements
- Incorrect subdomain usage

**Solution**:
- Study API documentation thoroughly
- Test URL building manually first
- Verify with actual API calls

### 🎯 Best Practices for New Scanners

#### **Code Organization**
1. **Single Responsibility**: Each scanner handles one API provider
2. **Clear Inheritance**: Use inheritance only for truly compatible APIs
3. **Descriptive Names**: Clear scanner names reflecting their purpose
4. **Comprehensive Documentation**: Document all custom behavior

#### **Testing Strategy**
1. **Start with Real APIs**: Test against actual endpoints early
2. **Handle Rate Limits**: Expect and handle rate limiting gracefully
3. **Multiple Addresses**: Test with various address types
4. **Error Scenarios**: Test invalid addresses, networks, methods

#### **Configuration Management**
1. **Environment Variables**: Support standard API key patterns
2. **Network Validation**: Validate networks at client creation
3. **Flexible Authentication**: Support both query and header auth
4. **Optional API Keys**: Design for APIs that work without keys

#### **Performance Considerations**
1. **Efficient HTTP**: Reuse connections where possible
2. **Proper Async**: Use async/await correctly throughout
3. **Resource Cleanup**: Always close HTTP sessions
4. **Error Recovery**: Implement retry logic for transient failures

### 🔄 Maintenance and Updates

#### **Regular Maintenance Tasks**
1. **API Changes**: Monitor for breaking changes in external APIs
2. **Test Updates**: Keep integration tests current
3. **Documentation**: Update examples and guides
4. **Dependencies**: Keep HTTP libraries updated

#### **Version Management**
1. **Scanner Versioning**: Use version numbers for scanner implementations
2. **Backward Compatibility**: Maintain legacy interfaces
3. **Migration Guides**: Document breaking changes clearly
4. **Deprecation Notices**: Give advance warning for removals

### 📊 Current Implementation Status

| Scanner | Status | Methods | Networks | Complexity | Maintenance |
|---------|--------|---------|----------|------------|-------------|
| **EtherscanV1** | ✅ Production | 17 | 4+ | Medium | Low |
| **EtherscanV2** | ✅ Production | 7 | 8+ | Medium | Low |
| **BaseScanV1** | ✅ Production | 17 | 3 | Very Low | Minimal |
| **BlockScoutV1** | ✅ Production | 17 | 8+ | Medium | Low |
| **RoutScanV1** | ✅ Production | 7 | 1 | High | Medium |

**Total: 6 working scanner implementations supporting 40+ networks with 80+ unified methods.**

---

## 🆕 **Moralis Web3 Data API Integration**

### Overview
Successfully integrated Moralis Web3 Data API as the 6th scanner implementation in the aiochainscan unified architecture. This integration demonstrates the flexibility and extensibility of the scanner system.

### Implementation Approach
**Pattern Used**: Complete Custom Implementation (Approach 3)
- **Why**: Moralis uses completely different API structure (RESTful vs query-based)
- **Authentication**: Header-based (`X-API-Key`) vs query-based (`apikey`)
- **URL Structure**: Path parameters (`/wallets/{address}/balance`) vs query modules
- **Response Format**: Direct JSON objects vs `{"result": data}` wrapper

### Key Features
- **Multi-chain Support**: 7 major EVM networks (ETH, BSC, Polygon, Arbitrum, Base, Optimism, Avalanche)
- **RESTful Design**: Modern API endpoints with path parameters
- **Rich Metadata**: Enhanced transaction and token data
- **Header Authentication**: Secure API key handling
- **Custom Parsers**: Specialized response parsing for Moralis format

### Architecture Integration
```python
# Following established patterns from RoutScanV1 and BlockScoutV1
@register_scanner
class MoralisV1(Scanner):
    name = "moralis"
    version = "v1"
    auth_mode = "header"
    auth_field = "X-API-Key"

    # Custom call() method for RESTful endpoints
    # Direct aiohttp usage for non-standard URL patterns
    # Chain ID mapping for multi-chain support
```

### Supported Methods (7 core methods)
- `ACCOUNT_BALANCE` → `/wallets/{address}/balance`
- `ACCOUNT_TRANSACTIONS` → `/wallets/{address}/history`
- `TOKEN_BALANCE` → `/wallets/{address}/tokens`
- `ACCOUNT_ERC20_TRANSFERS` → `/wallets/{address}/tokens/transfers`
- `TX_BY_HASH` → `/transaction/{txhash}`
- `BLOCK_BY_NUMBER` → `/block/{block_number}`
- `CONTRACT_ABI` → `/contracts/{address}`

### Configuration Added
- **Config System**: Added to `BUILTIN_SCANNERS` with multi-chain mappings
- **URL Builder**: Added Moralis domain support
- **Parsers**: 4 custom parsers for Moralis response formats
- **Environment**: `MORALIS_API_KEY` support

### Usage Example
```python
# Multi-chain balance checking with same interface
networks = ['eth', 'bsc', 'polygon', 'arbitrum', 'base']
address = "0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3"

for network in networks:
    client = ChainscanClient(
        scanner_name='moralis', scanner_version='v1',
        api_kind='moralis', network=network,
        api_key=os.getenv('MORALIS_API_KEY')
    )

    balance = await client.call(Method.ACCOUNT_BALANCE, address=address)
    tokens = await client.call(Method.TOKEN_BALANCE, address=address)

    print(f"{network}: {balance} wei, {len(tokens)} tokens")
    await client.close()
```

### Testing & Quality Assurance
- **Code Quality**: Passes `ruff check` (PEP 8 compliance)
- **Type Safety**: Full type hints throughout
- **Integration Test**: Created `test_moralis_integration.py`
- **Registry Test**: Verified scanner registration
- **Multi-chain Test**: Tested all 7 supported networks
- **Error Handling**: Enhanced error messages with chain context

### Lessons Applied from Project Guidelines
1. **Inheritance Strategy**: Used direct `Scanner` inheritance (not `EtherscanV1`) due to API differences
2. **URL Handling**: Custom `call()` method following `RoutScanV1` pattern
3. **Authentication**: Proper header-based auth implementation
4. **Error Handling**: Chain-specific error context
5. **Testing**: Comprehensive integration testing
6. **Documentation**: Complete documentation update

### Performance & Limitations
- **Performance**: Direct aiohttp usage for optimal speed
- **Rate Limiting**: Inherits from Moralis API limits
- **API Coverage**: 7 core methods (expandable to 20+ as needed)
- **Network Support**: 7 EVM chains (expandable)

### Future Enhancements
- **Additional Methods**: Easy to add more Moralis endpoints
- **Caching**: Could add response caching for repeated queries
- **Batch Requests**: Moralis supports batch operations
- **WebSocket**: Could add real-time data streaming

This integration serves as a reference implementation for adding complex, modern Web3 APIs to the aiochainscan ecosystem while maintaining backward compatibility and architectural consistency.

---

This guide reflects real-world experience implementing 6 different scanner types, including successful patterns and actual failures encountered during development.

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

### Directory plan (added under `aiochainscan/`)
- `domain/` (new)
- `ports/` (new)
- `services/` (new)
- `adapters/` (new)

Keep existing modules (`core/`, `modules/`, `scanners/`, `network.py`, `url_builder.py`) intact initially. Do not change `fastabi` paths or build settings.

### First slice (minimal but valuable)
1) Create packages: `aiochainscan/domain`, `aiochainscan/ports`, `aiochainscan/services`, `aiochainscan/adapters` (each with `__init__.py`).
2) Domain models: add `aiochainscan/domain/models.py` with clean VO/aliases (e.g., `Address`, `BlockNumber`, `TxHash`). Gradually migrate existing dataclasses that are truly pure. Do not move config managers or any I/O.
3) HTTP port: `aiochainscan/ports/http_client.py` with `Protocol`:
   - `async def get(url: str, params: Mapping[str, Any] | None = None) -> Any`
   - `async def post(url: str, data: Any | None = None, json: Any | None = None) -> Any`
4) HTTP adapter (canonical): `aiochainscan/adapters/aiohttp_client.py` implementing the port using `aiohttp.ClientSession` with proper lifecycle and `raise_for_status()`.
5) Service: `aiochainscan/services/account.py` exposing `async def get_address_balance(address: Address, network: str, api_kind: str, api_key: str | None) -> int`.
   - Build URL using existing `url_builder` (temporarily). Inject the HTTP port. Parse response via existing parsers if appropriate.
6) Facade: add new re-exports in `aiochainscan/__init__.py`:
   - `from .domain.models import Address` (and other VO as they appear)
   - `from .services.account import get_address_balance`
   Preserve existing exports (`Client`, `config`, etc.).
7) Backward compatibility: keep old imports working via re-exports in their original modules when feasible (e.g., thin aliasing in `config.py`). Avoid warnings in this phase.

### DTO policy (Phase 1)
- Use `TypedDict`/dataclasses for DTO validation at boundaries; keep domain models pydantic-free.
- Consider Pydantic later if needed; not required now.

### Import-linter contracts (initial)
- Add import-linter to dev dependencies and CI.
- Contracts (soft to start):
  - `domain` must not import from `aiochainscan.ports`, `services`, `adapters`, `core`, `modules`, `scanners`.
  - `ports` must not import from `services`, `adapters`, `core`, `modules`, `scanners`.
  - `services` may import `domain`, `ports`, and selected legacy helpers (`url_builder` temporarily) but not `adapters`.
  - `adapters` may import `ports` (and stdlib/third-party), not `services` or `domain`.
  - `facade` can import from anywhere; it is the composition edge.

### Quality gates
- `pytest -q` green (all existing tests must pass).
- `ruff` passes; formatting unchanged unless touched code requires it.
- `mypy --strict` passes for new code; avoid `Any` in public APIs.
- `import-linter` passes with initial contracts.

### Risks and mitigations
- **Cyclic imports**: Only move pure VO to `domain`. Use lazy imports in services if needed; keep adapters isolated.
- **Import paths compatibility**: Re-export names in original modules and in `__init__` to keep old imports working.
- **HTTP lifecycle**: Provide context manager or explicit `close()` in adapter; reuse session in services; no unclosed sessions.
- **Stack choice**: Use `aiohttp` (already a dependency). Add retries/timeouts where appropriate.
- **`url_builder` coupling**: Inject it as a function/dependency in the service to avoid cycles; later promote to a dedicated port.

### Definition of Done (Phase 1)
- New packages created and wired.
- `domain/models.py` exists with initial VO (`Address`, etc.) and re-exported via `aiochainscan/__init__.py`.
- `ports/http_client.py` and `adapters/aiohttp_client.py` implemented.
- `services/account.py:get_address_balance` implemented and exported via facade.
- All tests green; `mypy --strict`, `ruff`, and `import-linter` pass.

### Next iterations (high level)
- Add services for block/transaction reads.
- Extract `endpoint builder` into a port and its adapter; reduce reliance on legacy modules.
- Introduce DTO validation where responses are complex; consider Pydantic if/when it adds value.

### Progress log (brief)
- Phase 1: added domain VOs (`Address`, `TxHash`, `BlockNumber`), `HttpClient` port with `AiohttpClient` adapter, services for balance/block/transaction, and facade functions (`get_balance`, `get_block`, `get_transaction`). CI enforces import-linter.
- Added `EndpointBuilder` port with `UrlBuilder` adapter; refactored services to use it (no direct dependency on `url_builder` inside services).
- Added `get_token_balance` service and a simple facade helper `get_token_balance_facade` for convenience.

## Hexagonal Architecture – Current Stage (Phase 1 slice complete)

### What is in place
- domain: value objects (`Address`, `TxHash`, `BlockNumber`)
- ports: `HttpClient`, `EndpointBuilder`
- adapters: `AiohttpClient`, `UrlBuilderEndpoint`
- services: balance, block, transaction, token balance, gas oracle (all consume ports)
- facade: top-level helpers in `aiochainscan/__init__.py` with re-exports preserved
- dependency control: import-linter contracts enabled in CI and passing
- quality: `mypy --strict`, `ruff`, and tests are green; a flaky integration test is excluded from fast pre-push, still executed in CI
- URL decoupling: services use `EndpointBuilder` port (no direct dependency on `url_builder`)

### Risks / technical debt
- Legacy layer (`modules/*`, parts of `network.py`) still active in parallel; needs gradual migration/consolidation
- DTO/validation not standardized yet; services return provider-shaped payloads
- No unified structlog-based tracing/logging in adapters/services
- Cache/retries/rate limiting exist only in legacy; not modeled as ports
- Facade naming has minor inconsistency (`get_token_balance_facade` vs `get_balance`)

### Next steps (prioritized)
1) Service coverage: add services for logs, stats, proxy reads via `EndpointBuilder`
2) DTO layer: introduce `TypedDict` for service inputs/outputs and a provider→domain normalization
3) Infra ports: add `Cache`, `RateLimiter`/`RetryPolicy`, `Telemetry` (+ adapters) and align behavior with legacy
4) Facade: standardize helper names (prefer `get_*` form) and keep backward-compatible aliases
5) Legacy migration: route `modules/*` through services or deprecate; reduce direct `network.py` usage
6) Import rules: gradually tighten import-linter contracts
7) Tests: unit-test new services/adapters with mocked ports; add DTO snapshot tests

### Short take
The hexagonal skeleton is in place and already useful. Next focus: broaden services, introduce DTO normalization, migrate legacy module paths, and add infrastructure ports (cache/retries/telemetry).

## Hexagonal Architecture – Phase 1.1 Progress Update

### Implemented (since last update)
- domain DTOs: `GasOracleDTO`, `BlockDTO`, `TransactionDTO`, `LogEntryDTO`, `EthPriceDTO`.
- ports (infra added): `Cache`, `RateLimiter`, `RetryPolicy`, `Telemetry`.
- adapters (infra): `InMemoryCache`, `SimpleRateLimiter`, `ExponentialBackoffRetry`, `NoopTelemetry`.
- services (+ normalization helpers):
  - account: `get_address_balance`
  - block: `get_block_by_number`, `normalize_block`
  - transaction: `get_transaction_by_hash`, `normalize_transaction`
  - token: `get_token_balance`, `normalize_token_balance`
  - gas: `get_gas_oracle`, `normalize_gas_oracle`
  - logs: `get_logs`, `normalize_log_entry`
  - stats: `get_eth_price`, `normalize_eth_price`
- facade helpers exported: `get_balance`, `get_block`, `get_transaction`, `get_token_balance` (+ alias `get_token_balance_facade`), `get_gas_oracle` (+ alias `get_gas_oracle_facade`), `get_logs`, `get_eth_price`.
- facade normalizers exported: `normalize_block`, `normalize_transaction`, `normalize_log_entry`, `normalize_gas_oracle`, `normalize_token_balance`, `normalize_eth_price`.
- legacy migration (non-breaking):
  - `modules/account.py:balance` → calls `get_balance` first (fallback to legacy).
  - `modules/token.py:token_balance` → calls `get_token_balance` first (fallback to legacy).
  - `modules/block.py:get_by_number` → calls `get_block` first (fallback to legacy).
  - `modules/transaction.py:get_by_hash` → calls `get_transaction` first (fallback to legacy).

### Not yet implemented (known gaps)
- services coverage: remaining `stats` endpoints; broader proxy reads where applicable.
- DTOs: normalization for more `stats` responses and other complex payloads.
- telemetry/logging: unify on structlog adapter and propagate through services by default.
- cache/policy composition: configurable TTLs, composition at facade-level (currently adapters exist but wired as optional parameters inside services).
- legacy routing: migrate `modules/stats.py` and `modules/logs.py` to services internally, keep public interface intact.
- import rules: tighten import-linter contracts stepwise as migration proceeds.

### Testing notes (local fast path)
- Prefer running only related tests when touching specific layers, e.g.:
  - `pytest -q tests/test_logs.py tests/test_stats.py`
  - `pytest -q tests/test_block.py tests/test_transaction.py tests/test_token.py`
- CI remains responsible for full-suite and type checks (`mypy --strict`).
