#!/usr/bin/env bash
set -euo pipefail

# provision-worktree.sh — make an already-created worktree able to run the real
# checks: credentials, project skills, .venv, optional Rust FFI.
#
# Usage: scripts/agent/provision-worktree.sh <worktree-dir>
#
# Env:
#   AIO_SKIP_SYNC=1      skip the per-worktree `uv sync`
#   AIO_BUILD_FASTABI=1  build the Rust extension (needs the Rust toolchain)
#
# Callers: scripts/agent/new-worktree.sh (which creates the worktree first) and
# scripts/xworker-bootstrap.sh (xworker creates its own under ~/.cache/xworker).
# Every step is skip-if-exists — a caller may have provisioned part of the tree.

WT_DIR="${1:-}"
[[ -n "$WT_DIR" && -d "$WT_DIR" ]] || {
	echo "Usage: $0 <worktree-dir>" >&2
	exit 2
}
WT_DIR="$(cd "$WT_DIR" && pwd)"

# The PRIMARY working copy: --git-common-dir points at the shared .git, whose
# parent is the main checkout (where the untracked .env lives).
GIT_COMMON_DIR="$(cd "$(git -C "$WT_DIR" rev-parse --git-common-dir)" && pwd)"
MAIN_ROOT="$(dirname "$GIT_COMMON_DIR")"

cd "$WT_DIR"


# Untracked root config (.env) lives only in the primary checkout. Symlink
# rather than copy: a copy is a snapshot, so a key added to the root .env after
# this worktree was created never reaches it (silently, as a missing-key error
# in a session that "has" a .env). ConfigurationManager reads the file by path,
# so a symlink is indistinguishable to it. It stays gitignored either way.
# Machine-level credentials belong in ~/.aiochainscan/.env instead — the config
# manager reads that for every cwd, so no worktree plumbing is involved at all.
if [[ -L .env ]]; then
	: # already linked by an earlier caller
elif [[ -f "$MAIN_ROOT/.env" ]]; then
	echo "==> Linking .env from primary checkout..."
	ln -sfn "$MAIN_ROOT/.env" .env
elif [[ -f "$HOME/.aiochainscan/.env" ]]; then
	echo "==> No root .env; machine-level ~/.aiochainscan/.env will be used."
else
	echo "WARN: no $MAIN_ROOT/.env and no ~/.aiochainscan/.env — live-API calls will fail without keys." >&2
fi

# Project skills are a MIX of tracked dirs and untracked symlinks into
# ~/agent-skills; only the tracked half survives `git worktree add`. Recreate
# the symlinks (never the tracked dirs) so the skill catalog matches the
# primary checkout.
if [[ -d "$MAIN_ROOT/.claude/skills" ]]; then
	mkdir -p .claude/skills
	linked=0
	for src in "$MAIN_ROOT"/.claude/skills/*; do
		[[ -L "$src" ]] || continue
		name="$(basename "$src")"
		[[ -e ".claude/skills/$name" || -L ".claude/skills/$name" ]] && continue
		ln -s "$(readlink "$src")" ".claude/skills/$name" && linked=$((linked + 1))
	done
	if ((linked > 0)); then
		echo "==> Mirrored $linked symlinked project skill(s) from the primary checkout."
	fi
fi

if [[ "${AIO_SKIP_SYNC:-0}" == "1" ]]; then
	echo "==> Skipping uv sync (AIO_SKIP_SYNC=1). Run 'uv sync --extra dev --frozen' before checking/committing."
else
	# Fresh worktrees have no project .venv. Sync up front so pytest, mypy,
	# ruff and pre-commit work immediately (same extras as the CI lint job).
	echo "==> uv sync --extra dev --frozen (per-worktree .venv)..."
	uv sync --extra dev --frozen
fi

if [[ "${AIO_BUILD_FASTABI:-0}" == "1" ]]; then
	echo "==> Building Rust FFI (maturin develop --release; needs the Rust toolchain)..."
	if ! (cd aiochainscan/fastabi && uv run --with maturin maturin develop --release); then
		echo "WARN: fastabi build failed — decode() will fall back to the pure-Python path." >&2
	fi
else
	echo "==> Skipping fastabi build (AIO_BUILD_FASTABI=1 to build; decode() falls back to Python)."
fi

# pre-commit hooks live in the shared .git/hooks (git-common-dir), so they are
# already active in this worktree — no reinstall needed.
