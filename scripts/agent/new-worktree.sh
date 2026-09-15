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

"$(dirname "$0")/provision-worktree.sh" "$WT_DIR"

echo ""
echo "Worktree ready."
echo "  cd $WT_DIR"
echo ""
echo "Validate before claiming done:  make validate    (scripts/agent/validate_fast.sh)"
echo "Commit:                         make commit MSG=\"...\" PATHS=\"file1 file2\""
echo "Teardown after merge:           scripts/agent/rm-worktree.sh \"$SLUG\" --yes"
