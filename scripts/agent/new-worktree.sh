#!/usr/bin/env bash
set -euo pipefail

# new-worktree.sh — bootstrap an isolated git worktree for one coding-agent session.
#
# One agent == one worktree == one branch. main stays checked out only in the
# primary clone; agents never switch branches or stash to share a directory.
# Separate worktrees each have their own index, so this also eliminates the
# cross-session `.git/index.lock: File exists` collisions.
#
# Usage:
#   scripts/agent/new-worktree.sh <slug> [branch-type] [base-ref]
#     slug         short kebab-case task name; used for the branch and dir name
#     branch-type  feat | fix | chore | docs | arch | refactor   (default: feat)
#     base-ref     ref to branch from                 (default: origin/main)
#
# Env:
#   AIO_WORKTREE_DIR     parent dir for worktrees  (default: <repo>/.claude/worktrees)
#   AIO_SKIP_SYNC=1      skip the uv sync (faster; throwaway sessions only —
#                        pytest/pre-commit/mypy need the .venv, so you MUST
#                        sync before running checks or committing)
#   AIO_BUILD_FASTABI=1  also build the Rust FFI (maturin develop --release) —
#                        only needed for decode-path work; skipped otherwise
#
# When done (after the PR merges):
#   scripts/agent/rm-worktree.sh <slug> --yes

usage() {
	# Print the contiguous header-comment block (skips shebang + set line).
	awk 'NR<=3 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
}

SLUG="${1:-}"
if [[ -z "$SLUG" || "$SLUG" == "-h" || "$SLUG" == "--help" ]]; then
	usage
	exit 2
fi
TYPE="${2:-feat}"
BASE="${3:-origin/main}"
BRANCH="$TYPE/$SLUG"

# Resolve the PRIMARY working copy: --git-common-dir points at the shared .git,
# whose parent is the main checkout (where the untracked .env lives).
GIT_COMMON_DIR="$(cd "$(git rev-parse --git-common-dir)" && pwd)"
MAIN_ROOT="$(dirname "$GIT_COMMON_DIR")"

WT_PARENT="${AIO_WORKTREE_DIR:-$MAIN_ROOT/.claude/worktrees}"
WT_DIR="$WT_PARENT/$SLUG"

if [[ -e "$WT_DIR" ]]; then
	echo "ERROR: $WT_DIR already exists. Pick another slug or remove it first." >&2
	exit 1
fi

echo "==> Fetching origin (prune)..."
git -C "$MAIN_ROOT" fetch origin --prune

echo "==> Creating worktree"
echo "      dir:    $WT_DIR"
echo "      branch: $BRANCH"
echo "      base:   $BASE"
mkdir -p "$WT_PARENT"
git -C "$MAIN_ROOT" worktree add -b "$BRANCH" "$WT_DIR" "$BASE"

cd "$WT_DIR"

# Untracked root config (.env) lives only in the primary checkout — copy it so
# ETHERSCAN_KEY and any other runtime config work in this session too. It is
# gitignored, so it stays untracked in the worktree as well.
if [[ -f "$MAIN_ROOT/.env" ]]; then
	echo "==> Copying .env from primary checkout..."
	cp "$MAIN_ROOT/.env" .env
else
	echo "WARN: $MAIN_ROOT/.env not found — live-API examples may fail without ETHERSCAN_KEY." >&2
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

echo ""
echo "Worktree ready."
echo "  cd $WT_DIR"
echo ""
echo "Validate before claiming done:  make validate    (scripts/agent/validate_fast.sh)"
echo "Commit:                         make commit MSG=\"...\" PATHS=\"file1 file2\""
echo "Teardown after merge:           scripts/agent/rm-worktree.sh \"$SLUG\" --yes"
