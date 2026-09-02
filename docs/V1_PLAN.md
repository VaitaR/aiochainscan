# aiochainscan v1 plan

Product thesis: **the most reliable Python extraction layer for EVM explorer data.**
Three promises to the user — one API over Etherscan V2 + Blockscout; complete history
with no silent data loss; stream/decode/load straight into an ETL.

Everything below is scoped against that thesis. Anything that does not serve one of the
three promises is out of scope for v1 (explicitly: NFT abstractions, prices, DeFi
protocol adapters, multicall, signing, contract writes, additional explorer vendors).

## Ground truth as of 2026-09-02 (verified against main @ ad278a8)

- `pyproject.toml`: `version = "0.6.0"`, `build-backend = "maturin"`, runtime deps are
  exactly `httpx`, `aiolimiter`, `tenacity`, `orjson`.
- `aiochainscan/fastabi/Cargo.toml`: `ethers 2.0 (abigen)`, `arrow 53 (ffi)`,
  `pyo3-arrow 0.5`, plus pyo3/serde/pythonize/hex/thiserror/twox-hash/dashmap/mini-moka.
- `README.md:18-22` instructs installing from git because PyPI still serves 0.2.x.
- `core/client.py:50-51`: `ScannerName` and `NetworkName` are hard-coded `Literal`s.
- `ChainscanPool` (`core/pool.py`) already implements multi-provider failover with
  failure classification, sticky routing, cooldowns and pinned pagination.
- `blockscout` v1 already routes `TX_BY_HASH` / `PROXY_*` through `POST {base}/api/eth-rpc`.
- `services/pagination.py` has **no** range splitting and does not reference
  `PaginationDataLossError` (the exception exists in `exceptions.py` only).
- `services/analytics.py:191` `transactions_to_dataframe_arrow` is the sole consumer of
  the Rust Arrow path.

## Rejected, with reasons

| Proposal | Decision | Reason |
|---|---|---|
| Drop `tenacity` + `aiolimiter`, hand-roll retry/rate-limit | Rejected | 4 small mature runtime deps; trading them for ~200 unaudited LOC moves risk into our code for no user-visible gain. |
| Replace `ethers-rs` with Alloy crates | Deferred to post-v1 | The motivation was Rust graph size; once fastabi is a separate optional wheel that graph is off the default install path. Still worth doing for accelerator build time, not now. |
| Rename `ChainscanClient` → `Chainscan` | Rejected | Cost is the whole codebase, docs and ~1010 tests; benefit is aesthetic. The real defect is the constructor, fixed in Track D. |
| New `client.raw.account.txlist()` facade | Rejected | `client.call(Method.X, ...)` is already the raw escape hatch. Document it instead of adding a second way to do the same thing. |
| Transparent RPC fallback everywhere | Out of scope for v1 | Only some failure classes may fall back; `classify_failure` already encodes that distinction. An `RpcProvider` pool member is post-v1. |

---

## Track A — pure-Python base install (P0)

**Goal:** `pip install aiochainscan` requires no Rust toolchain and builds no native code.

1. Split distributions:
   - `aiochainscan` — pure Python, `build-backend = "hatchling"`, universal wheel.
   - `aiochainscan-fastabi` — the Rust accelerator, built by maturin from
     `aiochainscan/fastabi/`, published separately.
   - `aiochainscan[fastabi]` extra depends on `aiochainscan-fastabi`.
2. **Module name migration (the one hard constraint).** The canonical import is currently
   `aiochainscan.aiochainscan_fastabi`. A separate distribution cannot cleanly install a
   module into another distribution's package namespace, so the accelerator moves to
   top-level `aiochainscan_fastabi`. Every import site must accept **both** names during
   the transition (new name first, old name as fallback), so an existing editable/maturin
   checkout keeps working.
3. Arrow decision — **measure before removing.** Benchmark
   `transactions_to_dataframe_arrow` (Rust → Arrow FFI → Polars) against building
   normalized dicts and calling `pl.from_dicts()`, on a realistic batch (≥100k rows).
   Report both numbers next to a representative single-page HTTP latency. Remove `arrow`,
   `pyo3-arrow` and the Python wrapper **only if** the win is small relative to network
   time; otherwise keep them behind the `arrow` cargo feature, off by default.
4. Prove the pure-Python path: install the built sdist/wheel into a clean venv with no
   Rust toolchain available, import the package, and run the suite both with and without
   the `fallback` extra.

**Blocks:** Track B (cannot publish until the build backend is settled).

## Track B — release (P0, owner: main session, not delegated)

Publishing is an irreversible outward-facing action and stays with the main session,
gated on explicit user approval.

1. `0.6.0` → `1.0.0` in `pyproject.toml` and `AGENTS.md`.
2. `CHANGELOG.md` for 1.0.0, release notes.
3. Publish both distributions to PyPI; drop the git-install instructions from `README.md`.
4. Re-enable workflows (`gh workflow enable ci.yml test-install.yml wheels.yml`);
   `wheels.yml` now builds two packages (pure-Python universal + native per-platform).
5. Run the suite with `--extra mcp` so `tests/test_mcp_server.py:966,980` stop skipping.

Rationale for the priority: while PyPI serves 0.2.x with the removed legacy API, any
agent or developer who looks the library up writes code against a dead interface. That
outranks every feature below.

## Track C — guaranteed complete pagination (P0 feature, the differentiator)

**Goal:** `guarantee_complete=True` means "every matching record was returned, or an
exception was raised" — never silent truncation.

1. Adaptive block-range splitting in `services/pagination.py`: when a provider signals a
   result-limit overflow for `[from_block, to_block]`, bisect the range and recurse until
   each window provably fits under the cap. `scanners/nodereal_v1.py` already walks a
   range in fixed 1000-block windows — read it as a working precedent, but this must be
   *adaptive*, not fixed-width.
2. Detect the overflow condition per provider. Explorers signal a hit cap inconsistently
   (exact-`offset` result counts, "result window is too large" style errors, silently
   truncated pages). Enumerate what each supported scanner actually does and encode it
   explicitly — a heuristic that guesses wrong here reintroduces exactly the silent data
   loss this track exists to eliminate.
3. Raise `PaginationDataLossError` when a range cannot be split further (single block
   over the cap) — it must carry the block range and the observed cap. Wire the existing
   exception into the real code path; today nothing raises it from `pagination.py`.
4. `guarantee_complete: bool` threads through `get_all_*` / `iter_*_streaming`.
   Decide and document the default. Recommendation: default `True` for correctness, with
   the cost (more requests on wide ranges) stated in the docstring and `AGENTS.md`.
5. Tests must prove the guard is **non-vacuous**: a stub scanner that truncates at a cap,
   asserting the split path recovers the full set, and asserting the error fires when
   splitting is exhausted.

## Track D — normalized models + honest constructor (P1)

**Goal:** make "unified SDK" true at the type level, and fix the constructor whose
awkwardness forced a "use only `from_config()`" doc warning.

1. Frozen slotted dataclasses in `domain/` — `Transaction`, `TokenTransfer`,
   `InternalTransaction`, `Log`, `Block`. **No new dependencies** (no Pydantic).
   Each carries `provider_data` holding the untouched provider response, so a field the
   library does not know yet is never lost.
2. Per-provider normalization: Etherscan V2 and Blockscout describe the same entity
   differently, and absorbing that difference is the entire value proposition. Map field
   by field from real fixtures, not from assumption. Where a field exists on one provider
   only, it is `None` — never invented, never silently defaulted.
3. Wei/quantity fields stay exact: `int` or `Decimal`, never `float`. Addresses are EIP-55
   checksummed via the existing `domain/models.py` helpers. Timestamps are tz-aware UTC
   via `convert.py`.
4. Additive rollout: normalized accessors are new methods/flags alongside the existing
   dict-returning surface. Do **not** change what current methods return in this track —
   ~1010 passing tests encode that contract.
5. New public constructor `ChainscanClient(chain=..., provider=..., api_key=...)` where
   `chain` accepts a chain id or an alias; scanner version, api kind, base URL and network
   naming become implementation details. `from_config()` stays as a supported alias.

## Track E — distribution (P1, after A–D)

Ordered by leverage, all of it dependent on a published package and a real API surface:

1. Docs targeting concrete search intents (~8-10 pages), each shaped
   *problem → 15 lines of working code → why this library → where it is worse*.
2. An honest comparison page, including "for contract writes and signing, use web3.py".
3. `SKILL.md` (a decision tree, not a pitch), `llms.txt`, Context7 registration.
4. Post-v1: `RpcProvider` as a pool member, first-class Blockscout v2, generated chain
   registry replacing the hard-coded `Literal`s.

MCP stays an extra, not a product. MCP Registry submission comes after SDK adoption.
