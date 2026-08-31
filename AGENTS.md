# aiochainscan - Agent Context Guide

> **Purpose**: Quick context for LLM agents working on this codebase.
> **Version**: 0.4.1 (February 2026)

## What is this project?

Async Python wrapper for blockchain explorer APIs (Etherscan, BlockScout). Unified interface for querying blockchain data with hexagonal architecture and dependency injection. Includes Rust FFI for fast ABI decoding.

---

## Quick Start for Agents

> Public API policy: use `ChainscanClient` only.
> Legacy facade/context/url-builder entrypoints and old pagination-engine docs are removed from agent workflows.

### Primary Interface (USE THIS)
```python
from aiochainscan import ChainscanClient

async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
    # ── Account ──────────────────────────────────────────────
    balance = await client.get_balance('0x...')                   # Wei string
    txs     = await client.get_transactions('0x...')              # single page
    all_txs = await client.get_all_transactions('0x...')          # ALL (streaming aggregation → list)
    itxs    = await client.get_internal_transactions('0x...')     # single page
    erc20   = await client.get_token_transfers('0x...')           # single page
    erc721  = await client.get_erc721_transfers('0x...')          # single page
    erc1155 = await client.get_erc1155_transfers('0x...')         # single page
    tokens  = await client.get_token_portfolio('0x...')           # ERC-20 holdings
    nfts    = await client.get_nft_portfolio('0x...')             # NFT holdings

    # ── Transactions ─────────────────────────────────────────
    tx     = await client.get_transaction('0xHASH...')            # by hash
    status = await client.get_transaction_status('0xHASH...')     # receipt status
    check  = await client.check_transaction_status('0xHASH...')   # execution status

    # ── Blocks ───────────────────────────────────────────────
    block     = await client.get_block(12345678)                  # by number
    reward    = await client.get_block_reward(12345678)           # mining reward
    countdown = await client.get_block_countdown(99999999)        # ETA to block
    by_ts     = await client.get_block_by_timestamp(1609459200)   # nearest block

    # ── Contracts ────────────────────────────────────────────
    abi     = await client.get_contract_abi('0x...')              # JSON ABI
    source  = await client.get_contract_source('0x...')           # verified source
    created = await client.get_contract_creation(['0x...'])       # creator + tx

    # ── Tokens ───────────────────────────────────────────────
    bal     = await client.get_token_balance('0xWALLET', '0xTOKEN')  # raw units
    supply  = await client.get_token_supply('0xTOKEN')               # total supply
    info    = await client.get_token_info('0xTOKEN')                 # name/symbol/decimals

    # ── Gas & Stats ──────────────────────────────────────────
    price   = await client.get_eth_price()                        # USD/BTC
    gas     = await client.get_gas_oracle()                       # safe/propose/fast
    est     = await client.get_gas_estimate(2_000_000_000)        # ETA in seconds
    eth_sup = await client.get_eth_supply()                       # total ETH supply

    # ── Event Logs ───────────────────────────────────────────
    logs     = await client.get_logs('0x...', from_block=0)       # single page (≤1000)
    all_logs = await client.get_all_logs('0x...', from_block=0)   # ALL (streaming aggregation → list)

    # ── Proxy / JSON-RPC ─────────────────────────────────────
    result  = await client.eth_call('0xTO', '0xDATA')             # eth_call
    bal_hex = await client.eth_get_balance('0x...')                # hex Wei

    # ── High-level APIs ──────────────────────────────────────
    contract = await client.get_contract('0x...')                  # SmartContract
    async for event in contract.iter_events("Transfer", limit=100):
        print(event.args['from'], event.args['to'], event.args['value'])

    name    = await client.lookup_address('0x...')                 # ENS reverse
    address = await client.resolve_name('vitalik.eth')             # ENS forward

    # ── Streaming (large datasets, constant ~10MB RAM) ───────
    async for batch in client.iter_transactions_streaming('0x...', batch_size=1000):
        process(batch)

    # ── DataFrame export ─────────────────────────────────────
    df = await client.get_transactions_df('0x...')                 # Polars (ALL txs!)
    df = await client.get_token_portfolio_df('0x...')              # Polars
```

### ⚠️ Key Gotchas
- `get_transactions()` returns **one page** (~50-100 items). Use `get_all_transactions()` for complete data.
- `get_logs()` returns **≤1000 logs**. Use `get_all_logs()` for complete data.
- `get_all_*()` now uses **streaming aggregation** under the hood; for very large datasets prefer `iter_*_streaming()`.
- `get_transactions_df()` auto-paginates (uses `iter_transactions` internally).
- Balance/value/supply values are **Wei strings** — divide by `10**18` for ETH.

> **Note:** Legacy `Client` class and `modules/` were removed in v0.3.0.
> Legacy facade/context/url-builder public entrypoints and old pagination-engine usage were purged in modern API docs.

---

## Complete Method Reference

Every `Method` enum value (28 total) maps to typed convenience methods on `ChainscanClient`:

| Method Enum | Convenience Method(s) | Returns |
|---|---|---|
| `ACCOUNT_BALANCE` | `get_balance(address)` | `str` (Wei) |
| `ACCOUNT_TRANSACTIONS` | `get_transactions(address)` / `get_all_transactions(address)` | `list[dict]` |
| `ACCOUNT_INTERNAL_TXS` | `get_internal_transactions(address)` / `get_all_internal_transactions(address)` | `list[dict]` |
| `ACCOUNT_ERC20_TRANSFERS` | `get_token_transfers(address)` / `get_all_token_transfers(address)` | `list[dict]` |
| `ACCOUNT_ERC721_TRANSFERS` | `get_erc721_transfers(address)` | `list[dict]` |
| `ACCOUNT_ERC1155_TRANSFERS` | `get_erc1155_transfers(address)` | `list[dict]` |
| `ACCOUNT_TOKEN_PORTFOLIO` | `get_token_portfolio(address)` | `list[dict]` |
| `ACCOUNT_NFT_PORTFOLIO` | `get_nft_portfolio(address)` | `list[dict]` |
| `TX_BY_HASH` | `get_transaction(tx_hash)` | `dict` |
| `TX_RECEIPT_STATUS` | `get_transaction_status(tx_hash)` | `dict` |
| `TX_STATUS_CHECK` | `check_transaction_status(tx_hash)` | `dict` |
| `BLOCK_BY_NUMBER` | `get_block(block_number)` | `dict` |
| `BLOCK_REWARD` | `get_block_reward(block_number)` | `dict` |
| `BLOCK_COUNTDOWN` | `get_block_countdown(target_block)` | `dict` |
| `BLOCK_NUMBER_BY_TIMESTAMP` | `get_block_by_timestamp(timestamp, closest)` | `dict` |
| `CONTRACT_ABI` | `get_contract_abi(address)` | `str` (JSON) |
| `CONTRACT_SOURCE` | `get_contract_source(address)` | `dict` |
| `CONTRACT_CREATION` | `get_contract_creation(addresses)` | `list[dict]` |
| `CONTRACT_VERIFY` | `client.call(Method.CONTRACT_VERIFY, ...)` | *(multi-step workflow)* |
| `CONTRACT_VERIFY_STATUS` | `client.call(Method.CONTRACT_VERIFY_STATUS, ...)` | *(multi-step workflow)* |
| `TOKEN_BALANCE` | `get_token_balance(address, contract_address)` | `str` |
| `TOKEN_SUPPLY` | `get_token_supply(contract_address)` | `str` |
| `TOKEN_INFO` | `get_token_info(contract_address)` | `dict` |
| `GAS_ESTIMATE` | `get_gas_estimate(gas_price)` | `str` |
| `GAS_ORACLE` | `get_gas_oracle()` | `dict` |
| `EVENT_LOGS` | `get_logs(address, ...)` / `get_all_logs(address, ...)` | `list[dict]` |
| `ETH_SUPPLY` | `get_eth_supply()` | `str` |
| `ETH_PRICE` | `get_eth_price()` | `dict` |
| `PROXY_ETH_CALL` | `eth_call(to, data, tag)` | `str` |
| `PROXY_GET_BALANCE` | `eth_get_balance(address, tag)` | `str` |

### Paginated (get_all_*) vs Single-Page Methods

| Pattern | Use When | Memory |
|---|---|---|
| `get_transactions(address)` | Quick look, small wallets | Low |
| `get_all_transactions(address)` | Need ALL data (built via streaming aggregation) | Grows with data |
| `iter_transactions_streaming(address)` | Large wallets (1M+ txs) | Constant ~10MB |
| `get_transactions_df(address)` | Data analysis (Polars) | Grows with data |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT / DOMAIN LAYER                     │
│  core/client.py (ChainscanClient) | domain/contract.py       │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    SCANNER LAYER                             │
│  scanners/base.py | etherscan_v2.py | blockscout_v2.py      │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   AGGREGATION SERVICES                       │
│  account.py | logs.py | streaming_decoder.py | analytics.py  │
│  ens_resolver.py | chunked_fetcher.py                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                     PORTS (Interfaces)                       │
│  cache.py | progress.py | rate_limiter.py                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    ADAPTERS (Implementations)                │
│  memory_cache.py | aiolimiter_adapter | tenacity_retry      │
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
| Use `get_transactions()` for all data | Use `get_all_transactions()` or `iter_transactions_streaming()` | Single page returns ~50-100 items only! |
| Use `get_logs()` for complete data | Use `get_all_logs()` or `iter_logs_streaming()` | Single page capped at ~1000 logs! |
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
| `core/client.py` | **ChainscanClient** (~1800 lines) | All API interactions, 30+ convenience methods |
| `core/method.py` | **Method** enum (28 values) | Supported operations |
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
| `services/logs.py` | Event log fetching | Whale block warning, sliding window |

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
1. Extend `ChainscanClient` methods and scanner `SPECS` first
2. Keep `get_all_*` behavior as materialized results from streaming aggregation
3. Add/maintain matching `iter_*_streaming` path for large datasets
4. Always thread `on_progress` callbacks through public client methods

### Modifying HTTP Behavior
- Rate limiting: `adapters/aiolimiter_adapter.py` (burst=1 for APIs)
- Retry logic: `network.py` - includes NetworkError, RemoteProtocolError
- JSON parsing: Always use `orjson.loads(response.content)` not `response.json()`

---

## Important Patterns

### Session Lifecycle
```python
# Option 1: async context manager (preferred)
async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
    await client.get_balance('0x...')

# Option 2: manual close
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
try:
    await client.get_balance('0x...')
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

### Get ALL Data (Paginated)
```python
# These use streaming aggregation internally and return materialized lists:
all_txs = await client.get_all_transactions(address)
all_logs = await client.get_all_logs(address, from_block=0, topic0='0xddf252...')
all_transfers = await client.get_all_token_transfers(address)
all_internal = await client.get_all_internal_transactions(address)
```

### Progress Callbacks
```python
from aiochainscan.utils.progress_helpers import console_progress

txs = await client.get_all_transactions(
    address,
    on_progress=console_progress(),  # Real-time feedback
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
# Run all tests (587+ tests)
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

## Pre-Commit Validation (MANDATORY)

**Run BEFORE `git commit` — not after:**
```bash
pytest tests/ -q                    # Verify all 587+ tests pass
mypy aiochainscan --strict          # Type safety check (80 files)
pre-commit run --all-files          # All linters (ruff, format, etc.)
```
Only proceed to `git commit` when ALL three checks pass. Do NOT rely on post-commit hook to catch errors.

**Code Quality:**
- Follow hexagonal architecture — never bypass Network layer
- All Wei values as strings, all addresses as EIP-55 checksum
- Add `# noqa: CODE` pragmas only when error is unavoidable (document why)
