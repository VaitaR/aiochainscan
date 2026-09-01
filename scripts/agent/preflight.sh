#!/usr/bin/env bash
# Agent preflight — run before starting implementation.
# Checks that the local environment is clean and inputs exist.
# Exit code 0 = ok to proceed. Non-zero = fix before starting.

set -euo pipefail

PASS=0
FAIL=0

ok()   { echo "[OK]   $*"; ((PASS+=1)) || true; }
fail() { echo "[FAIL] $*"; ((FAIL+=1)) || true; }
info() { echo "[INFO] $*"; }

echo "=== aiochainscan agent preflight ==="
echo ""

# 1. Git state
info "Git branch: $(git branch --show-current 2>/dev/null || echo 'unknown')"
# Capture git status separately: piping straight into `wc -l` answers 0 for a
# failed read (reads as "clean") and, under set -e, aborts the whole preflight
# instead of reporting the failure. A failed read is UNKNOWN, never clean.
GIT_STATUS_OUT=""
GIT_STATUS_RC=0
GIT_STATUS_OUT=$(git status --porcelain 2>/dev/null) || GIT_STATUS_RC=$?
if [ "$GIT_STATUS_RC" -ne 0 ]; then
  info "Working tree state UNKNOWN — 'git status' failed (exit $GIT_STATUS_RC), not verified clean"
else
  if [ -z "$GIT_STATUS_OUT" ]; then
    ok "Working tree is clean"
  else
    DIRTY=$(printf '%s\n' "$GIT_STATUS_OUT" | grep -c '^' || true)
    info "Working tree has $DIRTY changed file(s) — review before starting"
  fi
fi

# 2. uv / Python env
if command -v uv &>/dev/null; then
  ok "uv is available: $(uv --version)"
else
  fail "uv not found — run: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

if command -v uv &>/dev/null; then
  if uv sync --extra dev --frozen -q; then
    ok "uv sync: dependencies in sync (extra: dev)"
  else
    fail "uv sync failed — check uv.lock or pyproject.toml"
  fi
else
  fail "uv sync unavailable — install uv before starting"
fi

# 3. .env presence (ETHERSCAN_KEY lives here; unit tests mock the network, so
#    this is advisory — only live-API examples and manual runs need it)
if [ -f ".env" ]; then
  ok ".env present"
else
  info ".env missing — copy .env.example (only needed for live-API runs, not for tests)"
fi

# 4. AGENTS.md readable
if [ -f "AGENTS.md" ]; then
  ok "AGENTS.md present"
else
  fail "AGENTS.md missing — cannot determine governance rules"
fi

# 5. Import linter config present + runs
if [ -f ".importlinter" ]; then
  if uv run lint-imports --config .importlinter >/dev/null 2>&1; then
    ok "import-lint: no boundary violations"
  else
    fail "import-lint: boundary check failed"
  fi
else
  info "import-lint: skipped (.importlinter not found)"
fi

# 6. Test collection (catches import errors/syntax errors before a full run)
if command -v uv &>/dev/null; then
  COLLECT_OUT=""
  if COLLECT_OUT=$(uv run pytest --collect-only -q 2>&1); then
    # Matches both "587 tests collected" and "387/395 tests collected (8 deselected)".
    # `|| TESTS=""` keeps a no-match grep from killing the script via pipefail.
    TESTS=$(printf '%s' "$COLLECT_OUT" | grep -E '[0-9]+(/[0-9]+)? tests? collected' | tail -1) || TESTS=""
    ok "pytest collection: ${TESTS:-clean}"
  else
    fail "pytest collection failed — fix import/syntax errors before starting"
  fi
fi

# 7. mypy available
if command -v uv &>/dev/null && uv run mypy --version >/dev/null 2>&1; then
  ok "mypy available: $(uv run mypy --version)"
else
  fail "mypy not available — uv sync first"
fi

# 8. Rust FFI (advisory — decode() falls back to pure Python without it)
if python3 -c "import aiochainscan.fastabi" 2>/dev/null || \
   uv run python -c "import aiochainscan.fastabi" 2>/dev/null; then
  ok "fastabi (Rust FFI) built"
else
  info "fastabi not built — decode() uses the Python fallback; build with 'make fastabi' if needed"
fi

echo ""
echo "=== Preflight result: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
  echo "Fix failures before starting implementation."
  exit 1
fi
exit 0
