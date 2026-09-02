# aiochainscan - Agent Context Guide

> **Purpose**: Quick context for LLM agents working on this codebase.
> **Version**: 0.6.0 (August 2026)

## What is this project?

Async Python wrapper for blockchain explorer APIs (Etherscan, BlockScout). Unified interface for querying blockchain data with hexagonal architecture and dependency injection. Includes Rust FFI for fast ABI decoding.

---

## Quick Start for Agents

> Public API policy: use `ChainscanClient` only.
> Legacy facade/context/url-builder entrypoints and old pagination-engine docs are removed from agent workflows.

### Primary Interface (USE THIS)
```python
from aiochainscan import ChainscanClient

async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
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
    final  = await client.wait_for_transaction('0xHASH...')       # poll until mined (120s/10s)

    # ── Blocks ───────────────────────────────────────────────
    block     = await client.get_block(12345678)                  # by number
    reward    = await client.get_block_reward(12345678)           # mining reward
    countdown = await client.get_block_countdown(99999999)        # ETA to block
    by_ts     = await client.get_block_by_timestamp(1609459200)   # nearest block
    reached   = await client.wait_for_block(20_000_000)           # poll until reached (600s/10s)

    # ── Contracts ────────────────────────────────────────────
    abi     = await client.get_contract_abi('0x...')              # JSON ABI
    source  = await client.get_contract_source('0x...')           # verified source
    created = await client.get_contract_creation(['0x...'])       # creator + tx
    verdict = await client.wait_for_verification(guid)            # poll Pass/Fail (300s/10s)

    # ── Tokens ───────────────────────────────────────────────
    bal     = await client.get_token_balance('0xWALLET', '0xTOKEN')  # raw units
    supply  = await client.get_token_supply('0xTOKEN')               # total supply
    info    = await client.get_token_info('0xTOKEN')                 # name/symbol/decimals
    holders = await client.get_token_holders('0xTOKEN')              # single page
    all_hld = await client.get_all_token_holders('0xTOKEN')          # ALL (streaming aggregation → list)
    top_hld = await client.get_top_token_holders('0xTOKEN', limit=100)  # top-N by balance
    count   = await client.get_token_holder_count('0xTOKEN')         # int

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
    async for batch in client.iter_token_holders_streaming('0xTOKEN', batch_size=1000):
        process(batch)

    # ── DataFrame export ─────────────────────────────────────
    df = await client.get_transactions_df('0x...')                 # Polars (ALL txs!)
    df = await client.get_token_portfolio_df('0x...')              # Polars

    # ── Self-hosted / custom instances ───────────────────────
    # A URL-shaped `network` targets any BlockScout instance (no API key):
    async with ChainscanClient.from_config(
        'blockscout_v2', 'https://my-blockscout.internal', expected_chain_id=100
    ) as selfhosted:
        info = await selfhosted.get_chain_info()    # ChainInfo (cached 1h)
        ok = await selfhosted.validate_chain(100)   # ChainscanDataError on mismatch
    # Etherscan v2 proxy: api_key still required + expected_chain_id mandatory:
    client = ChainscanClient.from_config(
        'etherscan', 'https://eth-proxy.internal', api_key='...', expected_chain_id=137
    )

    # ── Multi-provider failover pool ─────────────────────────
    from aiochainscan import ChainscanPool

    async with ChainscanPool.from_config(
        [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]  # priority order
    ) as pool:
        balance = await pool.get_balance('0x...')   # full ChainscanClient surface
        pool.last_provider                          # 'etherscan/ethereum' (sticky)

    # ── Value conversion helpers (module-level, float-free) ──
    from aiochainscan import format_ether, hex_to_int, to_iso, to_decimal_amount, wei_to_ether

    ether = wei_to_ether('1500000000000000000')      # Decimal('1.5') — exact, never float
    nice  = format_ether('1500000000000000000')      # '1.500000' (half-up, any magnitude)
    usdc  = to_decimal_amount('1500000', decimals=6) # Decimal('1.5') — any token precision
    n     = hex_to_int('0x1a')                       # 26 — hex str | decimal str | int
    iso   = to_iso('1609459200')                     # '2021-01-01T00:00:00+00:00'
```

> **Custom base URL heuristic:** a `network` string containing `scheme://` is treated
> as a base URL; anything else resolves through the chain registry as before (aliases
> never contain `://` — fully backward compatible). URLs are validated in
> `aiochainscan/base_url.py`: https only (`http` requires `allow_http=True`), no
> credentials/query/`..` segments, trailing slash normalized away. `expected_chain_id`
> is validated once before the first request (Network-layer guard → `ChainscanDataError`);
> `get_chain_info()` probes BlockScout via `POST {base}/api/eth-rpc` `eth_chainId` and
> resolves Etherscan chains through the keyless `GET /v2/chainlist` registry — both
> cached 1h in a process-shared `chain:`-namespaced cache (chainlist downloaded once).
> NodeReal rejects custom base URLs honestly (key rides in the URL path).

> **Polling helpers:** `wait_for_transaction` / `wait_for_verification` / `wait_for_block`
> are pure composition over existing `Method` calls (no new enum values). They poll with
> `asyncio.sleep`, use a loop-clock deadline (`ChainscanWaitTimeoutError(what, waited, last_state)`
> on expiry), return pending-vs-final states (revert / `Fail` verdicts are returned, not raised)
> and require only the methods they build on.

> **Value conversion helpers** (`convert.py`): module-level, stateless, stdlib-only
> utilities for the string scalars every explorer API returns. Wei/token math is
> `Decimal`-exact (`to_decimal_amount` / `wei_to_ether` — integer str/int only,
> fractional base-unit strings are rejected as corrupted data; negatives valid;
> 10^30+ wei exact), `format_ether` renders fixed-precision strings (half-up,
> context precision sized to the value so 10^40 wei does not overflow),
> `hex_to_int` accepts hex `'0x1a'` / decimal `'26'` / int (the proxy-vs-REST
> dual mode; signed hex `-0x10` works; bare `'1a'` is ambiguous → `ValueError`),
> `hex_to_str` decodes data fields (utf-8; `'0x'` → `''`), `to_datetime` /
> `to_iso` convert unix seconds (hex tolerated) to tz-aware UTC datetime /
> ISO-8601. All exported from the package root; enforced by `tests/test_convert.py`.

> **Scanner coverage:** the full surface above is declared by `etherscan` v2.
> `blockscout` v1 inherits the shared Etherscan-like SPECS but not the token
> holders; `blockscout_v2` declares a subset — see the Scanner Support Matrix.
> Convenience methods not declared by the configured scanner raise
> `MethodNotDeclaredError` (a `ValueError` subclass) at call time; the
> Method ↔ mixin ↔ SPECS mapping is enforced by
> `tests/test_method_consistency.py`.

> **Failover pool (`ChainscanPool`, `core/pool.py`):** composes several
> `(scanner, network)` clients for the SAME chain into one client with the full
> `ChainscanClient` surface. Failure classification (`classify_failure` /
> `FailureKind`) splits fallback-eligible errors (rate limit, network/5xx after
> transport retries, missing key — including HTTP 401/403 from the transport
> raise site, e.g. NodeReal's 401 on an invalid path key or a WAF/proxy 403 —
> plan restriction, method-not-declared) from
> fatal ones (arguments, not-found, data contract) — only the former switch
> providers. Sticky routing, per-class cooldowns and pagination pinning: see
> the "Multi-Provider Failover Pool" Semantics list below for the exact numbers.
> Transparency: `last_provider`, `provider=<label>` stamp in progress
> callbacks, `ChainscanProviderSwitchWarning` on switches,
> `ProviderPoolExhaustedError.attempts = [(provider, exception), ...]`.
> The pool never duplicates retries — it reacts only to exceptions that
> survived each member client's tenacity `Network`.

> **Guaranteed-complete pagination (`guarantee_complete`, default `True`):**
> `get_all_*` / `iter_*_streaming` / `iter_transactions` / `iter_logs` accept
> `guarantee_complete`. `True` means *every matching record was returned, or an
> exception was raised*.
>
> - **Overflow detection** is scanner-declared, never guessed:
>   `Scanner.result_window` is the provider's `page * offset` cap
>   (`etherscan` v2 and `blockscout` v1 via `EtherscanLikeScanner`:
>   `API_MAX_OFFSET_ETHERSCAN` = 10_000). `None` means the provider paginates
>   by an opaque server cursor that runs to exhaustion (`blockscout_v2`
>   `next_page_params`, `nodereal` `pageKey`) — nothing to overflow, and the
>   flag is inert. A third-party scanner that has a cap but leaves
>   `result_window = None` cannot be protected.
> - **The signal** is `collected >= result_window`, not an error string and not
>   "the last page was full". A capped explorer answers a partial page that is
>   indistinguishable from the end of the data, and the cap need not land on a
>   page boundary. BlockScout V1's cap is *assumed* equal to Etherscan's: it
>   could not be confirmed from this repo, and over-assuming only costs
>   requests while under-assuming loses data.
> - **Reaching the cap has two flavours** and the error says which. The
>   provider offered a continuation at the cap → records are definitely being
>   cut off (`confirmed=True`). The window came back exactly full with *no*
>   continuation → possibly complete, possibly capped, and the API offers no
>   way to tell (`confirmed=False`, message says "POSSIBLY truncated"). No
>   probe can settle the ambiguous case: it is precisely the case where the
>   provider returned no cursor, and cursors are opaque, so there is nothing
>   to request a further page with.
> - **The split is adaptive**: on overflow the block range is cut at the block
>   of the last record the provider managed to serve (arithmetic bisect only
>   when items carry no block number), and each half is strictly narrower, so
>   the recursion terminates.
> - **Costs.** Up to one extra pass over each overflowing window (the
>   truncated attempt is discarded rather than yielded, so nothing duplicates),
>   a buffer bounded by `result_window` items, and one unnecessary split for a
>   range holding *exactly* the cap.
> - **Two failure types.**
>   `PaginationDataLossError` (`start_block` / `end_block` / `api_limit` /
>   `items_fetched` / `confirmed`) means a real block range was narrowed until
>   a *single block* still exceeded the cap — splitting worked and ran out.
>   `CompletenessUnavailableError` (`method` / `provider` / `alternatives` /
>   `api_limit` / `items_fetched` / `confirmed`) means the endpoint has **no
>   splittable dimension** on this provider, so narrowing cannot apply at all;
>   its message names the providers that *can* serve the method completely,
>   computed from the scanner registry via
>   `scanners.scanners_serving_completely(method)` (a scanner qualifies by
>   declaring the method with `result_window is None`) — nothing is hardcoded.
> - **Visible break: `get_all_token_holders` / `iter_token_holders_streaming`
>   on Etherscan.** A holder list has no block range, so for a token with
>   >=10_000 holders the call now raises `CompletenessUnavailableError`
>   instead of silently returning the first 10_000. The remedy is a provider
>   switch — `blockscout_v2` serves holders natively via
>   `/api/v2/tokens/{addr}/holders` and follows `next_page_params` to
>   exhaustion — or `guarantee_complete=False` to accept truncation
>   deliberately. The error message states both.
> - `guarantee_complete=False` restores the pre-1.0 behaviour (fewer requests
>   on wide ranges, silent truncation possible). `ChainscanPool` forwards the
>   flag to its member clients.

### ⚠️ Key Gotchas
- `get_token_holders()` returns **one page**. Use `get_all_token_holders()` / `iter_token_holders_streaming()` for complete data. (`get_transactions()`/`get_logs()` single-page limits: see Pagination & Retry table below.)
- `get_all_*()` now uses **streaming aggregation** under the hood; for very large datasets prefer `iter_*_streaming()`.
- `get_all_*()` / `iter_*_streaming()` default to `guarantee_complete=True` — complete data or an exception, never silent truncation (see below).
- A **bounded** block range (`from_block > 0` / concrete `to_block`) on a provider whose spec declares no block-range params (e.g. BlockScout V2 transactions) raises `BlockRangeNotSupportedError` at every seam — single-page `get_*`, `call()`, `fetch_page()`, streams — instead of silently dropping the bounds; unbounded calls behave exactly as before.
- `get_transactions_df()` auto-paginates (uses `iter_transactions` internally).
- Balance/value/supply values are **Wei strings** — convert with `wei_to_ether()` / `to_decimal_amount()` (exact `Decimal`), never `int(wei) / 10**18` float division.

> **Note:** Legacy `Client` class and `modules/` were removed in v0.3.0 (see also the public API policy above).

---

## Multi-Agent Workflow (Worktrees & Scripts)

**One session == one worktree == one branch.** Never switch branches or stash to share a directory with another agent session — parallel sessions on one checkout cause `.git/index.lock` collisions and lost work. Setup mirrors `lombard-data-analytics`.

```bash
make wt-new SLUG=my-task                 # .claude/worktrees/my-task on branch feat/my-task
                                         # copies .env, runs uv sync --extra dev --frozen
make wt-ls                               # list worktrees + merge status (dry-run)
make wt-rm SLUG=my-task ARGS="--yes"     # teardown — refuses dirty or unmerged worktrees
```

Branch types: `feat | fix | chore | docs | arch | refactor` (2nd arg, default `feat`); base ref (3rd arg, default `origin/main`). Env knobs: `AIO_SKIP_SYNC=1`, `AIO_BUILD_FASTABI=1`.

### Agent script toolkit (`scripts/agent/`)

| Script | Purpose |
|--------|---------|
| `new-worktree.sh` | Bootstrap an isolated session worktree |
| `rm-worktree.sh` | Safe teardown — removes only clean + merged worktrees, squash-merge aware, integration branches protected |
| `preflight.sh` | Run BEFORE starting: env, deps, imports, test collection, fastabi status |
| `validate_fast.sh` | The DONE gate — ruff, format, import-lint, mypy --strict, full pytest |
| `safe_commit.sh` | `git add` + commit with index.lock retry (worktree-aware; use `make commit`) |
| `ci_watch.sh` | Bounded GH Actions poller; exit status is the verdict |
| `ruff_format_hook.py` | PostToolUse hook — auto-formats edited `*.py` |

### ⚠️ GitHub Actions temporarily DISABLED (Actions-minutes budget)

CI/CD, Test Installation and Build and Publish Wheels are `disabled_manually`. **Do not wait on CI — it will never run.** Use the local mirror instead:

```bash
make ci-local        # lint + format-check + import-lint + mypy --strict + pytest
```

Re-enable when the budget allows: `gh workflow enable ci.yml test-install.yml wheels.yml --repo VaitaR/aiochainscan`.

---

## Complete Method Reference

Every `Method` enum value (33 total) maps to typed convenience methods on `ChainscanClient`:

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
| `TOKEN_HOLDERS` | `get_token_holders(contract_address, page, offset)` / `get_all_token_holders(contract_address)` | `list[dict]` (`{'address', 'value'}`) |
| `TOKEN_TOP_HOLDERS` | `get_top_token_holders(contract_address, limit)` | `list[dict]` (Etherscan PRO only) |
| `TOKEN_HOLDER_COUNT` | `get_token_holder_count(contract_address)` | `int` |
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
│  core/client.py (ChainscanClient) | core/pool.py (Pool)      │
│  domain/contract.py                                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    SCANNER LAYER                             │
│  scanners/base.py | etherscan_v2.py | blockscout_v2.py      │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   AGGREGATION SERVICES                       │
│  pagination.py | analytics.py | ens_resolver.py              │
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
| Report a rangeless capped endpoint as a whale block | Raise `CompletenessUnavailableError` naming a provider that can serve it | Holder lists have no range to split - "could not split" misdescribes it and offers no remedy |
| Call complete data "lost" when the window came back exactly full | Say *possibly* truncated (`confirmed=False`) | A false error on correct data is not loud, it is wrong |
| Trust a partial page to mean "end of data" | Treat `>= Scanner.result_window` records as overflow | A capped page/offset API truncates with a partial page and no error |
| Split a range in fixed-width windows | Bisect on the *observed* overflow boundary | Fixed windows cost requests where data is sparse and still truncate where it is dense |

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
| `core/client.py` + `core/mixins/` | **ChainscanClient** (composition of per-domain mixins) | All API interactions, one convenience method per `Method` value plus `get_all_*`/`iter_*`/`wait_for_*`; constructed via `ScannerTarget` (`from_config` / `chain=`-`provider=` kwargs; the positional field form is gone) |
| `core/streaming.py` | **Streaming surface declaration** | `STREAMING_SPECS` registry (Method, params builder, operation noun, flags) + the ONE shared stream implementation; pool forwards and the test sweeps derive from it |
| `core/pool.py` | **ChainscanPool** | Multi-provider failover: `classify_failure` (lookup of the exception's `failure_kind`, regex fallback), sticky routing, cooldowns, pinned pagination |
| `domain/method.py` | **Method** enum (33 values) | Supported operations |
| `domain/contract.py` | **SmartContract** | High-level contract API |
| `domain/models.py` | **Address`, **TxHash** | Data validation, EIP-55 |
| `config.py` | **ConfigurationManager** | Credential/env resolution only (topology lives in `chain_registry.py`) |

### Services (Business Logic)
| File | Purpose | Key Pattern |
|------|---------|-------------|
| `services/pagination.py` | Pagination | `iter_pages`/`iter_items`/`collect_all` over `Scanner.fetch_page` cursors; the guarantee machinery lives in `services/pagination_guarantee.py` (adaptive range splitting, re-exported here) |
| `services/ens_resolver.py` | ENS name resolution | Cache + BlockScout V2 |
| `services/analytics.py` | Polars DataFrames | Column-oriented, Utf8 for Wei |
| `services/constants.py` | Shared service constants | - |

### Infrastructure
| File | Purpose | Key Pattern |
|------|---------|-------------|
| `network.py` | HTTP transport | ALL HTTP must go through here |
| `adapters/memory_cache.py` | In-memory LRU | O(1) ops, asyncio.Lock |
| `adapters/aiolimiter_adapter.py` | Rate limiting | Token bucket, burst=1 |
| `convert.py` | Wei/hex/datetime conversion helpers | Exact `Decimal` math, hex-aware int parsing, tz-aware UTC |
| `crypto.py` | Keccak-256, EIP-55 checksum | fastabi → eth-utils → pure-Python (`_keccak.py`) fallback chain — the base install always has a working backend |
| `decode.py` | ABI decoding (Python) | Wraps Rust FFI, orjson parsing |
| `fastabi/src/lib.rs` | ABI decoding (Rust) | Returns JSON, LRU cache |
| `mcp/` | MCP server for AI agents | Adapter over `ChainscanClient` — see MCP Server section |

---

## Scanner Support Matrix

| Scanner | Version | Free? | Key Env Var | Method coverage |
|---------|---------|-------|-------------|-----------------|
| BlockScout | v1 | ✅ Yes | - | Etherscan-like surface minus token holders (its Etherscan-compat layer answers "Unknown action" for the token module holder actions); `TX_BY_HASH`/`PROXY_*` served via the instance's `/api/eth-rpc` JSON-RPC (see below) |
| BlockScout | **v2** | ✅ Yes | - | Cursor-paginated (no result window → the only provider that can guarantee a complete `TOKEN_HOLDERS` list). Subset: `ACCOUNT_BALANCE`, `ACCOUNT_TRANSACTIONS`, `ACCOUNT_TOKEN_PORTFOLIO`, `CONTRACT_ABI`, `BLOCK_BY_NUMBER`, `TOKEN_HOLDERS` (native `/api/v2/tokens/{addr}/holders`), `TOKEN_HOLDER_COUNT` (token info `holders_count`) |
| Etherscan | v2 | ❌ No | `ETHERSCAN_KEY` | Full Etherscan-like surface + token holders (`tokenholderlist`/`topholders`/`tokenholdercount` are PRO endpoints) — all 33 `Method` values |
| NodeReal | v1 | Free tier | `NODEREAL_KEY` | BSC-only subset (22 `Method` values) incl. the only `CONTRACT_ABI`/`CONTRACT_SOURCE`/`ACCOUNT_INTERNAL_TXS` alternative for keyless-free BSC analytics |

> **Token holders notes:** the unified item shape is `{'address': EIP-55 str, 'value': str}`
> (raw-unit quantity — never Int64). `TOKEN_TOP_HOLDERS` is Etherscan-only: BlockScout V2's
> holders endpoint does not guarantee top-ordering, and NodeReal has no token-holders API
> (`nr_getTokenHoldings` is *address* holdings) — both raise honest `ValueError`.

### NodeReal (MegaNode / BSCTrace backend) — BSC analytics

`nodereal` v1 talks JSON-RPC 2.0 to `https://bsc-{mainnet,testnet}.nodereal.io/v1/{key}`
(NodeReal's `nr_*` Enhanced API — the engine behind https://bsctrace.com) plus the
BscScan-compatible verified-contract REST on `open-platform.nodereal.io`. Networks:
`bsc` / `bnb` / `binance` (mainnet) and `bsc-testnet`.

- Declares 22 of the 33 `Method` values; honest `ValueError` for contract
  verify, gas oracle/estimate, price/supply stats, block reward/countdown.
- `nr_getTransactionByAddress` serves ≤1000 blocks per request and **silently
  returns empty pages for wider ranges** — `fetch_page` therefore walks the
  requested range in 1000-block windows, so `get_all_*` / `iter_*_streaming`
  see complete history. An unbounded end block resolves the chain tip once.
- Holdings methods (`nr_getTokenHoldings`, `nr_getNFTHoldings`) page at 100
  items with hex `totalCount` cursors.
- JSON-RPC `-32005` (usage limit) is translated to `ChainscanRateLimitError`
  so the transport retry policy applies.

### BlockScout v1 proxy fallback (`/api/eth-rpc`)

BlockScout's Etherscan-compat REST answers `"Unknown module"` for
`module=proxy`, so `blockscout` v1 routes `TX_BY_HASH`, `PROXY_ETH_CALL` and
`PROXY_GET_BALANCE` through the instance's JSON-RPC endpoint
(`POST {base_url}/api/eth-rpc`) — the same keyless transport the chain-info
probe uses. The Network layer unwraps the JSON-RPC envelope and raises
`ChainscanClientProxyError` for reverts; a `null` result (unknown tx) comes
back as `None`. Verified live against `eth.blockscout.com`.

---

## MCP Server (`aiochainscan/mcp/`)

Agent adapter over `ChainscanClient` — **run**: `python -m aiochainscan.mcp_server`
(requires `mcp` extra). Structure:

| File | Purpose |
|------|---------|
| `mcp/envelope.py` | `ToolResponse{data, notes, instructions, pagination, content_text}` + truncation (`{value_sample, value_truncated}`, 512 chars) + `format_units` (lossless int math) |
| `mcp/cursors.py` | Opaque Base64URL cursors wrapping `fetch_page` scanner cursors (`InvalidCursorError` with "start over" advice) |
| `mcp/abi_codec.py` | Pure-Python ABI encode (calldata) / decode (eth_call outputs) — covers what fastabi doesn't (it decodes *inputs* only). Cross-checked against `eth_abi` in tests |
| `mcp/tools.py` | 12 tools as plain `client -> ToolResponse` functions (**no mcp import** — offline-testable) + `ClientPool` (one client per `(scanner, chain)`, connection pooling across calls) |
| `mcp/server.py` | FastMCP wiring: envelope → `CallToolResult` (text + structuredContent), tool registration |
| `mcp_server.py` | Entry point (historical import path preserved) |

**Tools**: `get_wallet_balance`, `get_address_overview`, `get_transactions`,
`get_transaction_info` (fastabi-decoded input via auto-ABI),
`get_token_portfolio`, `get_token_info`, `get_token_holders`,
`get_top_token_holders`, `get_contract_abi` (signature summary),
`read_contract` (auto-ABI + eth_call, outputs decoded), `resolve_ens`,
`list_chains`.

**Contract rules**:
- Curation caps: ≤50 items/page (`clamp_page_size`), curated field sets per tool.
- Pagination = one `client.fetch_page` call per response; `next_call.params`
  carries the new cursor — agents never parse cursors.
- Unsupported scanner methods → envelope `notes` (with scanner hints), never a
  crash; primary-call failures still raise (clean MCP error).
- Default scanner `blockscout` (keyless, v1); override per call (`scanner=`)
  or via `AIOCHAINSCAN_MCP_SCANNER`.
- Tests: `tests/test_mcp_server.py` (offline stubs; FastMCP registration
  tests need `uv run --extra mcp pytest`), `tests/test_blockscout_v1_ethrpc.py`.

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

# Self-hosted BlockScout: same lifecycle, URL instead of a chain alias
async with ChainscanClient.from_config('blockscout_v2', 'https://my-blockscout.internal') as client:
    await client.get_balance('0x...')  # no API key needed, chain_id unknown until probed

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
all_holders = await client.get_all_token_holders(token_contract)
```

### Progress Callbacks
```python
from aiochainscan.utils.progress_helpers import console_progress

txs = await client.get_all_transactions(
    address,
    on_progress=console_progress(),  # Real-time feedback
)
```

### Multi-Provider Failover Pool
```python
from aiochainscan import ChainscanPool

# Priority order: etherscan preferred, blockscout rescues. Providers serve the
# SAME chain; kwargs (timeout, proxy, rate_limiter, ...) forward to every member.
async with ChainscanPool.from_config(
    [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]
) as pool:
    await pool.get_balance('0x...')          # routed with failover
    async for batch in pool.iter_transactions_streaming('0x...'):
        ...                                   # pinned to ONE provider per call

    pool.last_provider                       # who answered last (sticky)
    pool.provider_states()                   # {label: available/cooldown/...}
    pool.reset_cooldowns()                   # operational escape hatch
```

Semantics:
- **Sticky**: last successful provider keeps serving (no yo-yo when a
  higher-priority provider leaves cooldown).
- **Cooldown**: rate limit → `max(retry_after, 30s)`; transient → 10s;
  auth → 600s; plan restriction → 3600s (all constructor-tunable). Cooling
  providers are skipped without an HTTP attempt; after expiry they get one
  half-open trial (failure re-enters cooldown).
- **Pagination pinning**: `get_all_*` / `iter_*` / `iter_*_streaming` bind to
  one provider per call; only a first-page failure may restart on the next
  provider (cursor state is still empty then). Mid-pagination errors
  propagate but still cool the provider.
- **from_config** excludes unconstructible providers with a warning (missing
  key etc.); raises only when NO provider could be built.
- All state is per-pool-instance — nothing global.

### Error Handling
```python
from aiochainscan.exceptions import (
    ChainscanRateLimitError,      # Retry with backoff
    ChainscanNetworkError,        # Retry (connection issues)
    PaginationDataLossError,      # Whale block: a single block over the API's cap
    CompletenessUnavailableError, # Endpoint has no splittable dimension here (.alternatives)
    ChainscanDataError,           # Data contract violation
    MethodNotDeclaredError,       # ValueError subclass: method not in SPECS
    BlockRangeNotSupportedError,  # MethodNotDeclaredError subclass: bounded block range the provider's spec cannot carry (raised at every seam: call/fetch_page/stream)
    ProviderPoolExhaustedError,   # Pool: every provider failed (.attempts)
    ChainscanProviderSwitchWarning,  # Pool: routed away from a provider
)
```

---

## Testing

```bash
# Run all tests (1000+ tests)
pytest tests/ -q

# Type checking (strict)
mypy aiochainscan --strict

# Linting + auto-fix
ruff check . --fix
ruff format .
```

Or in one shot: `make ci-local` (mirrors the disabled GitHub CI). Agents: run `make validate` before claiming DONE and `make commit MSG="..." PATHS="..."` to commit.

---

## Rust FFI Notes (fastabi/)

- **Build**: NOT automatic. Since the distribution split the base package builds with hatchling, so `uv sync --extra dev` installs no Rust extension — build it explicitly with `cd aiochainscan/fastabi && uv run --with maturin maturin develop --release`, or pass `AIO_BUILD_FASTABI=1` to `make wt-new`. Without it `tests/test_crypto.py` skips 12 tests and `decode()` uses the Python fallback; `scripts/agent/preflight.sh` reports which module (if any) is live.
- **Cache**: LRU with 1000 entries max (~50MB)
- **GIL**: Released during computation AND serialization
- **Return format**: JSON string → parsed by orjson in Python; `keccak256` returns bytes
- **Key invariant**: Never return PyDict/PyList directly (blocks GIL)
- **Imports**: canonical module name is top-level `aiochainscan_fastabi` (published as the
  separate `aiochainscan-fastabi` distribution — `aiochainscan[fastabi]` extra). Every
  import site tries the new top-level name first and falls back to the legacy
  `aiochainscan.aiochainscan_fastabi` name, so an existing maturin/editable checkout
  built under the old layout keeps working.
- **Arrow**: `decode_many_to_arrow` / zero-copy Polars export is behind the off-by-default
  `arrow` cargo feature (benchmarked as a small win next to network time — see
  `docs/V1_PLAN.md` Track A). `decode.py:ARROW_AVAILABLE` reflects whether the loaded
  extension was built with it; build with
  `cd aiochainscan/fastabi && maturin develop --release --features arrow` to enable it.

---

## Environment Setup

```bash
uv sync --extra dev        # deps only — the Rust extension is a separate package now
uv run pytest tests/ -q    # run tests
export ETHERSCAN_KEY="your_key"  # Optional
```

Required runtime deps are just: `httpx`, `orjson`, `tenacity`, `aiolimiter`.
Everything else is an extra (`data`, `mcp`, `http2`, `fallback`).

---

## Pre-Commit Validation (MANDATORY)

**Run BEFORE `git commit` — not after:**
```bash
pytest tests/ -q                    # Verify all 1000+ tests pass
mypy aiochainscan --strict          # Type safety check (69 source files)
pre-commit run --all-files          # All linters (ruff, format, etc.)
```
Only proceed to `git commit` when ALL three checks pass. Do NOT rely on post-commit hook to catch errors.

**Code Quality:**
- Follow hexagonal architecture — never bypass Network layer
- All Wei values as strings, all addresses as EIP-55 checksum
- Add `# noqa: CODE` pragmas only when error is unavoidable (document why)
