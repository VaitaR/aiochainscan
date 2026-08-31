# Claude Code — pointer file

@AGENTS.md

**AGENTS.md is imported above — follow it in full; do not re-read it.** It is the canonical project guide (public API, warnings, patterns, testing). This file adds only the Claude-Code-specific runtime integrations that other agents don't have. It does not override anything in AGENTS.md.

## Multi-agent worktrees

**One session == one worktree == one branch.** Never switch branches or stash to share a directory with another session.

- Bootstrap: `make wt-new SLUG=<task-slug> [TYPE=feat|fix|chore|docs|arch|refactor] [BASE=origin/main]` → creates `.claude/worktrees/<slug>/` on branch `<type>/<slug>`, copies `.env`, runs `uv sync --extra dev --frozen`.
- List: `make wt-ls` · Teardown (only clean + merged): `make wt-rm SLUG=<slug> ARGS="--yes"`.
- `AIO_SKIP_SYNC=1` skips the sync (throwaway sessions only); `AIO_BUILD_FASTABI=1` also builds the Rust FFI.

## Edit/Write hook (auto-applied)

`.claude/settings.json` wires a PostToolUse hook on `Edit|Write`: `scripts/agent/ruff_format_hook.py` auto-runs `ruff format` on edited `*.py` files (best-effort, never blocks). You still must pass `ruff format --check` in `make validate` — the hook formats the file you edited, not the whole repo.

## Path-scoped rules (auto-loaded)

`.claude/rules/*.md` attach automatically when you touch matching paths — do not re-read them manually. Currently: `fastabi.md` (Rust FFI invariants for `aiochainscan/fastabi/**` and `aiochainscan/decode.py`).

## Waiting on long-running things

Do not stream `gh run watch` — it burns tokens. Use the self-terminating poller `./scripts/agent/ci_watch.sh` (exit status is the verdict). Note: all workflows are currently disabled (Actions-minutes budget), so CI watch reports NO VERDICT until re-enabled; use `make ci-local` as the CI gate meanwhile.

## Permissions

`.claude/settings.json` allow-lists the agent scripts, `make`, read-only git/gh, and `uv run` quality commands; `.env` is denied for both Read and Edit. If a routine command keeps prompting, add it there instead of approving it every session.
