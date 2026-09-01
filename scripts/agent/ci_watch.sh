#!/usr/bin/env bash
# EXIT_CODES:
#   0  success — the run concluded success
#   1  CI failed — the run concluded failure
#   2  watch timeout — the wait budget elapsed before a terminal state
#   3  no run ever registered — nothing was watched for this ref; NOT a pass
#   4  NO VERDICT — the watcher could not read state (gh missing, CI disabled,
#      bad usage, unresolvable ref); ask again, never read as a red build
# END EXIT_CODES
# ci_watch.sh — wait for the GitHub Actions run of a ref to reach a terminal
# state, with bounded polling and compact output. Exit status IS the verdict.
#
# NOTE: all workflows in this repo are currently DISABLED (Actions-minutes
# budget). Until they are re-enabled this script exits 4 with a hint:
#   gh workflow enable ci.yml --repo VaitaR/aiochainscan   # (and the others)
#
# Usage:
#   ./scripts/agent/ci_watch.sh                    # latest run on current branch
#   ./scripts/agent/ci_watch.sh --branch main      # latest on a branch
#   ./scripts/agent/ci_watch.sh --pr 12            # latest on PR 12's head branch
#   ./scripts/agent/ci_watch.sh --workflow ci.yml  # filter by workflow file/name
#
# Env:
#   AIO_CI_WAIT_BUDGET     total seconds to wait (default 900)
#   AIO_CI_POLL_INTERVAL   seconds between polls (default 30)
#   AIO_CI_APPEAR_TIMEOUT  seconds to wait for a just-pushed run to register (default 90)

set -uo pipefail

BRANCH="" WORKFLOW="" PR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --workflow) WORKFLOW="${2:-}"; shift 2 ;;
    --pr) PR="${2:-}"; shift 2 ;;
    -h|--help) sed -n 's/^# \{0,1\}//p' "${0}"; exit 0 ;;
    *) echo "ERROR: unknown flag $1" >&2; exit 4 ;;
  esac
done

command -v gh >/dev/null 2>&1 || { echo "NO VERDICT: gh not installed" >&2; exit 4; }

if [ -n "$PR" ]; then
  BRANCH=$(gh pr view "$PR" --json headRefName -q .headRefName 2>/dev/null) \
    || { echo "NO VERDICT: cannot resolve PR #$PR head branch" >&2; exit 4; }
fi
if [ -z "$BRANCH" ]; then
  BRANCH=$(git branch --show-current 2>/dev/null)
  [ -n "$BRANCH" ] || { echo "NO VERDICT: detached HEAD — pass --branch or --pr" >&2; exit 4; }
fi

# Disabled workflows queue no runs — answer immediately instead of burning
# the appear-timeout and reporting a misleading "no run registered".
enabled=$(gh workflow list --all --json name,state -q '[.[] | select(.state != "disabled_manually" and .state != "disabled_inactivity")] | length' 2>/dev/null) || enabled=""
if [ "$enabled" = "0" ]; then
  echo "NO VERDICT: every workflow is disabled in this repo (Actions-minutes budget)."
  echo "Re-enable: gh workflow enable ci.yml|test-install.yml|wheels.yml --repo VaitaR/aiochainscan"
  exit 4
fi

BUDGET="${AIO_CI_WAIT_BUDGET:-900}"
INTERVAL="${AIO_CI_POLL_INTERVAL:-30}"
APPEAR="${AIO_CI_APPEAR_TIMEOUT:-90}"
WF_ARGS=()
[ -n "$WORKFLOW" ] && WF_ARGS=(--workflow "$WORKFLOW")

read_run() {
  gh run list --branch "$BRANCH" "${WF_ARGS[@]}" --limit 1 \
    --json databaseId,status,conclusion,displayTitle \
    -q '.[0] | "\(.databaseId)\t\(.status)\t\(.conclusion // "-")\t\(.displayTitle)"' 2>/dev/null
}

echo "Watching CI on branch '$BRANCH' (budget ${BUDGET}s, poll ${INTERVAL}s)..."

# Phase 1: wait for a run to appear (a watcher started right after git push
# can outrun GitHub's run registration).
elapsed=0
run=""
while [ "$elapsed" -lt "$APPEAR" ]; do
  run=$(read_run)
  [ -n "$run" ] && break
  sleep 5; elapsed=$((elapsed + 5))
done
if [ -z "$run" ]; then
  echo "NO RUN: nothing registered for '$BRANCH' within ${APPEAR}s — was anything pushed?"
  exit 3
fi

# Phase 2: poll until the latest run reaches a terminal state.
while [ "$elapsed" -lt "$BUDGET" ]; do
  id=$(printf '%s' "$run" | cut -f1)
  status=$(printf '%s' "$run" | cut -f2)
  conclusion=$(printf '%s' "$run" | cut -f3)
  title=$(printf '%s' "$run" | cut -f4)
  if [ "$status" = "completed" ]; then
    if [ "$conclusion" = "success" ]; then
      echo "SUCCESS: run $id '$title' concluded success (${elapsed}s)"
      exit 0
    fi
    echo "FAILED: run $id '$title' concluded '$conclusion' — inspect: gh run view $id --log-failed"
    exit 1
  fi
  printf '  [%3ds] run %s %s (%s)\n' "$elapsed" "$id" "$status" "$title"
  sleep "$INTERVAL"; elapsed=$((elapsed + INTERVAL))
  run=$(read_run) || true   # a failed read is a degraded tick, not a verdict
done

echo "TIMEOUT: run on '$BRANCH' still not terminal after ${BUDGET}s — re-run to keep watching."
exit 2
