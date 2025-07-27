# aiochainscan Project Overview

## Project Purpose
Async Python wrapper for blockchain explorer APIs (Chainscan, BSCScan, PolygonScan, etc.). Provides unified interface for querying blockchain data across multiple networks.

## Architecture

### Core Components
- **Client**: Main entry point, initializes all modules
- **Network**: HTTP client with throttling, retries, and dual backend support (aiohttp/curl_cffi)
- **UrlBuilder**: Constructs API URLs for different blockchain networks
- **Modules**: API endpoint implementations (account, block, contract, transaction, etc.)

### 🆕 **Unified Scanner Architecture (NEW)**
- **ChainscanClient**: Unified client providing logical method calls across different scanner APIs
- **Method Enum**: Type-safe logical operations (get_balance, get_tx_by_hash, etc.)
- **Scanner Registry**: Plugin system for different blockchain explorer implementations
- **EndpointSpec**: Declarative endpoint configuration with parameter mapping and response parsing

### Key Classes
- `Client`: Main client class with module instances (legacy)
- `ChainscanClient`: **NEW** unified client for cross-scanner logical method calls
- `Network`: HTTP handling with throttling and error management
- `UrlBuilder`: URL construction for different blockchain APIs
- `BaseModule`: Abstract base for all API modules
- `Scanner`: **NEW** abstract base for scanner implementations

## Supported Blockchains
- Ethereum (chainscan.io)
- BSC (bscscan.com)  
- Polygon (polygonscan.com)
- Optimism, Arbitrum, Fantom, Gnosis, Flare, Wemix, Chiliz, Mode, Linea, Blast, Base, XLayer

## Module Structure
```
aiochainscan/
├── client.py          # Legacy Client class
├── core/              # 🆕 NEW: Unified architecture components
│   ├── client.py      # ChainscanClient - unified interface
│   ├── method.py      # Method enum - logical operations
│   ├── endpoint.py    # EndpointSpec - endpoint configuration
│   └── __init__.py    
├── scanners/          # 🆕 NEW: Scanner implementations
│   ├── base.py        # Scanner abstract base class
│   ├── etherscan_v1.py # Etherscan API v1 implementation
│   ├── oklink_v1.py   # OKLink API v1 implementation
│   └── __init__.py    # Scanner registry system
├── network.py         # HTTP client with throttling
├── url_builder.py     # URL construction logic
├── exceptions.py      # Custom exceptions
├── modules/
│   ├── base.py        # BaseModule abstract class
│   ├── account.py     # Account-related API calls
│   ├── block.py       # Block data API calls
│   ├── contract.py    # Contract interaction APIs
│   ├── transaction.py # Transaction APIs
│   ├── token.py       # Token-related APIs
│   ├── stats.py       # Network statistics
│   ├── gas_tracker.py # Gas price tracking
│   ├── logs.py        # Event logs
│   ├── proxy.py       # JSON-RPC proxy methods
│   └── extra/
│       ├── utils.py   # Utility functions for bulk operations
│       └── links.py   # URL link helpers
```

## Key Features

### Legacy API (Maintained for Backward Compatibility)
```python
# Traditional per-module approach
client = Client.from_config('eth', 'main')
balance = await client.account.balance('0x...')
tx_list = await client.account.normal_txs('0x...')
await client.close()
```

### 🆕 **NEW: Unified Scanner API**
```python
# Single interface for all scanners
client = ChainscanClient.from_config('etherscan', 'v1', 'eth', 'main')

# Same logical calls work across different scanners
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address='0x...')

# Switch to different scanner with same code
xlayer_client = ChainscanClient.from_config('oklink', 'v1', 'xlayer', 'main')
balance = await xlayer_client.call(Method.ACCOUNT_BALANCE, address='0x...')
```

### 🔧 **Scanner Management**
```python
# List available scanners and their capabilities
scanners = ChainscanClient.get_available_scanners()
capabilities = ChainscanClient.list_scanner_capabilities()

# Check method support
if client.supports_method(Method.GAS_ORACLE):
    gas_price = await client.call(Method.GAS_ORACLE)
```

## 🚀 **NEW: Unified Architecture Benefits**

### 1. **Logical Method Abstraction**
- Same method call works across different scanner APIs
- Automatic parameter mapping (e.g., `startblock` vs `startBlockHeight`)
- Unified response parsing (e.g., Etherscan `result` vs OKLink `data`)

### 2. **Type-Safe Operations**
```python
from aiochainscan.core.method import Method

# IDE autocomplete and type checking
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
# vs error-prone string-based calls
```

### 3. **Scanner Plugin System**
```python
@register_scanner
class MyCustomScannerV1(Scanner):
    name = "mycustom"
    version = "v1" 
    supported_networks = {"main", "test"}
    
    SPECS = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method="GET",
            path="/balance",
            param_map={"address": "wallet"},
            parser=lambda r: r["balance"]
        )
    }
```

### 4. **Smart Parameter Mapping**
```python
# EndpointSpec automatically handles different parameter names
spec = EndpointSpec(
    param_map={
        "start_block": "startBlockHeight",  # OKLink style
        "end_block": "endBlockHeight",     # vs Etherscan "startblock"
    }
)
```

### 5. **Response Standardization**
```python
# Different response formats automatically normalized
etherscan_response = {"status": "1", "result": "1000"}  → "1000"
oklink_response = {"data": [{"balance": "1000"}]}      → {"balance": "1000"}
```

## 📊 **Current Scanner Support Matrix**

| Scanner | Version | Networks | Methods | Auth Mode |
|---------|---------|----------|---------|-----------|
| etherscan | v1 | main, test, goerli, sepolia | 17 | query (apikey) |
| oklink | v1 | main | 10 | header (OK-ACCESS-KEY) |

### 📈 **Method Coverage**
- `ACCOUNT_BALANCE` ✅ Etherscan, ✅ OKLink
- `ACCOUNT_TRANSACTIONS` ✅ Etherscan, ✅ OKLink  
- `TX_BY_HASH` ✅ Etherscan, ✅ OKLink
- `BLOCK_BY_NUMBER` ✅ Etherscan, ✅ OKLink
- `CONTRACT_ABI` ✅ Etherscan, ✅ OKLink
- `GAS_ORACLE` ✅ Etherscan, ❌ OKLink
- Plus 20+ more logical methods...

## 🔄 **Migration Guide**

### Existing Code (No Changes Required)
```python
# Legacy API continues to work unchanged
client = Client(api_key='key', api_kind='eth', network='main')
balance = await client.account.balance('0x...')
```

### New Code (Recommended)
```python
# Use unified client for new development
client = ChainscanClient.from_config('etherscan', 'v1', 'eth', 'main')
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
```

### 📝 **Adding New Scanners**
1. Create scanner class in `aiochainscan/scanners/`
2. Define `SPECS` mapping logical methods to endpoints
3. Register with `@register_scanner` decorator
4. Add to `__init__.py` imports

## 💻 **Development Guidelines**
- Follow **PEP 8** with Black formatting (line length 88)
- Use **type hints everywhere**, including variables (`x: int = 0`)
- Public API objects have **Google-style docstrings** with examples  
- Prefer `async` + `httpx.AsyncClient` for I/O; avoid sync I/O inside async flows
- Log via **structlog** (JSON); forbid bare `print`
- Raise custom exceptions (`class ProviderError(Exception): ...`) instead of generic `Exception`
- When adding functionality, **first** extend tests, **then** implement

## 🧪 **Testing Strategy**
- **Unit Tests**: Each component tested in isolation with mocks
- **Integration Tests**: End-to-end tests with real API calls (limited)
- **Scanner Tests**: Each scanner implementation thoroughly tested
- **Backward Compatibility**: Legacy Client API must remain unchanged

## CI/CD Codecov Fix (2025-01-26)

Fixed Codecov upload issues in CI/CD:
- Updated codecov action to use upload token
- Fixed coverage report generation  
- Verified coverage data collection and submission

Implemented comprehensive configuration management for multiple blockchain scanners:

**Key Features:**
- **Environment Variable Management**: API keys loaded from env vars (ETHERSCAN_KEY, BSCSCAN_KEY, etc.)
- **Multi-Scanner Support**: Unified configuration for 15+ blockchain scanners
- **Network Validation**: Each scanner supports specific networks with validation
- **Secure Key Management**: API keys never committed to git, loaded from environment
- **Backward Compatibility**: Existing Client constructor still works

### 🏗️ New Components:
1. **`aiochainscan/config.py`** ✅
   - `ScannerConfig` dataclass for scanner metadata
   - `ChainScanConfig` class for centralized configuration
   - Support for special scanner configurations (XLayer auth headers, etc.)

2. **Enhanced `Client` class** ✅
   - `Client.from_config(scanner, network)` factory method
   - `Client.get_supported_scanners()` class method
   - `Client.get_scanner_networks(scanner)` class method
   - `Client.list_configurations()` for status overview

3. **🆕 NEW: Unified Scanner Architecture** ✅
   - `ChainscanClient` for cross-scanner logical method calls
   - `Method` enum for type-safe logical operations  
   - `Scanner` plugin system with `EndpointSpec` configurations
   - Automatic parameter mapping and response parsing
   - Support for different authentication modes (query vs header)

4. **Comprehensive Test Suite** ✅
   - `tests/test_config.py` with 20+ test cases
   - `tests/test_unified_client.py` with 22+ test cases for new architecture
   - Environment variable mocking
   - Error handling validation
   - Client integration tests

5. **Example Usage** ✅
   - `examples/setup_config.py` demonstration script
   - `examples/unified_client_demo.py` showcasing new architecture
   - Shows both old and new usage patterns
   - Includes configuration status checking

### 🔧 Supported Scanners & Networks:
- **Ethereum**: main, test, goerli, sepolia (ETHERSCAN_KEY)
- **BSC**: main, test (BSCSCAN_KEY)  
- **Polygon**: main, mumbai, test (POLYGONSCAN_KEY)
- **Optimism**: main, goerli, test (OPTIMISM_KEY)
- **Arbitrum**: main, nova, goerli, test (ARBITRUM_KEY)
- **Fantom**: main, test (FANTOM_KEY)
- **Gnosis**: main, chiado (GNOSIS_KEY)
- **Flare**: main, test (FLARE_KEY - optional)
- **Base**: main, goerli, sepolia (BASE_KEY)
- **XLayer**: main (XLAYER_KEY with special header auth)
- **+6 more scanners** with full network support

### 📝 Usage Examples:
```python
# Legacy way - still works
client = Client(api_key='your_key', api_kind='eth', network='main')
balance = await client.account.balance('0x...')

# New configuration system
client = Client.from_config('eth', 'main')  # Uses ETHERSCAN_KEY env var

# 🆕 NEW: Unified scanner client  
unified_client = ChainscanClient.from_config('etherscan', 'v1', 'eth', 'main')
balance = await unified_client.call(Method.ACCOUNT_BALANCE, address='0x...')

# Same logical call works across different scanners
xlayer_client = ChainscanClient.from_config('oklink', 'v1', 'xlayer', 'main') 
balance = await xlayer_client.call(Method.ACCOUNT_BALANCE, address='0x...')

# Check available scanners and networks
print(ChainscanClient.list_scanner_capabilities())
```

### 🛡️ Security Features:
- API keys never stored in code or config files
- Environment variable validation with clear error messages
- Optional API keys for scanners that support free tiers
- .env files properly excluded from git tracking

### ✅ Testing Status:
- All existing tests continue to pass (backward compatibility maintained)
- New unified architecture tests added and passing (22 tests)
- Environment variable isolation in tests
- Error handling thoroughly tested

This unified scanner architecture provides a robust foundation for managing multiple blockchain scanner APIs while maintaining security, type safety, and ease of use. The system bridges the gap between different API formats while preserving full backward compatibility with existing code.

### 🔄 Recent Updates:
- **API Key Format**: Changed primary format from `{ID}_KEY` to `{SCANNER_NAME}_KEY` 
  - Primary: `ETHERSCAN_KEY` (instead of `ETH_KEY`)
  - Backward compatibility maintained for existing `ETH_KEY` format
  - New `.env` templates use the correct `{SCANNER_NAME}_KEY` format
  - Configuration system automatically prioritizes new format over old format

- **🆕 Unified Scanner Architecture**: Complete implementation of the proposed scanner architecture
  - **Method Enum**: 26 logical operations with type safety
  - **EndpointSpec**: Declarative endpoint configuration with parameter mapping
  - **Scanner Registry**: Plugin system for easy scanner addition
  - **Cross-Scanner Compatibility**: Same method calls work across different APIs
  - **Automatic Parsing**: Response format normalization across scanners

### 📊 Scanner Testing Results (Complete Analysis):

**✅ Working Scanners (2/12):**
- `eth` (Etherscan) - ETH mainnet + sepolia ✅
- `bsc` (BscScan) - BNB mainnet ✅

**🔑 Requiring API Key Setup (9/12):**
- `arbitrum` → Set `ARBISCAN_KEY`
- `base` → Set `BASESCAN_KEY`  
- `blast` → Set `BLASTSCAN_KEY`
- `fantom` → Set `FTMSCAN_KEY`
- `gnosis` → Set `GNOSISSCAN_KEY`
- `linea` → Set `LINEASCAN_KEY`
- `optimism` → Set `OPTIMISM_ETHERSCAN_KEY`
- `polygon` → Set `POLYGONSCAN_KEY`
- `xlayer` → Set `OKLINK_X_LAYER_KEY`

**⚠️ Special Cases (1/12):**