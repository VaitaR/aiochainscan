# aiochainscan - Agent Context Guide

> **Purpose**: Quick context for LLM agents working on this codebase.
> **Version**: 0.4.0

## What is this project?

Async Python wrapper for blockchain explorer APIs (Etherscan, BlockScout). Unified interface for querying blockchain data with hexagonal architecture and dependency injection.

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

# Always close when done
await client.close()
```

> **Note:** Legacy `Client` class and `modules/` were removed in v0.3.0.
> See [docs/MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md) for migration help.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      FACADE LAYER                            │
│  core/client.py (ChainscanClient) | __init__.py (get_*)     │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    SCANNER LAYER                             │
│  scanners/base.py | etherscan_v2.py | blockscout_v1.py      │
│                   | blockscout_v2.py (NEW)                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    SERVICE LAYER                             │
│  services/account.py | paging_engine.py | unified_fetch.py  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                     PORTS (Interfaces)                       │
│  ports/http.py | ports/cache.py | ports/telemetry.py        │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    ADAPTERS (Implementations)                │
│  adapters/aiohttp_client.py | memory_cache.py               │
│  adapters/aiolimiter_adapter.py (Token Bucket rate limit)   │
│          | simple_rate_limiter.py | retry_exponential.py    │
└─────────────────────────────────────────────────────────────┘
```

**Dependency rule**: Only downward. Never upward.

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `core/client.py` | **ChainscanClient** - primary unified interface |
| `core/method.py` | **Method** enum - all supported API operations |
| `scanners/base.py` | **Scanner** base class - implement for new providers |
| `scanners/blockscout_v2.py` | **BlockScoutV2Scanner** - modern REST API V2 |
| `adapters/aiolimiter_adapter.py` | **AioLimiterAdapter** - Token Bucket rate limiting |
| `network.py` | HTTP client with throttling, retry, session management |
| `exceptions.py` | All custom exceptions (`ChainscanRateLimitError`, etc.) |
| `config.py` | Configuration management, scanner configs |
| `services/paging_engine.py` | Pagination logic for bulk fetching |

---

## Scanner Support Matrix

| Scanner | Version | Free? | Key Env Var |
|---------|---------|-------|-------------|
| BlockScout | v1, **v2** | ✅ Yes | - |
| Etherscan | v2 | ❌ No | `ETHERSCAN_KEY` |

> **Removed in v0.3.0:** Moralis, RoutScan scanners

---

## Common Tasks

### Adding a New Scanner
1. Create `scanners/newscan_v1.py`
2. Inherit from `Scanner` base class
3. Define `SPECS` dict mapping `Method` → `EndpointSpec`
4. Register in `scanners/__init__.py`

### Adding a New Method
1. Add to `Method` enum in `core/method.py`
2. Add `EndpointSpec` in relevant scanner's `SPECS` dict

### Modifying HTTP Behavior
- Rate limiting: `adapters/simple_rate_limiter.py`
- Retry logic: `adapters/retry_exponential.py`
- Session management: `network.py`

---

## Important Patterns

### Session Lifecycle
```python
# ChainscanClient owns the Network session
# Scanner receives it via dependency injection
# Session is reused across all calls (connection pooling)

client = ChainscanClient.from_config('blockscout', 'ethereum')
try:
    # All calls reuse same HTTP session
    await client.call(Method.ACCOUNT_BALANCE, address='0x...')
    await client.call(Method.ACCOUNT_TRANSACTIONS, address='0x...')
finally:
    await client.close()  # Closes session
```

### Error Handling
```python
from aiochainscan.exceptions import (
    ChainscanRateLimitError,  # Rate limit hit (retry with backoff)
    ChainscanClientApiError,   # API returned error
    ChainscanClientProxyError, # JSON-RPC error
)

try:
    result = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
except ChainscanRateLimitError:
    # Wait and retry
except ChainscanClientApiError as e:
    # Check e.message, e.result
```

### Pagination
```python
from aiochainscan.services.unified_fetch import fetch_all

# Fetch all transactions with automatic pagination
txs = await fetch_all(
    data_type='transactions',
    address='0x...',
    api_kind='eth',
    network='main',
    api_key='KEY',
    strategy='fast',  # or 'safe'
)
```

---

## Testing

```bash
# Run all tests
pytest tests/ -q

# Run specific test file
pytest tests/test_client.py -v

# Run with coverage
pytest --cov=aiochainscan tests/

# Type checking
mypy aiochainscan --ignore-missing-imports

# Linting
ruff check .
ruff format .
```

---

## Known Issues / Tech Debt

See [docs/ROADMAP.md](docs/ROADMAP.md) for full list. Key items:

1. **DRY violations in `unified_fetch.py`** - Duplicate page fetcher closures
2. **`fetch_all_elements_optimized` in `utils.py`** - 150-line SRP violation
3. **Hardcoded scanner mappings** - Need scanner registry pattern

---

## Quick Reference: Method Enum

```python
class Method(Enum):
    # Account
    ACCOUNT_BALANCE = "account_balance"
    ACCOUNT_BALANCE_MULTI = "account_balance_multi"
    ACCOUNT_TRANSACTIONS = "account_transactions"
    ACCOUNT_INTERNAL_TRANSACTIONS = "account_internal_transactions"

    # Tokens
    TOKEN_BALANCE = "token_balance"
    TOKEN_TRANSFERS = "token_transfers"
    ACCOUNT_TOKEN_PORTFOLIO = "account_token_portfolio"    # NEW in v0.3
    ACCOUNT_NFT_PORTFOLIO = "account_nft_portfolio"        # NEW in v0.3

    # Contract
    CONTRACT_ABI = "contract_abi"
    CONTRACT_SOURCE = "contract_source"
    CONTRACT_VERIFY = "contract_verify"                    # NEW in v0.3
    CONTRACT_VERIFY_STATUS = "contract_verify_status"      # NEW in v0.3

    # Block
    BLOCK_BY_NUMBER = "block_by_number"
    BLOCK_COUNTDOWN = "block_countdown"

    # Logs
    EVENT_LOGS = "event_logs"

    # Gas
    GAS_ORACLE = "gas_oracle"

    # Stats
    ETH_SUPPLY = "eth_supply"
    ETH_PRICE = "eth_price"
```

---

## Environment Setup

```bash
# Install dependencies
pip install -e ".[dev]"

# Set API keys (optional)
export ETHERSCAN_KEY="your_key"
```

---

## Contact / Contributing

- See `CONTRIBUTING.md` for guidelines
- Run `ruff check . && pytest tests/` before PRs
- Follow hexagonal architecture patterns
