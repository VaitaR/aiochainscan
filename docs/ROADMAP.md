# aiochainscan Roadmap & Feature Plan

This document outlines the planned improvements and new features for the aiochainscan library, organized by priority and complexity.

---

## 📋 Table of Contents

1. [Version 0.3.0 Changes (Completed)](#version-030-changes-completed)
2. [Version 0.4.0 - Modern Stack Migration](#version-040---modern-stack-migration)
3. [Critical Fixes (Completed)](#critical-fixes-completed)
4. [Short-term Improvements](#short-term-improvements)
5. [Medium-term Features](#medium-term-features)
6. [Long-term Vision](#long-term-vision)
7. [Architecture Improvements](#architecture-improvements)
8. [Developer Experience](#developer-experience)

---

## ✅ Version 0.3.0 Changes (Completed)

Major refactoring completed in v0.3.0:

### Legacy Code Removal
- [x] **Removed Legacy Client** - `aiochainscan/client.py` deleted
- [x] **Removed Legacy Modules** - `aiochainscan/modules/` directory deleted
- [x] **Removed Unused Scanners** - Moralis and RoutScan scanners removed
- [x] **Cleaned Imports** - Updated `__init__.py` exports

### Modern Rate Limiting (aiolimiter)
- [x] **AioLimiterAdapter** - New Token Bucket algorithm implementation
  - Replaced `asyncio-throttle` with `aiolimiter>=1.1.0`
  - Key isolation for multi-tenant support
  - Thread-safe lazy initialization

### Expanded API Methods
- [x] **ACCOUNT_TOKEN_PORTFOLIO** - Get all ERC20 tokens for address
- [x] **ACCOUNT_NFT_PORTFOLIO** - Get all NFTs for address
- [x] **CONTRACT_VERIFY** - Submit source code for verification
- [x] **CONTRACT_VERIFY_STATUS** - Check verification status

### Blockscout REST API V2
- [x] **BlockScoutV2Scanner** - Native V2 API support
  - Path-based parameters (RESTful)
  - No API key required
  - Modern JSON responses
  - 11 networks supported

---

## ✅ Version 0.4.0 - Modern Stack Migration (Completed)

Major dependency upgrade to modern Python Web3 stack (2024-2025 best practices).

### 1. JSON Parsing & Data Validation (orjson + Pydantic V2)
**Status:** ⚠️ PARTIAL — orjson shipped and remains; the Pydantic DTO layer was
**later removed** (`domain/dto_v2.py` no longer exists, `pydantic` is not a
dependency). Typed responses are planned, not implemented — responses are
plain `dict`s; use `aiochainscan.convert` helpers for exact value typing.

- [x] Added `orjson>=3.10.0` to dependencies *(still current)*
- [~] Created `domain/dto_v2.py` with Pydantic models for all API responses — **removed in a later refactor (planned-not-implemented)**
- [~] Exported V2 DTOs: `TransactionDTOv2`, `InternalTransactionDTOv2`, `TokenTransferDTOv2`, `LogEventDTOv2`, `BlockDTOv2` — **removed with the DTO layer**

### 2. Retry Mechanism (tenacity)
**Status:** ✅ COMPLETE

- [x] Added `tenacity>=8.2.0` to dependencies
- [x] Created `adapters/tenacity_retry.py` implementing `RetryPolicy` port
- [x] `TenacityRetryAdapter` handles both HTTP errors and business-logic rate limits
- [x] Removed `aiohttp-retry` dependency

### 3. HTTP Client (httpx with HTTP/2)
**Status:** ✅ COMPLETE

- [x] Added `httpx[http2]>=0.27.0` to dependencies
- [x] Created `adapters/httpx_client.py` implementing `HttpClient` port
- [x] Updated `network.py` to use httpx instead of aiohttp
- [x] Updated `ChainscanClient` to use new httpx-based Network
- [x] Removed `aiohttp` and `requests` from core dependencies

### 4. Rate Limiting (aiolimiter)
**Status:** ✅ COMPLETE (done in v0.3.0, integrated in v0.4.0)

- [x] `AioLimiterAdapter` provides Token Bucket algorithm
- [x] Integrated with new `Network` class

### Migration Summary

**pyproject.toml dependencies (v0.4.0):**
```toml
dependencies = [
    "httpx[http2]>=0.27.0",    # Modern HTTP/2 client
    "aiolimiter>=1.1.0",       # Token Bucket rate limiter
    "tenacity>=8.2.0",         # Smart retries
    "pydantic>=2.7.0",         # Data validation & DTOs — later REMOVED
    "orjson>=3.10.0",          # Fast JSON parsing
    "eth-abi",
    "eth-utils>=2.0.0",        # Keccak & utilities
    "structlog>=23.1.0",
]
```

**Removed dependencies:**
- `aiohttp` → replaced by `httpx`
- `aiohttp-retry` → replaced by `tenacity`
- `requests` → `httpx` can do sync too
- `asyncio-throttle` → replaced by `aiolimiter`

**New public exports:**
- `HttpxClientAdapter` - Modern HTTP/2 client
- `TenacityRetryAdapter` - Transport-agnostic retry mechanism
- `TransactionDTOv2`, `InternalTransactionDTOv2`, `TokenTransferDTOv2`, `LogEventDTOv2`, `BlockDTOv2` - Pydantic V2 DTOs *(later removed — planned-not-implemented)*

**Removed example files:**
- `examples/routscan_demo.py` - RoutScan scanner was removed
- `examples/test_moralis_demo.py` - Moralis scanner was removed
- `examples/test_moralis_integration.py` - Moralis scanner was removed

---

## ✅ Version 0.4.1 - Complete API Coverage (Completed)

Full convenience method coverage and data integrity improvements.

### 1. Complete Method Coverage (30+ Convenience Methods)
**Status:** ✅ COMPLETE

- [x] Added typed convenience methods for ALL 28 Method enum values
- [x] `get_erc721_transfers()`, `get_erc1155_transfers()` - ERC-721/1155 transfer queries
- [x] `get_nft_portfolio()` - NFT holdings for address
- [x] `check_transaction_status()` - Execution status (isError field)
- [x] `get_contract_creation()` - Creator address + deployment tx
- [x] `get_token_supply()` - Total supply for token contract
- [x] `get_gas_estimate()` - ETA in seconds for gas price
- [x] `get_eth_supply()` - Total ETH supply
- [x] `eth_call()`, `eth_get_balance()` - JSON-RPC proxy methods
- [x] `get_block_countdown()`, `get_block_by_timestamp()` - Block query methods

### 2. Streaming Results API
**Status:** ✅ COMPLETE

- [x] `iter_transactions_streaming()` - Memory-efficient transaction streaming (~10MB RAM)
- [x] `iter_internal_transactions_streaming()` - Internal tx streaming
- [x] `iter_token_transfers_streaming()` - ERC-20 transfer streaming
- [x] `iter_logs_streaming()` - Event log streaming
- [x] Backpressure via `batch_size` parameter
- [x] `streaming_decoder.py` - AsyncIterator + `asyncio.to_thread` for non-blocking decode

### 3. Data Integrity Fixes
**Status:** ✅ COMPLETE

- [x] Fixed `get_transactions_df()` — was returning single page, now auto-paginates via `iter_transactions()`
- [x] Added whale block warning in `services/logs.py` — logs warning when potential data loss detected
- [x] 38 new tests in `test_client_convenience.py` (587+ total tests passing)
- [x] 100% mypy --strict compliance (80 source files)

---

## ✅ Critical Fixes (Completed)

These critical issues have been addressed in the recent audit:

### Security
- [x] **Path Traversal Vulnerability (CWE-22)** - Fixed in `modules/extra/utils.py`
  - Added address validation with regex `^0x[a-fA-F0-9]{40}$`
  - Added chain ID sanitization
  - Using `pathlib.Path` for safe path construction

- [x] **Global Mutable State** - Fixed in `config.py`
  - `get_scanner_config()` now returns deep copies
  - Prevents API key leakage between tenants

### Performance
- [x] **HTTP Session Lifecycle** - Fixed in `scanners/base.py` and `core/client.py`
  - Session reuse via dependency injection
  - Connection pooling now works correctly
  - 10-50x performance improvement for bulk operations

- [x] **Memory Leak in Cache** - Fixed in `adapters/memory_cache.py`
  - LRU eviction strategy with configurable `max_size`
  - Prevents unbounded memory growth

### Reliability
- [x] **Hidden Rate Limit Detection** - Fixed in `network.py`
  - New `ChainscanRateLimitError` exception
  - Detects HTTP 200 responses with rate limit messages

- [x] **Pagination Data Loss Warning** - Added in `services/paging_engine.py`
  - Critical logging when "whale problem" detected
  - Telemetry event for monitoring

---

## 🔥 Short-term Improvements (1-2 weeks)

### 1. Code Quality & Cleanup

#### 1.1 Eliminate getattr Hacks in base.py
**Priority:** HIGH | **Effort:** 3 days

```python
# Current (fragile)
api_kind_any = getattr(client, 'api_kind', None) or \
    getattr(getattr(client, '_url_builder', object()), '_api_kind', None)

# Target (clean)
class ClientContext(Protocol):
    @property
    def api_kind(self) -> str: ...
    @property
    def network(self) -> str: ...
    @property
    def api_key(self) -> str: ...
```

**Tasks:**
- [ ] Define `ClientContext` protocol in `ports/`
- [ ] Implement protocol in both `Client` and `ChainscanClient`
- [ ] Replace all `getattr` cascades with protocol access
- [ ] Update tests

#### 1.2 Extract Constants
**Priority:** MEDIUM | **Effort:** 1 day

- [x] Create `constants.py` module (`services/constants.py` exists)
- [ ] Move magic numbers:
  - `DEFAULT_TX_OFFSET = 10_000`
  - `DEFAULT_LOGS_OFFSET = 1_000`
  - `DEFAULT_MAX_CONCURRENT = 8`
  - `GATEWAY_ERROR_CODES = {502, 503, 504, 520, 524}`
- [ ] Update all usages

#### 1.3 Remove Dead Code
**Priority:** LOW | **Effort:** 1 day

- [ ] Audit `_use_graphql` flag (always `False`)
- [ ] Remove unused commented code in examples
- [ ] Clean up non-English comments

### 2. Retry Policy Enhancement

#### 2.1 Smart Rate Limit Retry
**Priority:** HIGH | **Effort:** 2 days

```python
class AdaptiveRetryPolicy:
    """Retry policy that handles both HTTP errors and logical rate limits."""

    def should_retry(self, error: Exception) -> bool:
        if isinstance(error, ChainscanRateLimitError):
            return True  # Always retry rate limits
        # ... existing logic

    def get_delay(self, attempt: int, error: Exception) -> float:
        if isinstance(error, ChainscanRateLimitError):
            return min(2 ** attempt, 60)  # Exponential up to 60s
        return self.base_delay * (2 ** attempt)
```

**Tasks:**
- [ ] Update `ExponentialBackoffRetry` to handle `ChainscanRateLimitError`
- [ ] Add configurable max delay for rate limits
- [ ] Add telemetry for rate limit retries

---

## 🚀 Medium-term Features (1-2 months)

### 3. New Data Fetching Capabilities

#### 3.1 Block Range Chunking for Whale Addresses
**Priority:** HIGH | **Effort:** 1 week

Address the "whale problem" where single blocks have >10k transactions.

```python
async def fetch_with_topic_splitting(
    address: str,
    *,
    topics: list[str] | None = None,
    chunk_by_topic: bool = True,
) -> list[dict]:
    """Split large result sets by event topic for parallel fetching."""
```

**Tasks:**
- [ ] Implement topic-based pagination fallback
- [ ] Add transaction index pagination where supported
- [ ] Create parallel fetch strategy for whale blocks

#### 3.2 Streaming Results API
**Status:** ✅ COMPLETE (v0.4.1)

Implemented in `services/paging_streaming.py`, `services/streaming_decoder.py`, and exposed via `ChainscanClient`:

```python
# Process 1M+ transactions with ~10MB RAM
async for batch in client.iter_transactions_streaming(address, batch_size=1000):
    await database.bulk_insert(batch)
```

**Completed:**
- [x] `AsyncIterator` interface for transactions, internal txs, token transfers, logs
- [x] Backpressure via configurable `batch_size`
- [x] Memory-efficient streaming decoder with `asyncio.to_thread`
- [x] Non-blocking JSON decode in thread pool

#### 3.3 Multi-Address Batch Queries
**Priority:** MEDIUM | **Effort:** 3 days

```python
async def get_balances_multi(
    addresses: list[str],
    *,
    concurrent: int = 10,
) -> dict[str, int]:
    """Fetch balances for multiple addresses efficiently."""
```

**Tasks:**
- [ ] Add batch balance endpoint support
- [ ] Implement concurrent single-address fallback
- [ ] Add progress callback for large batches

### 4. Enhanced Caching

#### 4.1 Finality-Aware Caching
**Priority:** MEDIUM | **Effort:** 3 days

```python
class FinalityAwareCache:
    """Cache that respects blockchain finality depth."""

    SAFE_DEPTH = 32  # Blocks considered finalized

    async def set(self, key: str, value: Any, *, block_number: int | None = None):
        if block_number and self._is_finalized(block_number):
            ttl = 86400  # 24h for finalized data
        else:
            ttl = 5  # 5s for pending/recent
```

**Tasks:**
- [ ] Track current block number
- [ ] Implement finality depth checking
- [ ] Skip caching for `latest`/`pending` tags

#### 4.2 Redis Cache Adapter
**Priority:** LOW | **Effort:** 2 days

- [ ] Implement `RedisCacheAdapter` in `adapters/`
- [ ] Support for distributed deployments
- [ ] Connection pooling

### 5. GraphQL Support Expansion

#### 5.1 Full BlockScout GraphQL
**Priority:** MEDIUM | **Effort:** 1 week

Currently only partial GraphQL support. Expand to cover:
- [ ] Full transaction history
- [ ] Token transfers
- [ ] Contract interactions
- [ ] Block details

---

## 🎯 Long-term Vision (3-6 months)

### 6. New Scanner Integrations

> **Note:** In v0.3.0, we removed Moralis and RoutScan scanners to focus on
> core Etherscan and Blockscout support. Future scanner additions will follow
> the same clean architecture established with these core providers.

#### 6.1 Alchemy API
**Priority:** HIGH | **Effort:** 2 weeks

```python
client = ChainscanClient.from_config('alchemy', 'ethereum')
```

**Features:**
- [ ] Enhanced metadata
- [ ] NFT API support
- [ ] Webhook subscriptions
- [ ] Transaction simulation

#### 6.2 Infura API
**Priority:** MEDIUM | **Effort:** 1 week

- [ ] JSON-RPC support
- [ ] IPFS integration

### 7. Advanced Features

#### 7.1 Real-time Event Subscriptions
**Priority:** HIGH | **Effort:** 3 weeks

```python
async with client.subscribe_events(address, topics) as events:
    async for event in events:
        process(event)
```

**Tasks:**
- [ ] WebSocket adapter
- [ ] Event filtering
- [ ] Reconnection handling
- [ ] Backfill support

#### 7.2 Transaction Simulation
**Priority:** MEDIUM | **Effort:** 2 weeks

```python
result = await client.simulate_transaction(
    from_address='0x...',
    to_address='0x...',
    data='0x...',
    value=0,
)
```

#### 7.3 Gas Estimation & Prediction
**Priority:** MEDIUM | **Effort:** 1 week

```python
estimate = await client.estimate_gas(
    transaction_type='eip1559',
    priority='fast',  # 'slow', 'medium', 'fast'
)
```

---

## 🏗 Architecture Improvements

### 8. Refactoring

#### 8.1 Scanner Registry
**Priority:** HIGH | **Effort:** 1 week

Partially implemented — `register_scanner()` decorator exists in `scanners/__init__.py`:

```python
@register_scanner
class EtherscanV2(Scanner):
    ...
```

**Completed:**
- [x] Create `ScannerRegistry` class (via `register_scanner` decorator)
- [x] Scanner self-registration decorator

**Remaining:**
- [ ] Move network mappings to scanner classes
- [ ] Remove hardcoded dicts from `core/client.py`

#### 8.2 Service Layer Consolidation
**Priority:** MEDIUM | **Effort:** 1 week

Consolidate duplicated pagination logic:

**Current structure (redundant):**
```
services/
├── unified_fetch.py      # High-level fetch_all
├── paging_engine.py      # Generic pagination
├── account.py            # Account-specific fetch
└── ...
```

**Target structure:**
```
services/
├── fetch.py              # Unified fetch API
├── pagination/
│   ├── engine.py         # Core pagination
│   ├── strategies.py     # Sliding, Paged, etc.
│   └── deduplication.py  # Result processing
└── transformers/
    └── sorting.py        # Common sorting utils
```

#### 8.3 Extract Utils.fetch_all_elements_optimized
**Priority:** HIGH | **Effort:** 3 days

Current 150-line monolithic function should become:

```python
class OptimizedFetcher:
    def __init__(self, scheduler: BlockRangeScheduler, workers: int):
        self.scheduler = scheduler
        self.workers = workers

    async def fetch(self, address: str) -> list[dict]:
        ranges = self.scheduler.generate_ranges()
        results = await self._parallel_fetch(ranges)
        return self._deduplicate_and_sort(results)
```

---

## 👨‍💻 Developer Experience

### 9. Documentation

#### 9.1 API Reference
**Priority:** HIGH | **Effort:** 1 week

- [ ] Generate API docs with Sphinx/MkDocs
- [ ] Add docstrings to all public methods
- [ ] Include code examples

#### 9.2 Migration Guide
**Priority:** MEDIUM | **Effort:** 2 days

- [ ] Legacy `Client` → `ChainscanClient` migration
- [ ] Breaking changes documentation
- [ ] Deprecation timeline

### 10. CLI Enhancements

#### 10.1 Interactive Mode
**Priority:** LOW | **Effort:** 3 days

```bash
$ aiochainscan shell
>>> balance 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045
1234.56 ETH
>>> transactions 0x... --limit 10
```

#### 10.2 Output Formats
**Priority:** LOW | **Effort:** 2 days

- [ ] JSON output (`--format json`)
- [ ] CSV export (`--format csv`)
- [ ] Table output (`--format table`)

### 11. Testing

#### 11.1 Integration Test Suite
**Priority:** HIGH | **Effort:** 1 week

- [ ] VCR-style request recording
- [ ] Mock server for offline testing
- [ ] Performance benchmarks

#### 11.2 Type Coverage
**Priority:** MEDIUM | **Effort:** 3 days

- [x] Achieve 100% mypy --strict compliance (80 source files pass)
- [ ] Add runtime type checking option
- [ ] Protocol validation tests

---

## 📊 Priority Matrix

| Feature | Impact | Effort | Priority | Status |
|---------|--------|--------|----------|--------|
| Scanner Registry | High | Medium | P0 | ⚡ Partial |
| Rate Limit Retry | High | Low | P0 | ❌ TODO |
| ClientContext Protocol | High | Low | P0 | ❌ TODO |
| Complete Method Coverage | High | Medium | P0 | ✅ Done (v0.4.1) |
| Streaming API | Medium | Medium | P1 | ✅ Done (v0.4.1) |
| mypy --strict 100% | Medium | Low | P1 | ✅ Done (v0.4.1) |
| GraphQL Expansion | Medium | High | P1 | ❌ TODO |
| Real-time Subscriptions | High | High | P2 | ❌ TODO |
| Redis Cache | Low | Low | P2 | ❌ TODO |
| CLI Enhancements | Low | Medium | P3 | ❌ TODO |

---

## 🗓 Release Plan

### v0.3.0 (Released)
- ✅ Legacy code removal (Client, modules/, Moralis, RoutScan)
- ✅ Modern rate limiting (aiolimiter)
- ✅ Expanded API methods (token/NFT portfolio, contract verify)
- ✅ Blockscout REST API V2

### v0.4.0 (Released)
- ✅ httpx with HTTP/2 (replaced aiohttp)
- ✅ tenacity retry (replaced aiohttp-retry)
- ✅ orjson + Pydantic V2 DTOs *(DTO layer later removed — see §1 above)*
- ✅ All critical security/performance fixes

### v0.4.1 (Released)
- ✅ Complete method coverage (30+ convenience methods)
- ✅ Streaming API (iter_transactions_streaming, etc.)
- ✅ DataFrame export fix (auto-pagination)
- ✅ 100% mypy --strict (80 files)
- ✅ 587+ tests passing

### v0.5.0 (Released)
- Rate limit retry enhancement
- ClientContext Protocol
- Scanner Registry completion
- Documentation updates

### v0.6.0 (Current — competitive-backlog feature set)
- ✅ Polling helpers: `wait_for_transaction` / `wait_for_verification` /
  `wait_for_block` (+ `ChainscanWaitTimeoutError`)
- ✅ Token holders: `TOKEN_HOLDERS` / `TOKEN_TOP_HOLDERS` /
  `TOKEN_HOLDER_COUNT` (33 `Method` values total; Etherscan v2 PRO +
  Blockscout v2 native)
- ✅ Custom base URLs for self-hosted instances (`expected_chain_id`,
  `allow_http`, `get_chain_info()`, `validate_chain()`)
- ✅ MCP server revamp (`aiochainscan/mcp/`): response envelope, opaque
  cursors with `next_call`, 12 read-only curated tools
- ✅ Multi-provider failover pool (`ChainscanPool`): sticky routing,
  cooldowns, capability routing, pinned pagination
- ✅ Value conversion helpers (`aiochainscan/convert.py`, exported at root)
- ✅ NodeReal scanner (BSC) and Blockscout v1 JSON-RPC proxy fallback
- GraphQL expansion, finality-aware caching and multi-address batch queries
  remain open (moved to the medium/long-term sections above)
- 1000+ tests passing, mypy --strict clean

### v1.0.0
- Real-time subscriptions
- Full API documentation
- Stable public API

---

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to help with these features.

Priority labels:
- **P0**: Critical path, needed for stability
- **P1**: Important for usability
- **P2**: Nice to have
- **P3**: Future consideration
