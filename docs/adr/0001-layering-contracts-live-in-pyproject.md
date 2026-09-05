---
status: accepted
date: 2026-09-05
---

# 0001 — The layering contracts live in `pyproject.toml`

## Decision

`[tool.importlinter]` in `pyproject.toml` is the single import-linter configuration.
The root `.importlinter` file is deleted, not commented out, and no invocation passes
`--config`: import-linter's own lookup order (`setup.cfg`, `.importlinter`,
`pyproject.toml`, stopping at the first file with a config section) must have exactly one
answer in this repo.

`services` may not import `core`, `network`, `scanners` or `adapters`; `adapters` may not
import `services` or `domain`; `domain` and `ports` may not import anything above them.
That is the rule `AGENTS.md` states as "only downward, never upward", and it is now the
rule that runs.

## Why `services` does not import `core`

Two names crossed that boundary. Both moved below every layer rather than being absolved
by an ignore list:

- `JSONDict` / `JSONList` → `aiochainscan/types.py`. A parsed-JSON alias belongs to no
  layer; the root is where this repo already keeps such names (`constants.py`,
  `exceptions.py`).
- `coerce_response_items` → `aiochainscan/domain/response.py`. Its two callers are
  `scanners.base` and `services.pagination`, and `services` may not import `scanners`, so
  the shared home has to sit under both. `domain` is the lowest layer and pure.

## Consequences

A missing config now fails the gate. `make import-lint`, `preflight.sh` and
`validate_fast.sh` previously skipped the check with a green line when `.importlinter` was
absent — a guard that would have reported success forever the moment its config moved.

Each contract is proven non-vacuous by injecting the forbidden import and observing the
break; re-run that probe when adding a contract, since a contract sourced on a
module that does not exist also reports `KEPT`.
