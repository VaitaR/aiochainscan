---
kind: deepening-brief
id: C6
slug: one-decode-seam
source: ../2026-09-03-review.md
status: done
base: 50d971e
---

# One decode seam for the single and batch paths

> **Done** — flash lane died to a provider rate limit mid-run; an in-session finishing agent salvaged the uncommitted work (verdict: coherent near-finish), completed two gaps, and committed `7a4df06`; merged to `main` (2026-09-03, no-ff). Gate: PASS-WITH-FINDINGS (LOW only; benchmark no-regression). The brief's repo-wide dead-name grep self-conflicts with its own `fastabi/` fence — resolved by scoping to decode.py.

## Repo orientation

aiochainscan is an async Python wrapper for blockchain-explorer APIs. `aiochainscan/decode.py`
picks an ABI-decode backend per process (Rust `fastabi` → pure-Python `abi_pure.py` floor)
and applies one output convention. Three entry points (fast single, pure single, batch)
currently restate the same plumbing. Tests: `uv run pytest tests/ -q`; gate
`make validate`. Note: the worktree has no Rust fastabi build — fastabi-gated tests skip;
that is expected.

## Task

Concentrate the per-item decode plumbing into one seam shared by all three entry points,
cache the serialized ABI string, delete six dead bindings — with zero behavioural change
and no hot-path regression.

## Current state (verified on `base`)

- **Fall-through rule implemented twice:** `decode.py:384-385` (single fast path) and
  `:753-755` (batch): "if fastabi returned an empty `function_name` AND the ABI declares
  the selector (`_declares_selector`), retry on the pure floor".
- **Duplicated fragments:** input-length guard `:361-364` / `:403-406` / `:723`; hex `0x`
  strip `:369-370` / `:725-726`; exception tuple `except (ValueError, KeyError, TypeError,
  RuntimeError)` `:391` / `:765`; empty-mark assignment (`decoded_func=''`,
  `decoded_data={}`) at six sites (`:362-363, :404-405, :436-437, :446-447, :736-737,
  :760-761`).
- **Per-call ABI re-serialization:** `:374` does `orjson.dumps(abi).decode()` every call,
  although `_abi_index` (`:254-285`) already computed that exact serialization for its
  blake2b digest at `:274`; `_AbiIndex` (`:234-246`) caches maps but not the JSON string.
- **Six dead bindings** (verified zero callers in package and tests): module bindings
  `:126-131` and their parsed-dict functions `:157-185` for `decode_many_direct`,
  `decode_many_flat`, `decode_many_hex`, `decode_many_raw`, `decode_one`,
  `decode_one_direct`. KEEP `_fast_decode_input`, `_fast_decode_many` (used at `:744`),
  `_fast_decode_to_arrow` (used by `services/analytics.py:224-226`) and the `_json` module
  bindings they need.
- `tests/test_decode.py` patches private internals 17 times — after this brief some of
  those patches may target consolidated seams; adjust only what breaks, do not rewrite the
  file.

## Contract

1. **One per-item seam.** A single internal helper (e.g. `_normalize_and_decode_one` —
   naming is yours) owning: input-length guard, hex `0x` strip, ABI→JSON hand-off, the
   gated fall-through rule, empty-mark assignment, and the exception tuple. All three entry
   points (`_decode_transaction_input_fast`, `_decode_transaction_input_python`,
   `decode_transaction_inputs_batch`) call it. The fall-through rule exists ONCE.
2. **`_AbiIndex` carries the JSON string.** Add the serialized ABI to the cached index so
   the fast path stops re-serializing per call. The digest computation stays as is.
3. **Delete the six dead bindings** (functions, wrappers, their `_json` module-level
   bindings if then unused). Grep-verified afterwards:
   `grep -rn "decode_many_direct\|decode_many_flat\|decode_many_hex\|decode_many_raw\|decode_one_direct\|\bdecode_one\b" aiochainscan/`
   finds nothing (the kept `decode_many`/`decode_input` names remain).
4. **Behaviour identical:** same outputs, same `PureAbiDecodeWarning` semantics (once per
   process, batches 50+), same tier-parity results, same batch whole-batch fallback
   semantics at `:765-767` (an exception mid-batch re-decodes on the floor — preserve
   exactly, including that already-decoded items get re-decoded).
5. **No hot-path regression:** run `uv run pytest tests/test_abi_pure.py -m benchmark`
   before and after; report both numbers. Tolerance: within noise (±5%) on the pure floor
   paths; the worktree lacks fastabi so Rust-path numbers will be absent — fine, state it.

## Edge cases

- `_declares_selector` gating must stay: without it, every non-declared selector would be
  pointlessly re-decoded on the floor (AGENTS.md documents this cost trap).
- The import-time stale-extension warning (`:94-102`) and `_MIN_FASTABI_VERSION` gate are
  untouched.
- `abi_pure.py` is deep and best-tested — do not touch it.
- Public names (`decode_transaction_input`, `decode_transaction_inputs_batch`, etc.) are
  unchanged.

## Files

**Change:** `aiochainscan/decode.py`, `tests/test_decode.py` (only patches that target
consolidated seams).
**Do not touch:** `aiochainscan/abi_pure.py`, `aiochainscan/fastabi/`,
`aiochainscan/services/analytics.py`, public API signatures.

## Out of scope

Rewriting `tests/test_decode.py` to public-path assertions wholesale (a follow-up can do
that once the seam settles); Arrow paths.

## Verification

```bash
uv run pytest tests/test_abi_pure.py -m benchmark > /tmp/bench_before.txt   # BEFORE changes
uv run pytest tests/test_decode.py tests/test_abi_pure.py tests/test_decode_fastabi.py -q
uv run pytest tests/ -q
make validate
uv run pytest tests/test_abi_pure.py -m benchmark > /tmp/bench_after.txt    # AFTER; compare
```

## Definition of done

- The fall-through rule (`_declares_selector` gate) appears exactly once in `decode.py`.
- The six dead names are gone (grep above empty).
- Benchmark numbers reported before/after; suites green; commit locally; no push, no PR.

## Decisions already made

- Consolidate in `decode.py` via one internal seam; no new public API — source review C6.
- Keep the batch fallback semantics verbatim even where they look wasteful.

## Open questions

- None blocking. If the seam helper's natural home turns out to be a small private class
  rather than a function, that is acceptable — keep it private.
