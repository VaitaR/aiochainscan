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
> `blockscout` v1 inherits the shared Etherscan-like SPECS and adds the holder
> list; `blockscout_v2` and `nodereal` declare subsets — see the Scanner
> Support Matrix.
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
>   `Scanner.RESULT_WINDOW_OVERRIDES` declares a **per-method** window where one
>   endpoint is bounded tighter than the rest, and `result_window_for(method)` is
>   what the pagination binding reads.
> - **The signal** is `collected >= result_window`, not an error string and not
>   "the last page was full". A capped explorer answers a partial page that is
>   indistinguishable from the end of the data, and the cap need not land on a
>   page boundary.
> - **BlockScout V1's caps are live-verified** (2026-09-02, `eth.blockscout.com`),
>   no longer assumed. Account endpoints: `page * offset <= 10_000` exactly —
>   `page=11&offset=1000` and `page=2&offset=10000` both answer `status=0`
>   "Result window is too large, PageNo x Offset size must be less than or equal
>   to 10000", while an over-cap `offset=10001` is silently clamped to 10_000
>   items. `logs/getLogs` is different and **ignores page/offset entirely**,
>   answering at most 1000 logs with `status=1` "OK" — so its window is
>   `API_MAX_OFFSET_LOGS` = 1000 (declared in `RESULT_WINDOW_OVERRIDES`), and
>   `EtherscanLikeScanner.fetch_page` issues no cursor for a spec that maps
>   neither `page` nor `offset`, because "the next page" there is the first page
>   again.
> - **Etherscan v2's caps are live-verified too** (2026-09-02, key-authenticated).
>   `page * offset <= 10_000` is enforced with an error, but the per-page size is
>   a separate, *silent* limit: `offset=5000` or `offset=10000` answers **1000**
>   items with `status=1` "OK". A short page like that reads as end-of-data, so
>   `batch_size=5000` returned 1000 of 2009 transactions — silent loss under the
>   default `guarantee_complete=True`, because 1000 never reaches the 10_000
>   window. `Scanner.max_page_size` declares what a provider actually serves
>   (Etherscan 1000, BlockScout V1 10_000, both measured) and `fetch_page`
>   clamps `offset` to it, so the page-full test compares against a number the
>   provider agreed to. Cross-check: Etherscan and BlockScout V1 now return
>   byte-identical counts for the same range (1085 logs, 2009 txs).
>   Etherscan's docs are **silent** on both caps, so measurement is the only
>   source — and the 1000-per-page figure is a *dated* change (Etherscan cut it
>   from 10_000 to 1000 in July 2026). Treat `max_page_size` as a measured
>   constant with a shelf life: re-measure it with `make probe-caps`
>   (`scripts/agent/probe_provider_caps.py` — asks each provider for pages
>   straddling its declared caps and exits non-zero on drift), do not reason
>   about it. Last run 2026-09-02: Etherscan v2 and BlockScout V1 both
>   reproduced their declarations for `ACCOUNT_TRANSACTIONS` and `EVENT_LOGS`
>   (Etherscan serves 1000 per page and refuses `page*offset` at 11_000;
>   BlockScout V1 serves 10_000 per page, refuses at 20_000, and answers
>   `getLogs` page 2 with page 1's first record — the paging-ignored cap
>   `RESULT_WINDOW_OVERRIDES` declares). BlockScout V2 and NodeReal are
>   cursor-paginated and declare no cap, so the probe reports "nothing to
>   verify" for them rather than firing requests whose answer could not move a
>   declaration; a declared cap the probe cannot exercise counts as unverified,
>   never as a pass.
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
>   declaring the method with `result_window_for(method) is None`) — nothing is
>   hardcoded. The question is asked **per method, not per scanner**: BlockScout
>   V1 caps its account endpoints at 10_000 and still serves the holder list to
>   exhaustion, so reading the scanner-wide window alone would hide it from the
>   remedy this function computes.
> - **Visible break: `get_all_token_holders` / `iter_token_holders_streaming`
>   on Etherscan.** A holder list has no block range, so for a token with
>   >=10_000 holders the call now raises `CompletenessUnavailableError`
>   instead of silently returning the first 10_000. The remedy is a provider
>   switch — `blockscout/v1`, `blockscout/v2` and `nodereal/v1` all serve the
>   holder list to exhaustion, and the error names whichever of them the
>   registry finds — or `guarantee_complete=False` to accept truncation
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
| `probe_provider_caps.py` | Re-measures declared pagination caps live (`make probe-caps`); exit 1 on drift or on a provider left unconfirmed for want of a key |
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
| `TOKEN_TOP_HOLDERS` | `get_top_token_holders(contract_address, limit)` | `list[dict]` (Etherscan PRO + NodeReal `topN`; `limit` ≤ 1000 on Etherscan, clamped to 100 on NodeReal) |
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
| Assume the provider honoured the `offset` you sent | Clamp it to `Scanner.max_page_size` before comparing | Etherscan serves 1000 for `offset=5000` with `status=1` — the "partial" page is a full one |
| Give every endpoint the scanner's one `result_window` | Declare the tighter ones in `RESULT_WINDOW_OVERRIDES` | BlockScout V1 `getLogs` caps at 1000 and ignores paging; walking to 10_000 re-fetches page 1 ten times |
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
| `decode.py` | ABI decoding (Python) | Backend chain fastabi → `abi_pure.py` (no third tier); orjson parsing; content+identity-cached ABI index |
| `abi_pure.py` | Pure-Python ABI codec | The always-available decode floor AND the MCP calldata encoder — no dependencies beyond `crypto.py` |
| `fastabi/src/lib.rs` | ABI decoding (Rust) | Returns JSON, LRU cache |
| `mcp/` | MCP server for AI agents | Adapter over `ChainscanClient` — see MCP Server section |

---

## Scanner Support Matrix

| Scanner | Version | Free? | Key Env Var | Method coverage |
|---------|---------|-------|-------------|-----------------|
| BlockScout | v1 | ✅ Yes | - | Etherscan-like surface **plus** `TOKEN_HOLDERS` (its own action name `token/getTokenHolders`, not Etherscan's `tokenholderlist`); `TX_BY_HASH`/`PROXY_*` served via the instance's `/api/eth-rpc` JSON-RPC (see below) |
| BlockScout | **v2** | ✅ Yes | - | Cursor-paginated (no result window). Subset of 11: `ACCOUNT_BALANCE`, `ACCOUNT_TRANSACTIONS`, `ACCOUNT_INTERNAL_TXS`, `ACCOUNT_ERC20_TRANSFERS`, `ACCOUNT_TOKEN_PORTFOLIO`, `ACCOUNT_NFT_PORTFOLIO`, `CONTRACT_ABI`, `CONTRACT_SOURCE`, `BLOCK_BY_NUMBER`, `TOKEN_HOLDERS` (native `/api/v2/tokens/{addr}/holders`), `TOKEN_HOLDER_COUNT` (token info `holders_count`) |
| Etherscan | v2 | ❌ No | `ETHERSCAN_KEY` | Full Etherscan-like surface + token holders (`tokenholderlist`/`topholders`/`tokenholdercount` are PRO endpoints) — all 33 `Method` values |
| NodeReal | v1 | Free tier | `NODEREAL_KEY` | BSC-only subset (25 `Method` values) incl. the only `CONTRACT_ABI`/`CONTRACT_SOURCE`/`ACCOUNT_INTERNAL_TXS` alternative for keyless-free BSC analytics |

> **Token holders notes:** the unified item shape is `{'address': EIP-55 str, 'value': str}`
> (raw-unit quantity — never Int64) — the ONE Method with a normalized cross-scanner item
> shape; everything else stays provider-native, so a caller switching providers for any
> other Method must expect the provider's own field names and nesting.
> Three providers serve the list to exhaustion (`result_window_for(TOKEN_HOLDERS) is None`):
> BlockScout V1, BlockScout V2 and NodeReal. Etherscan declares it but bounds it at 10_000.
> `TOKEN_HOLDER_COUNT` does NOT exist on BlockScout V1 (`getTokenHolderCount`,
> `tokenholdercount` and `getTokenHoldersCount` were all probed live and all answer
> `status=0` "Unknown action").
> `TOKEN_TOP_HOLDERS` is declared by Etherscan and NodeReal (`nr_getTokenHolders` with
> `topN`), not by either BlockScout leg: V2's holders endpoint documents no ordering, and
> V1's is *empirically* balance-ordered but documents no guarantee, so declaring it there
> would sell an observation as a contract.

> **Live verification status of the holder surface** (all probes 2026-09-02):
> BlockScout V1 and V2 are live-verified end to end (V1: 33/33 unique holders for a token
> whose count V2 independently reports as 33; no result window at 11k/50k depth where the
> *account* endpoints reject `page=11&offset=1000` outright). **NodeReal's three holder
> methods are now live-verified too** (2026-09-02, `bsc-mainnet`, BSC-USD and CAKE):
> the holder list returns the documented `{pageKey, details: [{accountAddress,
> tokenBalance}]}`, `pageKey` round-trips (3×100 holders, 300 distinct addresses, a fresh
> opaque cursor per page), and `topN` **does** order descending by balance — measured, so
> the docs' undirected "returned by balance order" is settled for that call. The plain
> holder list is NOT balance-ordered, which is why `TOKEN_TOP_HOLDERS` stays a separate
> declaration.
>
> **The one place the docs and the live API disagree: `nr_getTokenHolderCount`.** The docs
> show `{"result": "0x123"}` — the JSON-RPC `result` IS the hex count — while the live API
> answers `{"result": {"result": "0x46b3f99"}}`. Read as documented, that yielded **0
> holders for a token with 74 million of them**, a wrong answer indistinguishable from a
> token nobody holds. `_parse_token_holder_count` now accepts both shapes and raises
> `ChainscanDataError` on any third one instead of counting zero. End-of-pagination remains
> documented only by its complement ("If more results are available, a pageKey will be
> returned"), so treating an empty *or absent* `pageKey` as exhaustion is still an
> inference — the code accepts both.
>
> Keys for this live surface live in `~/.aiochainscan/.env` (machine-level, read by
> `ConfigurationManager` for every cwd, so worktrees need no plumbing); a repo-local
> `./.env` still overrides it. NodeReal also documents these two methods as "BSC and ETH mainnet
> only" while `supported_networks` is BSC-only — deliberately not widened, since nothing
> establishes ETH support for the other 22 methods.

> **BlockScout's per-instance REST carries a deprecation notice** for the Etherscan-compat
> `/api` layer, yet every V1 endpoint this library uses answered correctly and keylessly in
> the 2026-09-02 probes. Treat V1 as working-but-on-notice: a V1 breakage is expected to
> show up as a working V2 path, not as a bug here.

### NodeReal (MegaNode / BSCTrace backend) — BSC analytics

`nodereal` v1 talks JSON-RPC 2.0 to `https://bsc-{mainnet,testnet}.nodereal.io/v1/{key}`
(NodeReal's `nr_*` Enhanced API — the engine behind https://bsctrace.com) plus the
BscScan-compatible verified-contract REST on `open-platform.nodereal.io`. Networks:
`bsc` / `bnb` / `binance` (mainnet) and `bsc-testnet`.

- Declares 25 of the 33 `Method` values; honest `ValueError` for contract
  verify, gas oracle/estimate, price/supply stats, block reward/countdown.
- The public→wire mapping is DECLARED in `SPECS` and executed:
  `param_style` (`'rpc-positional'` / `'rpc-object'` / `'query'` for the
  contract REST) picks the wire shape, `param_map` carries every accepted
  public name (Etherscan-style input aliases included — first declared
  wins) and, for positional methods, the wire order. `_build_rpc_params` /
  `_build_transfer_filter` / `_resolve_window` / `_filter_transfer_items`
  all read their param sources from that map, so `supports_block_range` and
  the consistency sweep read the same declarations that run. Specs declare
  no `path` — `_rpc_url()` / `_rest_contract()` own the URLs.
- Token holders (`nr_getTokenHolders` / `nr_getTokenHolderCount`) page by an
  opaque `PageKey` — empty on the first request, non-empty while more pages
  exist — with a hex-encoded `PageSize` capped at 100 by the docs. Because
  `get_top_token_holders()` is a single non-paginated call, a `limit` above
  100 is silently clamped to 100 there. Doc-only, never live-verified: see
  the verification-status note under the support matrix.
- `nr_getTransactionByAddress` serves ≤1000 blocks per request and **silently
  returns empty pages for wider ranges** — `fetch_page` therefore walks the
  requested range in 1000-block windows, so `get_all_*` / `iter_*_streaming`
  see complete history. An unbounded end block resolves the chain tip once.
  The walk is deliberately NodeReal-local (the dialect's silent-empty-wide-
  range behaviour has no engine equivalent; folding it below the pagination
  seam would trade guarantee clarity for abstraction), but its block-range
  inputs are the spec's declared `fromBlock`/`toBlock` sources.
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

### BlockScout V2 and `TX_BY_HASH` — a transport blocker, not an omission

`GET /api/v2/transactions/{hash}` returns the full transaction dict, but its
payload carries a top-level `result` field of its own (the execution-status
string `"success"`/`"error"`), and `Network._handle_response` unwraps any
top-level `result` (then `data`) as an Etherscan envelope. So a declared
`TX_BY_HASH` on this scanner would hand callers the string `"success"` where
they expect a dict — verified live. `TOKEN_HOLDERS` and the account endpoints
are unaffected (`{items, next_page_params}`); the collision is a property of
the *payload*, so any future BlockScout V2 endpoint with a top-level
`result`/`data` key hits it too. Declaring the method is blocked on scoping
that unwrapping to the Etherscan dialect (or letting a spec opt out) — a
transport-contract change, not a scanner one. `EVENT_LOGS` is likewise
undeclared for a different reason: `/addresses/{hash}/logs` is address-scoped
with no topic or block filter on the wire, so a caller's `topic0=` or bounded
range would be silently dropped.

### Doc-declared input limits are enforced before the request

Two Etherscan endpoints document a hard input cap, and both are now refused
locally rather than sent and misinterpreted:
`getcontractcreation` takes at most `API_MAX_CONTRACT_CREATION_ADDRESSES` = 5
addresses, `topholders` at most `API_MAX_TOP_HOLDERS` = 1000. Both raise
`InputLimitExceededError` from
`EtherscanLikeScanner._perform_raw_request`, keyed on the `Method` enum (never
on a wire action string), which is the seam every Etherscan-dialect leg passes
through — including BlockScout V1, whose own `_perform_request` override
delegates upward for non-JSON-RPC methods.

`InputLimitExceededError` is a `ChainscanClientError` with
`failure_kind = FailureKind.FATAL`: an oversized input is refused identically
by every provider, so the pool must propagate it, not fail over and cool a
healthy provider. **This placement is load-bearing, not stylistic.**
`translate_unexpected_errors` in `scanners/base.py` re-raises only
`ChainscanClientError` and `MethodNotDeclaredError`; everything else — a bare
`ValueError` or `KeyError` from any scanner seam — becomes
`ChainscanNetworkError(retryable=False)`, whose `failure_kind` is `TRANSIENT`.
A caller's own bug therefore reads to the pool as a transient network fault:
it fails over, cools a working provider, and surfaces
`ProviderPoolExhaustedError` instead of the real error. Any new
"this call cannot be served as asked" exception must join the
`ChainscanClientError` family to survive that ladder.

---

## MCP Server (`aiochainscan/mcp/`)

Agent adapter over `ChainscanClient` — **run**: `python -m aiochainscan.mcp_server`
(requires `mcp` extra). Structure:

| File | Purpose |
|------|---------|
| `mcp/envelope.py` | `ToolResponse{data, notes, instructions, pagination, content_text}` + truncation (`{value_sample, value_truncated}`, 512 chars) + `format_units` (lossless int math) |
| `mcp/cursors.py` | Opaque Base64URL cursors wrapping `fetch_page` scanner cursors (`InvalidCursorError` with "start over" advice) |
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
- Cursor allow-lists are derived, never hand-listed: each Scanner declares the
  cursor-key vocabulary it may emit per method (`Scanner.cursor_keys` for a
  uniform dialect, `Scanner.CURSOR_KEYS` per `Method`, read via
  `cursor_keys_for`), and `mcp/tools.py`'s `scanner_cursor_keys` unions those
  declarations over the registered scanners serving the method. No
  scanner-private cursor key names (`__nr_window`, `pageKey`, `address_hash`,
  ...) appear as literals in `mcp/tools.py` — a new scanner's keys are
  accepted by registering the scanner alone.
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
2. Inherit from `Scanner` (or `EtherscanLikeScanner`) base class
3. Define `SPECS` dict mapping `Method` → `EndpointSpec` (set
   `unknown_params='drop'` for strict query APIs; path placeholders in
   `path` are excluded from the query automatically; `path` itself is
   optional — JSON-RPC dialect scanners whose `_perform_request` owns the
   URL leave it empty and declare `param_style` (`'rpc-positional'` /
   `'rpc-object'`) plus the full `param_map` so the builders, the
   block-range capability and the consistency sweep read one declaration)
4. The base owns the seams — do NOT override `call()` for transport:
   `Scanner.call()` applies the error ladder (`translate_unexpected_errors`)
   exactly once and dispatches through ONE mechanism (UrlBuilder endpoint
   via `network.get/post`, or a full URL via the `_request_url` hook).
   Override only dialect hooks: `_request_url` (per-instance hosts),
   `_transport_headers` (provider header quirks), `_error_context`,
   `_perform_request` / `_perform_raw_request` (transports no spec can
   express — JSON-RPC envelopes), `_require_mapped_network` for the
   network→URL table lookup. **Never touch HTTP sessions** — every request
   goes through the injected Network client.
5. Declare pagination caps where you measured them: `result_window`
   (scanner-wide `page * offset` cap), `max_page_size` (silent per-page
   clamp), and `RESULT_WINDOW_OVERRIDES` (per-method windows tighter than the
   scanner's) — see the guarantee-complete notes above.
6. Register in `scanners/__init__.py`

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
    InputLimitExceededError,      # ChainscanClientError, FailureKind.FATAL: caller passed more than the endpoint documents (see below)
    AbiTypeNotSupportedError,     # ValueError subclass: pure ABI codec has no rule for this Solidity type
    MethodNotDeclaredError,       # ValueError subclass: method not in SPECS
    BlockRangeNotSupportedError,  # MethodNotDeclaredError subclass: bounded block range the provider's spec cannot carry (raised at every seam: call/fetch_page/stream)
    ProviderPoolExhaustedError,   # Pool: every provider failed (.attempts)
    ChainscanProviderSwitchWarning,  # Pool: routed away from a provider
    AbiTypeNotSupportedError,     # ValueError subclass: Solidity type no decode tier handles
    PureAbiDecodeWarning,         # Bulk decode running without the [fastabi] Rust backend
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

## ABI Decode Backend Chain

`decode.py` picks a backend per process: `fastabi` (Rust, `[fastabi]`) →
`abi_pure.py` (always available). There is no third tier — `abi_pure.py`
covers the whole ABI spec, so a bare `pip install aiochainscan` decodes
transaction inputs, event logs, `SmartContract.iter_events` and the MCP
`read_contract` / `get_transaction_info` tools with no extras installed.
`eth-abi` is a **test oracle** in `[dev]`, never a runtime path.

- **One output convention across both tiers** (the Rust one): ints above
  `i64::MAX` as strings, `bytes`/`bytesN` as `0x` hex, arrays *and* tuples as
  `list`. `tests/test_abi_pure.py::TestTierParity` pins it — a decoded value
  must not change shape when a user adds or drops `[fastabi]`.
- **Unsupported Solidity type → `AbiTypeNotSupportedError`**, never an empty
  `decoded_data`: a gap in this library must not read as undecodable
  calldata. Malformed/truncated calldata stays non-fatal (empty result), which
  is what `_MALFORMED_CALLDATA_ERRORS` is for — a spam transaction whose
  selector collides must not kill a decode loop.
- **Both tiers are strict about padding**, and deliberately so: the spec says
  the unused bits of a word are zero (or the sign extension, for `int<N>`), so
  rejecting is more defensible than guessing. Dirty `address`/`bytesN`
  padding, an out-of-range `uint<N>`/`int<N>`, a non-canonical `bool` and a
  dynamic offset pointing into the head area all raise. So does non-zero
  padding between a dynamic value and its 32-byte boundary — but only the
  padding bytes actually present are checked: a payload whose final pad is
  absent is a truncation the length checks already own, and rejecting it here
  would reject data eth-abi accepts. `ethabi` is lenient
  and has no strict mode, so the Rust tier gets a hand-written validation pass
  (`validate_sequence` in `lib.rs`) before `Function::decode_input`; it works
  on byte slices only, no bignum. That pass must also validate `string` as
  UTF-8 itself: `ethabi` converts lossily, so without the check a non-UTF-8
  byte sequence decodes to U+FFFD on Rust and raises on the floor — the same
  calldata reading differently per tier. Do not implement any of this by
  re-encoding and comparing — that is *over*-strict (it rejects non-minimal
  but legal offsets).
- **Cost of strictness: +14% end-to-end on the pure floor**
  (`decode_transaction_input`, ERC-20 `transfer`; +48% on the raw two-word
  `decode_values`, where nothing else is left to amortize it; `-m benchmark`
  in `tests/test_abi_pure.py`), **+2% single / +25% bulk on the Rust tier**
  (0.516→0.526 us/call, 1.045→1.311 ms per 1000). Keep `validate_sequence`
  generic over the parameter iterator: materializing a `Vec<ParamType>` per
  call instead cost +99% single / +143% bulk, which is what the pass looked
  like before that one allocation was removed. Bulk work (`decode_many`, streaming, DataFrames)
  still belongs on `[fastabi]`, and `decode_transaction_inputs_batch` says so
  once per process (`PureAbiDecodeWarning`) for batches of 50+. Log decoding
  never had a Rust path at all (fastabi decodes *inputs* only), so it warns
  about nothing.
- **`fixedMxN` / `ufixedMxN` decode to `Decimal`** (`raw / 10**N`, exact via
  `scaleb`). They exist so `AbiTypeNotSupportedError` cannot fire where the
  old eth-abi tier coped. Widths are validated at parse time: `int`/`uint`
  a multiple of 8 in 8..256, `bytesN` 0<N≤32, fixed scale 0<N≤80.
  Every `scaleb` must be passed `_FIXED_CONTEXT` explicitly: `scaleb` is a
  *context* operation and the default context's `prec=28` silently rounds a
  full-width value (int256 needs 78 significant digits) into a confident wrong
  number. The `Decimal(str)` constructor itself is exact and context-free.
- **The Rust tier falls through, not out**, when it recognises nothing:
  `fastabi` answers an unimplemented type with an empty `function_name`
  rather than an error, which would silently give `[fastabi]` users *less*
  than a base install. `_decode_transaction_input_fast` therefore retries on
  the pure floor whenever the Rust result is empty — and so does
  `decode_transaction_inputs_batch`, which shares the same rule: a type that
  falls back in a single decode must not come back empty in a batch of the
  same call. Both retries are gated on `_declares_selector`: without it every
  transaction whose selector this ABI does not declare would be re-decoded on
  the floor to reach the same empty answer, which on the bulk path is the
  whole cost of the bulk path.
- **The floor's hot path is the glue, not the ABI walk.** Decoding an ERC-20
  `transfer` spends ~40% in `abi_pure` and the rest in `decode.py`, so the
  conventions are applied in ONE traversal (`_to_rust_convention`) and the hot
  functions avoid `typing.cast`, which is a real call at runtime. Arrays get
  `_decode_array` rather than `_decode_sequence([elem] * count, ...)`: no list
  of N references, and the head size is a multiplication instead of a sum
  over N. Splitting the traversal per rule or reintroducing the casts costs
  ~30% end-to-end, which is what this shape was measured against.
- **The ABI index is cached** (`_abi_index`): identity fast path, then a
  content digest, holding the function/event maps plus each selector's
  compiled decode plan — hashing an ABI costs more than decoding against it.
  The index is built from a round-trip of the serialized ABI, so it shares no
  mutable state with any caller: one index serves every equal ABI list, and
  without the copy an in-place mutation of one list would change how every
  other one decodes. Mutating a list in place still leaves *its own* cached
  index stale (the identity path never rehashes) — build a new list instead.

---

## Rust FFI Notes (fastabi/)

- **Build**: NOT automatic. Since the distribution split the base package builds with hatchling, so `uv sync --extra dev` installs no Rust extension — build it explicitly with `cd aiochainscan/fastabi && uv run --with maturin maturin develop --release`, or pass `AIO_BUILD_FASTABI=1` to `make wt-new`. Without it `tests/test_crypto.py` skips 12 tests and `decode()` uses the Python fallback; `scripts/agent/preflight.sh` reports which module (if any) is live.
- **Version floor**: the extension exports `__version__` from `CARGO_PKG_VERSION`, and
  `decode.py` refuses anything below `_MIN_FASTABI_VERSION` (0.2.0) — the release that made
  the Rust tier reject non-UTF-8 strings and dirty dynamic padding. A stale local build is
  ignored with `PureAbiDecodeWarning` and decoding drops to the pure floor, because a tier
  that decodes by the pre-strict rules is worse than no Rust tier. Bump both
  `fastabi/Cargo.toml` and `fastabi/pyproject.toml` whenever decode semantics change, and
  raise the floor with them.
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
Everything else is an extra (`data`, `mcp`, `http2`, `fallback`). `[fallback]`
is native **keccak** only (`_keccak.py` is ~97× slower than `eth-hash`); ABI
decoding needs no extra at all.

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
