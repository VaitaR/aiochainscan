---
kind: deepening-brief
id: C5
slug: merge-pagination-guarantee
source: ../2026-09-03-review.md
status: done
base: 8e9bf4a
---

# Merge the pagination-guarantee module into the engine

> **Done** — lane commit `64b3480` on `xw/c5-merge-pagination-guarantee`, merged to `main`
> (2026-09-03, no-ff). Gate: PASS-WITH-FINDINGS — MEDIUM was an evidence-pack note (the test
> import change was invisible in the diff, closed by the green suites), LOW ×2 cosmetic.

## Repo orientation

aiochainscan is an async Python wrapper for blockchain-explorer APIs. The **Pagination
engine** (`CONTEXT.md`) is `aiochainscan/services/pagination.py`; its completeness half
lives in `aiochainscan/services/pagination_guarantee.py` (overflow detection, adaptive range
splitting, the two terminal errors) — but the two modules import each other in a cycle,
papered over with function-body local imports. Tests: `uv run pytest tests/ -q`; gate
`make validate`.

## Task

Merge `pagination_guarantee.py` into `pagination.py` as one module and delete the file,
without changing a single behaviour.

## Current state (verified on `base`)

- `pagination.py:54-60` imports everything from `pagination_guarantee` and re-exports it
  (`__all__` at `:64-80`).
- `pagination_guarantee.py:231` and `:291` import `iter_pages` and the private
  `_notify_progress` back from `pagination` INSIDE function bodies (cycle workaround).
- The only importer of `pagination_guarantee` outside the pair is
  `tests/test_normalized_streaming.py` (verify with
  `grep -rn "pagination_guarantee" aiochainscan/ tests/`).
- CONTEXT.md already names `pagination.py` as the home of the Pagination engine — this
  merge aligns code with the glossary.

## Contract

1. **Move, don't edit.** The guarantee machinery (`split_window` recursion `:141-166`,
   `_Overflow`/`_fetch_window` `:176-246`, `iter_pages_complete` `:249-349`, the two error
   constructors `:317-334`, helpers) moves into `pagination.py` VERBATIM — no renames, no
   logic edits, no "improvements". Internal-only names keep their leading underscores.
2. **Public names identical.** `services.pagination`'s `__all__` and every importable name
   stay exactly as callers see them today (the re-exported guarantee names just live in the
   one module now). Zero caller changes in `aiochainscan/`.
3. **Cycle gone.** The function-body local imports (`:231`, `:291`) become direct module-level
   references; no local imports remain.
4. **Delete `pagination_guarantee.py`.** Update the ONE test import in
   `tests/test_normalized_streaming.py` to import from `services.pagination`. Grep proves no
   other importer: `grep -rn "pagination_guarantee" aiochainscan/ tests/` must be empty
   afterwards.
5. **One docstring tells the whole story.** Merge the two module docstrings so the combined
   module documents loop + completeness as one engine (keep the load-bearing measured-cap
   notes verbatim — they record live-verified provider behaviour).

## Edge cases

- Import order matters if the guarantee code references names defined later in
  `pagination.py` — place the moved block after `iter_pages`/`_notify_progress` definitions,
  or keep whatever placement keeps every name resolvable at call time.
- `services/pagination.py` is imported by `core/client.py`, `core/streaming.py`, mixins —
  their imports must keep working untouched.
- Do not merge the TEST files; `tests/test_pagination_guarantee.py` keeps its name and
  assertions, only its imports change if they referenced the deleted module path.

## Files

**Change:** `aiochainscan/services/pagination.py`, `aiochainscan/services/pagination_guarantee.py`
(delete), `tests/test_normalized_streaming.py` (one import), `tests/test_pagination_guarantee.py`
(import only, if needed).
**Do not touch:** any behaviour inside the moved code, `aiochainscan/core/`,
`aiochainscan/scanners/`, `aiochainscan/services/analytics.py`, `aiochainscan/mcp/`.

## Out of scope

Everything else — this is a pure module merge.

## Verification

```bash
uv run pytest tests/test_pagination_engine.py tests/test_pagination_guarantee.py tests/test_normalized_streaming.py -q
uv run pytest tests/ -q
make validate
grep -rn "pagination_guarantee" aiochainscan/ tests/   # must print nothing
```

## Definition of done

- `aiochainscan/services/pagination_guarantee.py` does not exist.
- The grep above is empty; all suites green; commit locally; no push, no PR.

## Decisions already made

- Merge (not a shared-helper inversion) — the module has zero external importers; source
  review C5.
- Verbatim move; blame churn is the accepted cost.

## Open questions

- None blocking. If the combined file feels too large to navigate, you may add section
  comment banners — nothing more.
