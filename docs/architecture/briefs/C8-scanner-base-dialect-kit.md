---
kind: deepening-brief
id: C8
slug: scanner-base-dialect-kit
source: ../2026-09-03-review.md
status: done
base: 8e9bf4a
---

# Scanner base defaults: instance root in `__str__` / `_error_context`

> **Done** — lane commit `c6f7cd0`, merged to `main` (2026-09-03, no-ff). Gate: PASS-WITH-FINDINGS; the MEDIUM (base_url identity in the V1 custom-URL branch) was closed by the orchestrator: the parent stores `base_url` verbatim and the child assigns the same parameter.

## Repo orientation

aiochainscan is an async Python wrapper for blockchain-explorer APIs. `aiochainscan/scanners/base.py`
defines the `Scanner` base class; three concrete scanners each override `__str__`/`__repr__`
and `_error_context` to name their instance host — six overrides restating one payload, and
two of the three `_error_context` overrides produce messages WORSE than the default they
replace (they drop the method name). Tests: `uv run pytest tests/ -q`; gate
`make validate`.

## Task

Give the base class one instance-root concept feeding default `__str__`/`__repr__` and
`_error_context`, and delete the six subclass overrides — messages become at least as
informative as today's in every case.

## Current state (verified on `base`)

- `__str__`/`__repr__` overridden in `blockscout_v1.py:246-258`,
  `blockscout_v2.py:658-668`, `nodereal.py:1235-1245`; base default at `base.py:609-619`.
  All six methods' real content is "scanner name/version + the instance root" (host or base
  URL).
- `_error_context` default at `base.py:464-466` includes the method name; the overrides at
  `blockscout_v1.py:186-187` and `blockscout_v2.py:571-572` IGNORE the `method` parameter
  (message loses the method name); `nodereal.py:1011-1012` drops the host instead.
- Each scanner already holds its root as an attribute (`instance_domain` / `base_url` /
  `rpc_base_url` — check each `__init__`).

## Contract

1. **Base owns the root.** `Scanner` gains a way to expose its instance root — e.g. a
   `_instance_root: str | None` attribute (default `None`) set by each concrete scanner's
   `__init__` from the attribute it already computes. No new public API (leading
   underscore).
2. **Base defaults use it.** Base `__str__`/`__repr__` append the root when present;
   base `_error_context` message includes scanner name, version, root (when present) AND
   the method name — a superset of every current message's information.
3. **Delete all six overrides** plus the three `_error_context` overrides. The three
   scanners keep only the `__init__` line that sets the root.
4. **Messages ≥ today's.** For every scanner, the new default message contains at least
   every fact today's override contained (method name restored where it was being dropped
   is an improvement, not a regression — note it in the commit message).

## Edge cases

- Tests may pin current `str(scanner)` or error-message text — update such assertions only
  to the new (equally or more informative) text; grep first
  (`grep -rn "str(scanner\|__str__\|_error_context" tests/`).
- BlockScout V1 and V2 roots are instance domains; NodeReal's is its base URL — the root
  string each scanner sets must be the same value its old override printed.
- Keep `_error_context`'s signature unchanged (it receives the method).

## Files

**Change:** `aiochainscan/scanners/base.py`, `aiochainscan/scanners/blockscout_v1.py`,
`aiochainscan/scanners/blockscout_v2.py`, `aiochainscan/scanners/nodereal.py` (override
deletions + root assignment), tests that pin the affected strings (assertions only).
**Do not touch:** `aiochainscan/scanners/etherscan_v2.py` (no instance root, default
already fine), `aiochainscan/core/`, `aiochainscan/services/`, any transport/behaviour
code.

## Out of scope

The shared JSON-RPC send+translate helper (originally sketched in review C8) — explicitly
dropped: unproven unification, and `nodereal.py` is being changed by candidate C4's brief
in parallel. Do not start it.

## Verification

```bash
uv run pytest tests/test_blockscout_v1_ethrpc.py tests/test_nodereal.py tests/test_scanner_fetch_page.py -q
uv run pytest tests/ -q
make validate
```

Add one test: for each of the three scanners, `str(scanner)` contains name, version and
root; an unexpected error's context message contains the method name AND the root (the two
facts today's overrides each drop one of).

## Definition of done

- `grep -n "def __str__\|def __repr__\|def _error_context" aiochainscan/scanners/*.py`
  finds hits ONLY in `base.py`.
- All verification green; commit locally; no push, no PR.

## Decisions already made

- Root is a private attribute consumed by base defaults — not a property, not public —
  source review C8 (downscoped to the base-defaults half).
- JSON-RPC kit explicitly out of scope.

## Open questions

- If a scanner's old `__repr__` printed something beyond name/version/root (check each),
  preserve that fact in its root string or keep that one override — report which.
