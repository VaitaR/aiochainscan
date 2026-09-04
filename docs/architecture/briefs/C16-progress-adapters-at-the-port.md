---
kind: deepening-brief
id: C16
slug: progress-adapters-at-the-port
source: ../2026-09-05-review.md
status: accepted
base: c9943a2
---

# Put the progress-port adapters where the port's adapters live

## Repo orientation

`aiochainscan` is an async Python wrapper over blockchain-explorer APIs, built on a
hexagonal layering that `CONTEXT.md` defines:

- **Port** — an interface in `aiochainscan/ports/` describing a capability the domain
  needs. Surviving ports: `cache`, `progress`, `rate_limiter`.
- **Adapter** — "concrete implementation of a port in `aiochainscan/adapters/`".

The layering is enforced by `import-linter` contracts in `pyproject.toml:147-200`, run
as part of `make validate` (ruff, format check, import-linter, `mypy --strict`, pytest).
Run the contracts alone with `uv run lint-imports`.

## Task

Move the six `ProgressCallback` adapters from `aiochainscan/utils/progress_helpers.py`
to `aiochainscan/adapters/progress.py`, keep the documented import path working as a
re-export, extend the `import-linter` contracts to cover the new module, and add the
test file these six factories currently do not have.

## Why this is not cosmetic (read before starting)

`aiochainscan/ports/progress.py:8-65` declares the `ProgressCallback` port. Its six
concrete satisfiers live in `aiochainscan/utils/progress_helpers.py`:
`console_progress` (`:12`), `tqdm_progress` (`:65`), `rich_progress` (`:130`),
`silent_progress` (`:191`), `logging_progress` (`:218`), `callback_with_interval`
(`:271`). `aiochainscan/adapters/__init__.py:1-11` exports three adapters, none of them
for progress — so a reader who follows the project's own definition to `adapters/`
concludes the port has none.

The consequence is structural rather than behavioural: `utils` is named by no
`import-linter` contract, so the rule that guards every other adapter — "Adapters do not
import services" and "…do not import domain" (`pyproject.toml:161-169`) — does not apply
to these six. Nothing is broken today (`progress_helpers.py:1-9` imports only
`sys`, `typing`, and the port itself under `TYPE_CHECKING`; `tqdm` and `rich` are
imported lazily inside their factories). The seam is simply somewhere the contracts do
not look, and there is no test file for it.

## Contract

1. **New module `aiochainscan/adapters/progress.py`** holding all six factories,
   unchanged in behaviour and in signature. It may import `aiochainscan.ports.progress`
   (under `TYPE_CHECKING`, as today) and nothing from `services`, `domain`, `core` or
   `network`.
2. **`aiochainscan/utils/progress_helpers.py` becomes a re-export** of those six names.
   The path is documented in `AGENTS.md`
   (`from aiochainscan.utils.progress_helpers import console_progress`) and this is a
   1.0.0 library, so it must keep working with identical behaviour. Both of these must
   hold after the move, for every one of the six names:

   ```python
   from aiochainscan.adapters.progress import console_progress          # new path
   from aiochainscan.utils.progress_helpers import console_progress     # documented path
   ```

   and the two must be **the same object** (`is`), not two definitions.
3. **Export the six from `aiochainscan/adapters/__init__.py`**, alongside the three
   adapters already there, so the package's adapter inventory is complete.
4. **Extend the `import-linter` contracts** so the new module is covered by the same
   forbidden-import rules as its neighbours. Adding a module under `adapters` is enough
   if the existing contracts are declared on the `aiochainscan.adapters` package — check
   `pyproject.toml:161-169` and confirm; if they are declared per-module, add the new
   one explicitly. Say in your report which case you found.
5. **Update `CONTEXT.md`**'s **Adapter** entry so the surviving-adapter list names the
   progress adapters. One line; do not restructure the glossary.

## Edge cases

- `tqdm_progress` (`:65`) and `rich_progress` (`:130`) import optional third-party
  packages **inside** the factory body. Keep that lazy import exactly where it is —
  hoisting it to module scope would make `import aiochainscan.adapters` fail for anyone
  without `tqdm`/`rich` installed.
- `progress_helpers.py` has **no `__all__`**. The re-export module needs one, or `ruff`
  will flag the unused imports (`F401`). Use an explicit `__all__` rather than
  `# noqa: F401` — the project's rule is that a `noqa` needs a documented reason, and
  here there is a cleaner option.
- `aiochainscan/utils/__init__.py` re-exports only `default_range`. Do not change it and
  do not add the progress names to it — that would create a third import path.
- Check whether any name is re-exported from `aiochainscan/__init__.py`; if so, that
  path must keep resolving to the same object too.
- `examples/progress_callback_demo.py` imports from the documented path. It must keep
  working; do not rewrite it to the new path (that would defeat the compatibility test).

## Files

**Change:** `aiochainscan/adapters/progress.py` (new),
`aiochainscan/utils/progress_helpers.py` (becomes a re-export),
`aiochainscan/adapters/__init__.py`, `pyproject.toml` (import-linter contracts, only if
needed — see Contract item 4), `CONTEXT.md` (one line),
`tests/test_progress_adapters.py` (new).

**Delete:** nothing. The old module stays as a re-export.

**Do not touch:** `aiochainscan/ports/`, `aiochainscan/utils/date.py`,
`aiochainscan/utils/__init__.py`, `examples/`, any other adapter,
`aiochainscan/core/`, `aiochainscan/services/`.

## Out of scope

- **`aiochainscan/utils/date.py`.** `default_range` (`:10`) has no caller inside the
  package, exercised only by `tests/test_utils_date.py`. That is a public-API question
  (deprecate or keep), not a seam-location one, and it is deliberately not part of this
  brief.
- **`adapters/simple_rate_limiter.py`.** Exported but never constructed in production
  (`network.py:295` always builds `AioLimiterAdapter`). It is still the second adapter
  that makes the `RateLimiter` seam real. Leave it.
- **Adding an adapter for a port that has none**, or removing a port.
- **Changing any factory's behaviour, signature or defaults.**

## Verification

```bash
uv run lint-imports
uv run pytest tests/test_progress_adapters.py -q
make validate
```

Add `tests/test_progress_adapters.py`. There is no existing test file for these six
factories, so this is also the first coverage they get. It must assert:

1. **Path identity** — for each of the six names, the object imported from
   `aiochainscan.adapters.progress` `is` the object imported from
   `aiochainscan.utils.progress_helpers`. Iterate the six names from a list in the test;
   assert the list has length 6 so the loop cannot silently shrink to zero and pass
   while asserting nothing.
2. **Behaviour** — `console_progress` writes to a supplied file-like object (pass an
   `io.StringIO`, assert non-empty output), `silent_progress` writes nothing, and
   `logging_progress` emits on the named logger (`caplog`). These are `async` callbacks:
   check `ports/progress.py:8-65` for the call signature and await them.
3. **Optional-dependency safety** — importing `aiochainscan.adapters` succeeds without
   `tqdm` or `rich` being used; calling `tqdm_progress()` when the package is absent is
   allowed to raise, but the module import is not.

Prove the identity assertion is non-vacuous: point the re-export at a fresh local
definition once, show the test failing, restore it, show it passing. Paste both runs.

Report command output, not a summary of it.

## Definition of done

- `aiochainscan/adapters/progress.py` holds the six factories; `progress_helpers.py`
  defines none of them and re-exports all six with an explicit `__all__`.
- Both import paths resolve to the same objects, proven by a test that fails when they
  do not.
- `uv run lint-imports` passes and the new module is inside the contracts' scope; your
  report states which of the two cases in Contract item 4 applied.
- `CONTEXT.md`'s Adapter entry names the progress adapters.
- `make validate` passes in full.
- Commit locally on a branch. Do not push, do not open a PR.

## Decisions already made

- The documented `utils.progress_helpers` path is preserved, not deprecated — this is a
  1.0.0 library (source review, C16).
- The move is navigational plus contract coverage; no behaviour changes.

## Open questions

- If moving the module makes an `import-linter` contract fail for a reason you did not
  expect, that is a finding worth more than the move: **stop, report the contract and
  the cycle, and do not weaken the contract to get green.**

"I could not do X" is a valid answer. An unmet item must be reported as unmet, not
interpreted away.
