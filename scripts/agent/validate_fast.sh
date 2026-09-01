#!/usr/bin/env bash
# EXIT_CODES:
#   0  all required checks passed
#   1  at least one check failed — do not mark DONE
# END EXIT_CODES
# Agent fast validation — the DONE gate. Run before claiming any task finished.
# Mirrors the disabled GitHub CI lint/test jobs and the AGENTS.md pre-commit
# validation mandate: ruff check, ruff format, import-linter, mypy --strict,
# full pytest. Exit code 0 = all checks passed. Non-zero = do not mark DONE.

set -euo pipefail

PASS=0
FAIL=0

ok()   { echo "[OK]   $*"; ((PASS+=1)) || true; }
fail() { echo "[FAIL] $*"; ((FAIL+=1)) || true; }
info() { echo "[INFO] $*"; }

# The pytest summary line is the only place the number of tests that ACTUALLY
# RAN is visible, so report it next to the verdict. A green rung whose scope
# silently narrowed is otherwise indistinguishable from a real pass. An
# unparseable summary is reported as UNKNOWN, never as a count.
pytest_counts() {
  local line
  line=$(printf '%s\n' "$1" | grep -E '[0-9]+ (passed|failed|error)' | tail -1) || true
  line=$(printf '%s' "$line" | sed -E 's/^[= ]+//; s/[= ]+$//; s/ in [0-9].*$//')
  if [ -n "$line" ]; then
    printf '%s' "$line"
  else
    printf 'test counts UNKNOWN (pytest summary unparseable)'
  fi
}

echo "=== aiochainscan fast validation ==="
echo ""

# Changed-file set, informational only (all checks here are whole-repo).
# Uncommitted work alone is not enough: this runs after committing too, so
# union it with the diff against the branch point.
BASE=$(git merge-base HEAD "${AIO_VALIDATE_BASE:-origin/main}" 2>/dev/null || echo "")
CHANGED=$( { git diff --name-only HEAD 2>/dev/null; git diff --cached --name-only 2>/dev/null;
             [ -n "$BASE" ] && git diff --name-only "$BASE"...HEAD 2>/dev/null;
             git ls-files --others --exclude-standard 2>/dev/null; } | sort -u )
if [ -n "$CHANGED" ]; then
  N_CHANGED=$(printf '%s\n' "$CHANGED" | grep -c '^' || true)
  info "changed files vs origin/main (incl. untracked): $N_CHANGED"
else
  info "no changed files detected vs origin/main"
fi
echo ""

# --- 1. Ruff lint ---
echo "-- ruff check --"
if uv run ruff check . --quiet 2>&1; then
  ok "ruff check: no issues"
else
  fail "ruff check: violations found"
fi

# --- 2. Ruff format ---
echo "-- ruff format --"
if uv run ruff format --check --quiet . 2>&1; then
  ok "ruff format: no changes needed"
else
  fail "ruff format: files would be reformatted — run 'uv run ruff format .'"
fi

# --- 3. Import linter (hexagonal dependency rule) ---
echo "-- import-lint --"
if [ -f ".importlinter" ]; then
  if uv run lint-imports --config .importlinter >/dev/null 2>&1; then
    ok "import-lint: no boundary violations"
  else
    fail "import-lint: boundary check failed"
  fi
else
  info "import-lint: skipped (.importlinter not found)"
fi

# --- 4. mypy strict ---
echo "-- mypy --"
MYPY_OUT=""
if MYPY_OUT=$(uv run mypy --strict aiochainscan 2>&1); then
  ok "mypy --strict: clean ($(printf '%s' "$MYPY_OUT" | tail -1))"
else
  fail "mypy --strict: $(printf '%s\n' "$MYPY_OUT" | tail -3)"
fi

# --- 5. Full test suite ---
echo "-- pytest --"
PYTEST_OUT=""
if PYTEST_OUT=$(uv run pytest tests/ -q --tb=short 2>&1); then
  ok "pytest: $(pytest_counts "$PYTEST_OUT")"
else
  fail "pytest: $(pytest_counts "$PYTEST_OUT") — failing output:"
  printf '%s\n' "$PYTEST_OUT" | grep -E '^(FAILED|ERROR)' | head -20 || true
fi

echo ""
echo "=== Validation result: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
  echo "Do NOT claim DONE. Fix the failures above (or justify PARTIAL)."
  exit 1
fi
echo "All checks green — safe to claim DONE."
exit 0
