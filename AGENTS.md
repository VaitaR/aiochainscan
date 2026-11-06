# aiochainscan - Agent Contract

Async Python wrapper for blockchain explorer APIs (Etherscan, BlockScout, NodeReal,
Routescan): one `ChainscanClient` interface, hexagonal architecture with dependency
injection, guaranteed-complete pagination, exact Wei math, optional Rust FFI (`fastabi`)
for ABI decoding.

## Reference docs: read the one your task touches

| Read | When you |
|---|---|
| [docs/agents/client-surface.md](docs/agents/client-surface.md) | add/change a convenience method, need a method's name/return shape, custom base URLs, polling helpers, `convert.py` |
| [docs/agents/pagination.md](docs/agents/pagination.md) | touch `services/pagination.py`, `fetch_page`, `result_window` / `max_page_size` / `RESULT_WINDOW_OVERRIDES`, completeness errors, measured caps |
| [docs/agents/providers.md](docs/agents/providers.md) | change a scanner, its `SPECS` or networks, the chain registry, holder methods, credentials loading; need a provider's measured behaviour |
| [docs/agents/failover-pool.md](docs/agents/failover-pool.md) | touch `core/pool.py`, `classify_failure` / `FailureKind`, cooldowns |
| [docs/agents/contracts-and-proxies.md](docs/agents/contracts-and-proxies.md) | touch proxy resolution, `SmartContract`, `decode_input` / `decode_transactions` / `decode_logs` |
| [docs/agents/abi-decoding.md](docs/agents/abi-decoding.md) | touch `decode.py`, `abi_pure.py`, `aiochainscan/fastabi/`, or build the Rust extension |
| [docs/agents/mcp-server.md](docs/agents/mcp-server.md) | touch `aiochainscan/mcp/`, `mcp_server.py` or `mcpb/` |

User-facing docs live in [docs/](docs/README.md); the scanner declarations in
`aiochainscan/scanners/` win when a doc and the code differ.

## Public API

Use `ChainscanClient` only; legacy facade/context/url-builder entrypoints are gone.

```python
from aiochainscan import ChainscanClient, ChainscanPool

async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    balance = await client.get_balance('0x...')             # Wei string
    txs = await client.get_transactions('0x...')            # ONE page
    all_txs = await client.get_all_transactions('0x...')    # every record, or an exception
    async for batch in client.iter_transactions_streaming('0x...', batch_size=1000):
        ...                                                  # constant memory
    abi = await client.get_contract_abi('0x...', follow_proxy=True)
    calls = await client.decode_transactions(txs)

# A URL-shaped network targets a self-hosted BlockScout / Etherscan proxy:
ChainscanClient.from_config('blockscout_v2', 'https://my-blockscout.internal', expected_chain_id=100)

async with ChainscanPool.from_config([('etherscan', 'ethereum'), ('blockscout', 'ethereum')]) as pool:
    await pool.get_balance('0x...')                          # failover, full client surface
```

Every `Method` enum value (34) has a typed convenience method; a method the configured
scanner does not declare raises `MethodNotDeclaredError` (a `ValueError`) at call time.
The Method ↔ mixin ↔ SPECS mapping is enforced by `tests/test_method_consistency.py`.
`aiochainscan scanners` prints each scanner's declared methods, chains, caps and keys.

### Key gotchas

- `get_transactions()` / `get_logs()` / `get_token_holders()` return **one page**. For
  complete data use `get_all_*()` (materialized via streaming aggregation) or
  `iter_*_streaming()` (large datasets); `get_transactions_df()` auto-paginates.
- `get_all_*()` / `iter_*_streaming()` default to `guarantee_complete=True`: every matching
  record or an exception (`PaginationDataLossError`, `CompletenessUnavailableError`) —
  never silent truncation. `get_all_token_holders` on Etherscan raises for >=10_000
  holders; the error names providers that serve the list completely.
- A **bounded** block range (`from_block > 0` / concrete `to_block`) on a provider whose
  spec declares no block-range params raises `BlockRangeNotSupportedError` at every seam
  (single-page `get_*`, `call()`, `fetch_page()`, streams) instead of dropping the bounds.
- `get_contract_abi()` returns the ABI stored **for that address** — for a proxy, the
  proxy's own ABI, which decodes none of its traffic. Pass `follow_proxy=True`, or use
  `get_contract()` / `SmartContract.from_address()`. `proxy_strategy='metadata'` (default)
  costs no extra request; `'auto'` / `'chain'` read storage slots and the diamond loupe.
- Balance/value/supply values are **Wei strings**: convert with `wei_to_ether()` /
  `to_decimal_amount()` (exact `Decimal`), never `int(wei) / 10**18`.
- Raw responses are provider-native. Only `TOKEN_HOLDERS` items share one cross-scanner
  shape (`{'address': EIP-55 str, 'value': str}`).
- ENS: `None` means no record; `MethodNotDeclaredError` when the scanner lacks `eth_call`;
  `ENSScannerUnavailableError` (a `ValueError`) off Ethereum mainnet, from the batch calls
  too. Rate limits and transport failures surface as themselves.

## Workflow: worktrees and scripts

**One session == one worktree == one branch.** Never switch branches or stash to share a
directory with another agent session — parallel sessions on one checkout cause
`.git/index.lock` collisions and lost work.

```bash
make wt-new SLUG=my-task                 # .claude/worktrees/my-task on branch feat/my-task
                                         # copies .env, runs uv sync --extra dev --frozen
make wt-ls                               # list worktrees + merge status (dry-run)
make wt-rm SLUG=my-task ARGS="--yes"     # teardown — refuses dirty or unmerged worktrees
```

Branch types: `feat | fix | chore | docs | arch | refactor` (2nd arg, default `feat`);
base ref (3rd arg, default `origin/main`). Env knobs: `AIO_SKIP_SYNC=1`,
`AIO_BUILD_FASTABI=1`.

| Script (`scripts/agent/`) | Purpose |
|--------|---------|
| `new-worktree.sh` | Bootstrap an isolated session worktree |
| `provision-worktree.sh` | Provision an EXISTING worktree (.env, skills, .venv, fastabi) — shared by `new-worktree.sh` and `../xworker-bootstrap.sh` |
| `rm-worktree.sh` | Safe teardown — only clean + merged worktrees, squash-merge aware, integration branches protected |
| `preflight.sh` | Run BEFORE starting: env, deps, imports, test collection, fastabi status |
| `validate_fast.sh` | The DONE gate (`make validate`) — ruff, format, import-lint, mypy --strict, full pytest |
| `safe_commit.sh` | `git add` + commit with index.lock retry (use `make commit MSG="..." PATHS="..."`) |
| `ci_watch.sh` | Bounded GitHub Actions poller for a pushed commit; exit status is the verdict |
| `probe_provider_caps.py` | `make probe-caps`: re-measures declared pagination caps live; exit 1 on drift, rate-limited/inconclusive probes or an unconstructible provider |
| `probe_blockscout_hosts.py` | `make probe-hosts`: re-verifies BlockScout hosts live; a 429 is INCONCLUSIVE, never a dead host |
| `build_mcpb.py` | `make mcpb`: packs `mcpb/` into `dist/aiochainscan-<version>.mcpb`; refuses while the bundle and `server.json` versions disagree |
| `ruff_format_hook.py` | PostToolUse hook — auto-formats edited `*.py` |

Claude Code: `.claude/settings.json` runs `ruff_format_hook.py` on the edited file only (so
`make validate` still gates the repo), allow-lists the agent scripts, `make`, read-only
git/gh and `uv run` quality commands (add a routine command there rather than approving it
each session) and denies `.env`. `.claude/rules/fastabi.md` attaches when you touch
`aiochainscan/fastabi/**` or `aiochainscan/decode.py`.

## Validation and commit (mandatory)

Run BEFORE `git commit`, not after:

```bash
make validate        # ruff + format + import-lint + mypy --strict + full pytest (the DONE gate)
pre-commit run --all-files
```

Commit only when both pass (`make commit MSG="..." PATHS="..."`); do not rely on a
post-commit hook. `make ci-local` mirrors GitHub CI. GitHub Actions (CI/CD, Test
Installation, Build and Publish Wheels) are enabled; watch a pushed commit with
`scripts/agent/ci_watch.sh`. Add `# noqa: CODE` only when the error is unavoidable, with
the reason.

Setup: `uv sync --extra dev` (deps only — the Rust extension is built separately, see
[abi-decoding.md](docs/agents/abi-decoding.md#rust-ffi-fastabi)). Required runtime deps are
`httpx`, `orjson`, `tenacity`, `aiolimiter`; everything else is an extra (`data`, `mcp`,
`http2`, `fallback`, `fastabi`). `[fallback]` is native **keccak** only (`_keccak.py` is
~97× slower than `eth-hash`); ABI decoding needs no extra. Live keys: see
[providers.md](docs/agents/providers.md#credentials).

## Architecture

Layers, top to bottom: client/domain (`core/client.py` + `core/mixins/`, `core/pool.py`,
`domain/`) → scanners (`scanners/`) → aggregation services (`services/pagination.py`,
`analytics.py`, `ens_resolver.py`) → ports (`ports/`: cache, progress, rate limiter) →
adapters (`adapters/`: memory cache, aiolimiter, tenacity retry) → Rust FFI (`fastabi/`).

**Dependency rule**: Only downward. Never upward. Never bypass Network layer. The layering
contracts are enforced by import-linter from `pyproject.toml`
([ADR 0001](docs/adr/0001-layering-contracts-live-in-pyproject.md)).

### Key files

| File | Source of truth for |
|------|---------------------|
| `core/client.py` + `core/mixins/` | `ChainscanClient`: one convenience method per `Method` plus `get_all_*`/`iter_*`/`wait_for_*`; constructed via `ScannerTarget` (`from_config` / `chain=`-`provider=` kwargs; the positional field form is gone) |
| `core/streaming.py` | `STREAMING_SPECS` registry (Method, params builder, operation noun, flags) + the ONE shared stream implementation; pool forwards and test sweeps derive from it |
| `core/pool.py` | `ChainscanPool`: `classify_failure`, sticky routing, cooldowns, pinned pagination |
| `domain/method.py` | `Method` enum (34 values) |
| `domain/contract.py` | `SmartContract` |
| `domain/models.py` | `Address`, `TxHash`, EIP-55 validation |
| `config.py` | `ConfigurationManager`: credential/env resolution only. Topology lives in `registry/` (`data.py` tables, `views.py` derivations, `resolve.py` target resolution), re-exported by `chain_registry.py` |
| `services/pagination.py` | `iter_pages`/`iter_items`/`collect_all` over `Scanner.fetch_page` cursors + the guarantee machinery (adaptive range splitting) |
| `services/analytics.py` | Polars DataFrames (Utf8 for Wei) |
| `services/ens_resolver.py` | ENS resolution: cache + BlockScout V2 `ens_domain_name` |
| `network.py` | HTTP transport — ALL HTTP goes through here |
| `response_dialects.py` | `ResponseDialect` protocol: `EtherscanEnvelope` + `JsonRpcEnvelope` |
| `convert.py` | Wei/hex/datetime helpers: exact `Decimal`, hex-aware int parsing, tz-aware UTC |
| `crypto.py` | Keccak-256, EIP-55: fastabi → eth-utils → pure-Python (`_keccak.py`) fallback chain |
| `decode.py` / `abi_pure.py` | ABI decoding: fastabi → pure-Python floor (no third tier) |
| `_redaction.py` | Credential redaction helpers (re-exported from `network.py`) |

## Critical warnings

### Data integrity
| ❌ DON'T | ✅ DO | Why |
|----------|-------|-----|
| Use `pl.Int64` for Wei | Use `pl.Utf8` (String) | Int64 overflows at 9.22 ETH |
| Use raw pointers as cache keys | Use content hash (xxhash) | Python reuses memory addresses |
| Store addresses lowercase | Use `to_checksum_address()` | EIP-55 checksum matters for comparisons |

### Async performance
| ❌ DON'T | ✅ DO | Why |
|----------|-------|-----|
| Use `requests.get()` | `await` the injected client | Blocks the event loop |
| Create httpx/aiohttp sessions in scanners | Use `Network.request()` | Bypasses connection pooling/retry |
| Build PyDict in Rust loops | Return JSON, parse with orjson | GIL blocks the event loop during object creation |
| O(N) scan in cache `set()` | Lazy TTL check in `get()` only | 100k items = seconds of freeze |
| `response.json()` | `orjson.loads(response.content)` | One parser, bytes in |

### Pagination and retry
| ❌ DON'T | ✅ DO | Why |
|----------|-------|-----|
| Use `get_transactions()` / `get_logs()` for all data | `get_all_*()` or `iter_*_streaming()` | A page holds ~50-100 txs / ≤1000 logs |
| Wrap an async generator with `@retry` | Retry inside the generator at page-fetch level | Tenacity completes when the generator is created, not exhausted |
| Reset adaptive offset per page | Persist offset state across all pages | "Yo-yo effect" doubles API requests |
| Skip whale blocks silently | Raise `PaginationDataLossError` | Silent data loss is unacceptable |
| Report a rangeless capped endpoint as a whale block | Raise `CompletenessUnavailableError` naming a provider that can serve it | Holder lists have no range to split |
| Call complete data "lost" when the window came back exactly full | Say *possibly* truncated (`confirmed=False`) | A false error on correct data is wrong, not loud |
| Trust a partial page to mean "end of data" | Treat `>= Scanner.result_window` records as overflow | A capped API truncates with a partial page and no error |
| Assume the provider honoured the `offset` you sent | Clamp it to `Scanner.max_page_size` before comparing | Etherscan serves 1000 for `offset=5000` with `status=1` |
| Give every endpoint the scanner's one `result_window` | Declare tighter ones in `RESULT_WINDOW_OVERRIDES` | BlockScout V1 `getLogs` caps at 1000 and ignores paging |
| Split a range in fixed-width windows | Bisect on the *observed* overflow boundary | Fixed windows waste requests where sparse, truncate where dense |
| Run `get_all_logs` on Etherscan with the default 10s `timeout` | Pass `timeout` above ~35s | The ~30s server-side refusal is what the engine splits on; a shorter timeout fails with `ChainscanNetworkError` |
| Reason about a provider cap | Re-measure it (`make probe-caps`) | Caps change silently; Etherscan cut its page size to 1000 in July 2026 |

### Network
| ❌ DON'T | ✅ DO | Why |
|----------|-------|-----|
| Use HTTP/2 with burst requests | `max_burst=1` or HTTP/1.1 | Cloudflare WAF sends GOAWAY, not 429 |
| Retry only `TimeoutException` | Include `NetworkError`, `RemoteProtocolError` | Connection resets are common |

## Errors and the error ladder

```python
from aiochainscan.exceptions import (
    ChainscanRateLimitError,      # Retry with backoff
    ChainscanNetworkError,        # Retry (connection issues)
    ChainscanResultWindowExceededError,  # FATAL: provider refused the request as too big (engine splits it)
    PaginationDataLossError,      # Whale block: a single block over the API's cap
    CompletenessUnavailableError, # Endpoint has no splittable dimension here (.alternatives)
    ChainscanDataError,           # Data contract violation
    ENSScannerUnavailableError,   # ValueError: ENS cannot be served on this scanner/network
    InputLimitExceededError,      # ChainscanClientError, FATAL: input over a documented cap
    AbiTypeNotSupportedError,     # ValueError: no decode tier handles this Solidity type
    MethodNotDeclaredError,       # ValueError: method not in SPECS
    BlockRangeNotSupportedError,  # MethodNotDeclaredError: bounded range the spec cannot carry
    ProviderPoolExhaustedError,   # Pool: every provider failed (.attempts)
    ChainscanProviderSwitchWarning,  # Pool: routed away from a provider
    PureAbiDecodeWarning,         # Bulk decode running without the [fastabi] Rust backend
)
```

**Any new "this call cannot be served as asked" exception must join the
`ChainscanClientError` family.** `translate_unexpected_errors` in `scanners/base.py`
re-raises only `ChainscanClientError` and `MethodNotDeclaredError`; anything else — a bare
`ValueError` or `KeyError` from a scanner seam — becomes
`ChainscanNetworkError(retryable=False)`, whose `failure_kind` is `TRANSIENT`. The pool
would then fail over, cool a working provider and surface `ProviderPoolExhaustedError`
instead of the real error. Example: `InputLimitExceededError`
([providers.md](docs/agents/providers.md#doc-declared-input-limits)).

## Common tasks

### Adding a new scanner
1. Create `scanners/newscan_v1.py`, inheriting `Scanner` (or `EtherscanLikeScanner`).
2. Define `SPECS`: `Method` → `EndpointSpec`. Set `unknown_params='drop'` for strict query
   APIs; `path` placeholders are excluded from the query automatically. JSON-RPC dialect
   scanners whose `_perform_request` owns the URL leave `path` empty and declare
   `param_style` (`'rpc-positional'` / `'rpc-object'`) plus the full `param_map`, so the
   builders, the block-range capability and the consistency sweep read one declaration.
3. Register the scanner's declared networks in `tests/test_registry_consistency.py`:
   `test_all_scanners_are_swept` fails until they join the cross-product construction
   sweep (alias spellings like `bnb`/`binance`/`bsc` resolve to one target).
4. The base owns the seams — do NOT override `call()` for transport. `Scanner.call()`
   applies the error ladder once and dispatches through ONE mechanism (UrlBuilder endpoint
   via `network.get/post`, or a full URL via `_request_url`). Override only dialect hooks:
   `_request_url`, `_transport_headers`, `_error_context`, `_perform_request` /
   `_perform_raw_request` (transports no spec can express), `_require_mapped_network`.
   **Never touch HTTP sessions.**
5. Declare pagination caps you measured: `result_window`, `max_page_size`,
   `RESULT_WINDOW_OVERRIDES` ([pagination.md](docs/agents/pagination.md)).
6. Register in `scanners/__init__.py`.

### Adding bulk fetch support
1. Extend `ChainscanClient` methods and scanner `SPECS` first.
2. Keep `get_all_*` as materialized results of streaming aggregation, with a matching
   `iter_*_streaming` path (declared in `core/streaming.py`).
3. Thread `on_progress` callbacks through every public client method.

### Modifying HTTP behaviour
- Rate limiting: `adapters/aiolimiter_adapter.py` (token bucket, burst=1 for APIs).
- Retry: `network.py` has one admission path (`Network._send`: guard → rate-limit →
  dispatch → handle → finish → retry, written once), retrying
  `exceptions.TRANSIENT_EXCEPTIONS` — the single transient vocabulary shared with the
  first-request guard and `TenacityRetryAdapter.DEFAULT_RETRY_EXCEPTIONS`.
- Response envelopes: `response_dialects.py`. An absent/empty content-type header is
  accepted as an opaque JSON attempt; an explicit non-JSON type (`text/html`) is refused
  before parsing.

## Code quality

- Follow the hexagonal architecture; never bypass the Network layer.
- All Wei values as strings, all addresses as EIP-55 checksum.
- Never hardcode keys; `ConfigurationManager` resolves them from the environment / `.env`.
