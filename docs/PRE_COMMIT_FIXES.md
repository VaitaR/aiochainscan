# Pre-Commit Fixes - 2026-02-23

## Issues Fixed

### 1. Circular Import in `aiochainscan/__init__.py`
**Problem**:
```python
# Line 26 - Circular import
from aiochainscan.core.client import ChainscanClient
```
When `ChainscanClient` is imported, it imports scanners → scanners register themselves → triggers module initialization → circular dependency.

**Solution**:
Moved `ChainscanClient` import to the end of `__init__.py` (after all scanner registrations):
```python
# Import ChainscanClient last to avoid circular import
# (it imports scanners which register themselves during import)
from aiochainscan.core.client import ChainscanClient  # noqa: E402
```

### 2. aiohttp Import Blocker in `blockscout_v2.py`
**Problem**:
```python
# Line 20 - Unconditional import
import aiohttp
```
Library fails to import when `aiohttp` is not installed (httpx-only installations).

**Solution**:
Made aiohttp import optional with fallback:
```python
try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore
```

Added runtime checks in methods that use aiohttp:
```python
if aiohttp is None:
    raise ImportError(
        "aiohttp is required for BlockScout V2 scanner. "
        "Install it with: pip install 'aiochainscan[http]'"
    )
```

### 3. Code Formatting Issues
**Auto-Fixed by pre-commit hooks**:
- Trailing whitespace removed (6 files)
- Ruff formatting applied (2 files)
- Line ending normalization

**Files formatted**:
- `.github/workflows/wheels.yml`
- `AGENTS.md`
- `docs/AUDIT_2026-02-23_INDEPENDENT.md`
- `docs/QA_REPORT_2026-02-23.md`
- `docs/ROADMAP.md`
- `docs/skill.md`
- `tests/test_decode_fastabi.py`
- `aiochainscan/__init__.py`
- `aiochainscan/scanners/blockscout_v2.py`

## Verification

### ✅ Pre-commit Hooks
```bash
uv run pre-commit run --all-files
```
**Result**: All 8 hooks passed

### ✅ Test Suite
```bash
python -m pytest tests/ -q
```
**Result**: 338 passed, 7 skipped, 12 deselected

### ✅ Import Test
```python
from aiochainscan import ChainscanClient, Method
print(ChainscanClient)  # <class 'aiochainscan.core.client.ChainscanClient'>
print(Method)  # <enum 'Method'>
```
**Result**: No circular import errors

### ✅ User Flow Test
```python
async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
    balance = await client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
    txs = await client.get_transactions('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
```
**Result**: ✅ Balance: 32.1229 ETH, ✅ Transactions: 50

## Impact

**Before**:
- Library failed to import with circular dependency error
- Library crashed when aiohttp not installed
- Pre-commit hooks failed with formatting issues

**After**:
- ✅ Clean imports with lazy loading
- ✅ Graceful degradation for optional dependencies
- ✅ All pre-commit hooks pass
- ✅ All 338 tests pass
- ✅ User flows work correctly

## Related Issues

- Circular import prevents library usage
- aiohttp blocker (duplicate of previous fix in `adapters/__init__.py`)
- Code formatting consistency

## Next Steps

1. ✅ Pre-commit hooks integrated into development workflow
2. ✅ Consider adding `.pre-commit-config.yaml` to repo
3. ✅ Update CI/CD to run pre-commit hooks in GitHub Actions
4. Document pre-commit setup in CONTRIBUTING.md
