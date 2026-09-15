#!/usr/bin/env bash
set -euo pipefail

# xworker-bootstrap.sh — the name xworker.sh looks for after `git worktree add`.
# Thin on purpose: scripts/agent/provision-worktree.sh stays the single source of
# truth for what a worktree needs, shared with new-worktree.sh.

exec "$(dirname "$0")/agent/provision-worktree.sh" "$@"
