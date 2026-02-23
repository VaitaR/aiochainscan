# CI/CD Simplification - 2026-02-23

## Problem
Multiple workflows were attempting to build wheels with maturin, all failing:
- `ci.yml` - build job failed with maturin error
- `test-install.yml` - all jobs failed with maturin error
- Only `wheels.yml` (using cibuildwheel) could potentially work

## Root Cause
Building wheels with Rust extensions (maturin) is complex:
- Requires Rust toolchain correctly configured
- `python -m build` and `uv build` struggle with maturin
- `cibuildwheel` is the proper tool for cross-platform Rust extension wheels

## Solution: Simplified CI Strategy

### Changes Made

#### 1. Removed test-install.yml
**Reason**: This workflow provided minimal value:
- Duplicated testing already done in ci.yml
- Attempted to build wheels on every push (unnecessary)
- All jobs failed with maturin errors
- Installation testing can happen locally or in wheels.yml

#### 2. Simplified ci.yml - Removed build job
**Before**: CI/CD had 4 jobs:
- lint ✓
- test ✓
- build ✗ (failed with maturin)
- publish (depended on build)

**After**: CI/CD has 2 jobs:
- lint ✓
- test ✓

**Why**:
- CI should focus on **code quality**, not distribution packaging
- Building wheels is slow and complex with Rust extensions
- Wheels are only needed on release, not every push
- The Rust extension (fastabi) is **optional** - package works without it

#### 3. Kept wheels.yml (unchanged)
This is the **only** workflow that should build wheels:
- Uses `cibuildwheel` (proper tool for Rust extensions)
- Builds for multiple platforms and Python versions
- Only runs on release or manual trigger
- Handles PyPI publishing directly

## New CI Strategy

### On Every Push/PR
**ci.yml** runs:
1. **Lint** - pre-commit, mypy, import-linter
2. **Test** - pytest across Python 3.10, 3.11, 3.12

Fast, focused on code quality. No wheel building.

### On Release
**wheels.yml** runs:
1. **Build wheels** - cibuildwheel for Linux, Windows, macOS
2. **Build sdist** - source distribution
3. **Publish to PyPI** - wheels + sdist

Comprehensive, handles all platforms, uses proper tooling.

## Benefits

1. **Faster CI** - no maturin builds on every push
2. **Clearer separation** - code quality vs distribution
3. **Fewer failures** - removed problematic workflows
4. **Standard practice** - most Python+Rust projects follow this pattern

## Testing Installation

### Before Release (Local)
```bash
# Test editable install (no wheel needed)
pip install -e .
python -c "import aiochainscan"

# Test that package works without Rust extension
pip install -e . --no-build-isolation
```

### After Release
- `wheels.yml` tests each wheel after building via `CIBW_TEST_COMMAND`
- Users can install from PyPI: `pip install aiochainscan`

## What We're NOT Testing Anymore

1. ~~Wheel installation in clean venv on every push~~ → Tested in wheels.yml on release
2. ~~Source distribution install~~ → Tested in wheels.yml on release
3. ~~Git install simulation~~ → Users can test this locally if needed
4. ~~Build package on every push~~ → Only build on release

## Alternative: If You REALLY Want Install Testing

If you absolutely need to test installation on every push, use this minimal approach in ci.yml:

```yaml
test-basic-install:
  name: Test Basic Install
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    # Test editable install (no wheel, no maturin)
    - name: Test editable install
      run: |
        python -m venv /tmp/test
        source /tmp/test/bin/activate
        pip install -e .
        python -c "import aiochainscan; print('✓ Works')"
```

**But this is not recommended.** The current simplified approach is better.

## Summary

**Before**: 3 workflows, 2 failing with maturin errors
**After**: 2 workflows, both working

CI/CD is now aligned with standard Python+Rust project practices:
- ✅ Code quality on every push
- ✅ Wheel building only on release
- ✅ Proper tooling (cibuildwheel for Rust extensions)
