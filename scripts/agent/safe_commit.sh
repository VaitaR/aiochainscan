#!/usr/bin/env bash
# EXIT_CODES:
#   0  committed
#   1  usage error, or the index lock was held by a live git process
#   2  the requested staging population is not representable (a glob in the
#       legacy two-argument form); nothing staged, nothing committed
# END EXIT_CODES
# Safe git add + commit with index.lock retry — worktree-aware.
#
# Why: `git commit` holds the index lock for the whole pre-commit run, and this
# repo's `validate-airflow-dags` hook runs pytest (always_run: true, ~20-30s). A
# second `git add`/`git commit` during that window fails with
# "index.lock: File exists". A *crashed* prior git also leaves a stale lock.
#
# This wrapper waits out a live lock and removes it only once it is provably
# stale (no git process running) — it never clobbers a lock a live commit holds.
#
# The lock path is resolved with `git rev-parse --git-path index.lock`, so it is
# correct in BOTH a normal checkout (.git/index.lock) and a linked worktree
# (.git/worktrees/<name>/index.lock). A literal ".git/index.lock" is WRONG in a
# worktree, where ".git" is a file, not a directory — the original bug this fixes.
#
# Usage (drop-in for `git add FILES && git commit -m MSG`):
#   ./scripts/agent/safe_commit.sh -m "commit message" <path>...   # exact
#   ./scripts/agent/safe_commit.sh "path/to/file1 path/to/file2" "commit message"
#   ./scripts/agent/safe_commit.sh "." "commit message"   # stage all
#
# Staging population: the `-m` form takes each path as its own argument, splits
# nothing, and stages under `git --literal-pathspecs`, so a path containing
# whitespace, a bracket or an asterisk means exactly itself (the legacy form
# cannot express any of those). Pathspec magic (`:(exclude)…`) is therefore NOT
# available here by design — call `git add` directly if you want it.
#
# The two-argument form still splits its single path string
# on whitespace — that is its interface — but with pathname expansion DISABLED:
# a glob is refused with exit 2 instead of being expanded by this script's shell
# into whatever happens to match right now. Neither silent reading is safe —
# shell and git-pathspec glob semantics differ (git's `*` crosses `/`) — and
# staging a superset silently combines unrelated work. Three or more positional
# arguments are a usage error, because the message would be ambiguous: the old
# script read it as "$2" and silently dropped the rest, committing a path as the
# commit message.
#
# Exit status:
#   0  committed
#   1  usage error, or the index lock was held by a live git process
#   2  the requested staging population is not representable (a glob in the
#      two-argument form) — nothing was staged and nothing was committed
#
# Env:
#   SAFE_COMMIT_LOCK_WAIT      seconds to wait for a live lock before treating it
#                              as stale (default 30; keep > the pre-commit run).
#   SAFE_COMMIT_ASSUME_STALE=1 skip the live-git-process guard and treat a
#                              timed-out lock as stale (tests / forced recovery).
#   SAFE_COMMIT_NO_VERIFY=1    commit with --no-verify. Escape hatch for shared
#                              checkouts: this repo's pre-commit mypy hook checks
#                              the WHOLE package, so another agent's in-flight
#                              WIP blocks unrelated commits. Run the gates on
#                              YOUR files yourself first — do not use this to
#                              skip validation of your own change.

set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo '.')"

PATHS=()

if [ "${1:-}" = "-m" ]; then
  # Exact form: the message is named, every remaining argument is one path. No
  # splitting anywhere, so a single path containing whitespace — which the
  # legacy form cannot express at all — works here.
  MSG="${2:-}"
  shift 2 2>/dev/null || shift "$#"
  PATHS=("$@")
elif [ "$#" -gt 2 ]; then
  # Ambiguous: which of these is the message? The old script answered "$2" and
  # silently dropped the rest, committing a PATH as the commit message.
  echo "ERROR: $# arguments given — the message would be ambiguous." >&2
  echo "  Exact form:  safe_commit.sh -m <commit message> <path>..." >&2
  echo "  Legacy form: safe_commit.sh \"<path> <path>\" <commit message>" >&2
  exit 1
else
  FILES="${1:-}"
  MSG="${2:-}"

  if [ -z "$FILES" ] || [ -z "$MSG" ]; then
    echo "Usage: safe_commit.sh <path>... <commit message>" >&2
    echo "   or: safe_commit.sh \"<path> <path>\" <commit message>" >&2
    exit 1
  fi

  # Split on whitespace (the legacy interface) but with pathname expansion off,
  # so this script never turns a glob into a file list of its own choosing.
  set -f
  # shellcheck disable=SC2206  # deliberate word split of the legacy one-string form
  PATHS=($FILES)
  set +f

  for _p in "${PATHS[@]}"; do
    case "$_p" in
      *'*'*|*'?'*|*'['*)
        echo "ERROR: glob '$_p' cannot be staged exactly — pass each path as its own argument:" >&2
        echo "  safe_commit.sh -m \"$MSG\" <path> <path> ..." >&2
        echo "  (expanding it here would stage whatever matches now, which is not what you named)" >&2
        exit 2 ;;
    esac
  done
fi

if [ "${#PATHS[@]}" -eq 0 ] || [ -z "$MSG" ]; then
  echo "Usage: safe_commit.sh <path>... <commit message>" >&2
  exit 1
fi

LOCK="$(git rev-parse --git-path index.lock)"
WAIT_MAX="${SAFE_COMMIT_LOCK_WAIT:-30}"

# Wait out a live lock; remove it only once it is provably stale. Returns 1 if a
# live git process still holds the lock after the wait (caller should give up).
_wait_for_index() {
  local waited=0
  while [ -e "$LOCK" ] && [ "$waited" -lt "$WAIT_MAX" ]; do
    sleep 1
    waited=$((waited + 1))
    printf "\r  [index.lock] waiting %ds (%s)...   " "$waited" "$LOCK"
  done
  [ "$waited" -gt 0 ] && echo ""
  [ -e "$LOCK" ] || return 0

  # Still locked after the wait. A live git process means a legitimate commit is
  # in progress (e.g. the 20-30s pre-commit pytest) — do NOT clobber it.
  if [ "${SAFE_COMMIT_ASSUME_STALE:-0}" != "1" ] && pgrep -x git >/dev/null 2>&1; then
    echo "  index.lock held and a git process is live — not removing. Re-run shortly." >&2
    return 1
  fi
  echo "  index.lock stale after ${waited}s (no live git) — removing $LOCK"
  rm -f "$LOCK"
}

_stage() {
  # `--literal-pathspecs` is the load-bearing flag, not `--`: `--` only stops
  # OPTION parsing, while git still reads each argument as a pathspec — so a
  # file literally named `[ab].py` staged itself AND `a.py`/`b.py` (measured),
  # and `:(exclude)…` would have selected thousands of paths. Literal mode makes
  # every argument mean exactly the path it spells; a caller who wants pathspec
  # magic should call `git add` directly. Quoted expansion keeps the population
  # exactly what was resolved above.
  git --literal-pathspecs add -- "${PATHS[@]}"
}

if ! _wait_for_index; then
  exit 1
fi

# Stage; if a lock reappeared between the wait and `git add` (race with a
# background process), wait once more and retry a single time.
if ! _stage 2>/dev/null; then
  sleep 2
  if ! _wait_for_index; then
    exit 1
  fi
  _stage
fi

git commit ${SAFE_COMMIT_NO_VERIFY:+--no-verify} -m "$MSG"
