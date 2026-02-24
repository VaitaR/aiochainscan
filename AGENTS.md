# aiochainscan - Agent Context Guide

> **Purpose**: Quick context for LLM agents working on this codebase.
> **Version**: 0.4.1 (February 2026)

## What is this project?

Async Python wrapper for blockchain explorer APIs (Etherscan, BlockScout). Unified interface for querying blockchain data with hexagonal architecture and dependency injection. Includes Rust FFI for fast ABI decoding.

---

## Quick Start for Agents

### Primary Interface (USE THIS)
```python
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

# Create client (BlockScout V2 - no API key needed)
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

# Make API calls
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address='0x...')
portfolio = await client.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address='0x...')

# High-level SmartContract API (NEW in v0.4.1)
contract = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")
async for event in contract.iter_events("Transfer", limit=1000):
    print(event.args['from'], event.args['to'], event.args['value'])

# ENS resolution (NEW in v0.4.1)
address = await client.resolve_name("vitalik.eth")
name = await client.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")

# Streaming for large datasets (NEW in v0.4.1) - constant ~10MB RAM
async for batch in client.iter_transactions_streaming(address, batch_size=1000):
    process(batch)

# Always close when done
await client.close()
```

> **Note:** Legacy `Client` class and `modules/` were removed in v0.3.0.
> Facade functions (`get_balance`, etc.) are **DEPRECATED** in v0.4.0 - use `ChainscanClient`.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      FACADE LAYER                            │
│  core/client.py (ChainscanClient) | domain/contract.py      │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    SCANNER LAYER                             │
│  scanners/base.py | etherscan_v2.py | blockscout_v2.py      │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    SERVICE LAYER                             │
│  paging_engine.py | streaming_decoder.py | chunked_fetcher  │
│  ens_resolver.py | unified_fetch.py | analytics.py          │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                     PORTS (Interfaces)                       │
│  http.py | cache.py | telemetry.py | progress.py            │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    ADAPTERS (Implementations)                │
│  aiohttp_client.py | memory_cache.py | aiolimiter_adapter   │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    RUST FFI (fastabi/)                       │
│  decode.py (Python) ←→ lib.rs (Rust + orjson serialization) │
└─────────────────────────────────────────────────────────────┘
```

**Dependency rule**: Only downward. Never upward. Never bypass Network layer.

---

## ⚠️ CRITICAL WARNINGS (Read Before Coding)

### Data Integrity
| ❌ DON'T | ✅ DO | Why |
|----------|-------|-----|
| Use `pl.Int64` for Wei | Use `pl.Utf8` (String) | Int64 overflows at 9.22 ETH! |
| Use raw pointers as cache keys | Use content hash (xxhash) | Python reuses memory addresses |
| Store addresses lowercase | Use `to_checksum_address()` | EIP-55 checksum matters for comparisons |

### Async Performance
| ❌ DON'T | ✅ DO | Why |
|----------|-------|-----|
| Use `requests.get()` | Use `await http_client.get()` | Blocks event loop for 5+ seconds |
| Create httpx/aiohttp sessions in scanners | Use `Network.request()` | Bypasses connection pooling/retry |
| Build PyDict in Rust loops | Return JSON, parse with orjson | GIL blocks event loop during object creation |
| O(N) scan in cache `set()` | Lazy TTL check in `get()` only | 100k items = seconds of freeze |

### Pagination & Retry
| ❌ DON'T | ✅ DO | Why |
|----------|-------|-----|
| Wrap async generator with `@retry` | Apply retry inside generator at page-fetch level | Tenacity completes when generator is created, not exhausted |
| Reset adaptive offset per page | Persist offset state across all pages | "Yo-yo effect" doubles API requests |
| Skip whale blocks silently | Raise `PaginationDataLossError` | Silent data loss is unacceptable |

### Network
| ❌ DON'T | ✅ DO | Why |
|----------|-------|-----|
| Use HTTP/2 with burst requests | Set `max_burst=1` or use HTTP/1.1 | Cloudflare WAF sends GOAWAY, not 429 |
| Retry only `TimeoutException` | Include `NetworkError`, `RemoteProtocolError` | Connection resets are common |

---

## Key Files to Know

### Core (Source of Truth)
| File | Purpose | Source of Truth For |
|------|---------|---------------------|
| `core/client.py` | **ChainscanClient** | All API interactions |
| `core/method.py` | **Method** enum | Supported operations |
| `domain/contract.py` | **SmartContract** | High-level contract API |
| `domain/models.py` | **Address**, **TxHash** | Data validation, EIP-55 |
| `config.py` | **ConfigurationManager** | Scanner configs (lazy-loaded) |

### Services (Business Logic)
| File | Purpose | Key Pattern |
|------|---------|-------------|
| `services/paging_engine.py` | Pagination | Sliding window, dedup, fail-fast |
| `services/streaming_decoder.py` | Memory-efficient decoding | AsyncIterator + `asyncio.to_thread` |
| `services/chunked_fetcher.py` | Block range splitting | Prevents DB timeouts |
| `services/ens_resolver.py` | ENS name resolution | Cache + BlockScout V2 |
| `services/analytics.py` | Polars DataFrames | Column-oriented, Utf8 for Wei |

### Infrastructure
| File | Purpose | Key Pattern |
|------|---------|-------------|
| `network.py` | HTTP transport | ALL HTTP must go through here |
| `adapters/memory_cache.py` | In-memory LRU | O(1) ops, asyncio.Lock |
| `adapters/aiolimiter_adapter.py` | Rate limiting | Token bucket, burst=1 |
| `decode.py` | ABI decoding (Python) | Wraps Rust FFI, orjson parsing |
| `fastabi/src/lib.rs` | ABI decoding (Rust) | Returns JSON, LRU cache |

---

## Scanner Support Matrix

| Scanner | Version | Free? | Key Env Var |
|---------|---------|-------|-------------|
| BlockScout | v1, **v2** | ✅ Yes | - |
| Etherscan | v2 | ❌ No | `ETHERSCAN_KEY` |

---

## Common Tasks

### Adding a New Scanner
1. Create `scanners/newscan_v1.py`
2. Inherit from `Scanner` base class
3. Define `SPECS` dict mapping `Method` → `EndpointSpec`
4. **Use `self._network_client.request()`** - never create own HTTP session
5. Register in `scanners/__init__.py`

### Adding Bulk Fetch Support
1. Use `paging_engine.fetch_all_generic()` with `FetchSpec`
2. For streaming: use `paging_streaming.fetch_all_generic_streaming()`
3. Always pass `on_progress` callback through to engine

### Modifying HTTP Behavior
- Rate limiting: `adapters/aiolimiter_adapter.py` (burst=1 for APIs)
- Retry logic: `network.py` - includes NetworkError, RemoteProtocolError
- JSON parsing: Always use `orjson.loads(response.content)` not `response.json()`

---

## Important Patterns

### Session Lifecycle
```python
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
try:
    # All calls reuse same HTTP session (connection pooling)
    await client.call(Method.ACCOUNT_BALANCE, address='0x...')
finally:
    await client.close()
```

### Streaming for Large Datasets
```python
# Process 1M+ transactions with ~10MB RAM
async for batch in client.iter_transactions_streaming(address, batch_size=1000):
    # Each batch decoded in thread pool (non-blocking)
    await database.bulk_insert(batch)
```

### Progress Callbacks
```python
from aiochainscan.utils.progress_helpers import console_progress

txs = await fetch_all_transactions_fast(
    ...,
    on_progress=console_progress()  # Real-time feedback
)
```

### Error Handling
```python
from aiochainscan.exceptions import (
    ChainscanRateLimitError,      # Retry with backoff
    ChainscanNetworkError,        # Retry (connection issues)
    PaginationDataLossError,      # Whale block - manual handling needed
    ChainscanDataError,           # Data contract violation
)
```

---

## Testing

```bash
# Run all tests (549+ tests)
pytest tests/ -q

# Type checking (strict)
mypy aiochainscan --strict

# Linting + auto-fix
ruff check . --fix
ruff format .
```

---

## Rust FFI Notes (fastabi/)

- **Build**: `cd aiochainscan/fastabi && maturin develop --release`
- **Cache**: LRU with 1000 entries max (~50MB)
- **GIL**: Released during computation AND serialization
- **Return format**: JSON string → parsed by orjson in Python
- **Key invariant**: Never return PyDict/PyList directly (blocks GIL)

---

## Environment Setup

```bash
pip install -e ".[dev]"
export ETHERSCAN_KEY="your_key"  # Optional
```

---

## Contact / Contributing

**Pre-Commit Validation (MANDATORY - run before git commit):**
```bash
pytest tests/ -q                    # Verify all 549 tests pass
mypy aiochainscan --strict          # Type safety check (80 files)
pre-commit run --all-files          # All linters (ruff, format, etc.)
```
Only proceed to `git commit` when ALL checks pass. Do NOT rely on post-commit hook to catch errors.

**Code Quality:**
- Follow hexagonal architecture - never bypass Network layer
- All Wei values as strings, all addresses as EIP-55 checksum
- Add `# noqa: CODE` pragmas only when error is unavoidable (document why)
