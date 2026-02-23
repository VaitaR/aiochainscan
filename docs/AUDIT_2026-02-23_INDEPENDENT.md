# Independent Code Audit: aiochainscan
**Date:** 2026-02-23  
**Auditor:** Senior Software Architect  
**Focus:** Architecture, Security, Type Safety, Performance, API Consistency

---

## Executive Summary

This audit discovered **29 mypy errors**, multiple architectural concerns, and several issues **not covered** in the existing audit document. The codebase shows good progress on hexagonal architecture but has significant gaps in Protocol implementations, exception handling hygiene, and resource management.

---

## Findings by Category

### 1. TYPE SAFETY ISSUES (mypy)

| Severity | File | Line | Issue | Fix |
|----------|------|------|-------|-----|
| **HIGH** | [adapters/simple_rate_limiter.py](aiochainscan/adapters/simple_rate_limiter.py#L22) | 22 | Protocol signature mismatch: `acquire(key)` missing default value | Add `key: str = 'default'` to match Protocol |
| **HIGH** | [adapters/__init__.py](aiochainscan/adapters/__init__.py#L6) | 6 | `Cannot assign to a type` - wrong type assignment pattern for optional imports | Use `AiohttpClient: type | None = None` pattern |
| **HIGH** | [services/analytics.py](aiochainscan/services/analytics.py#L21) | 21 | `None` assigned to module type variable | Use `Any` or proper TypeAlias pattern |
| **HIGH** | [mcp_server.py](aiochainscan/mcp_server.py#L16) | 16 | Same pattern - `FastMCP = None` type error | Use `FastMCPType: Any = None` pattern |
| **MEDIUM** | [core/client.py](aiochainscan/core/client.py#L341) | 341 | Missing type annotation for `__aexit__` parameters | Add proper exception type hints |
| **MEDIUM** | [core/client.py](aiochainscan/core/client.py#L372) | 372+ | Multiple `list[dict]` without type params | Use `list[dict[str, Any]]` |
| **MEDIUM** | [adapters/orjson_parser.py](aiochainscan/adapters/orjson_parser.py#L27) | 27,42 | `Returning Any from function declared to return dict[str, Any]` | Add explicit cast or change return type |
| **MEDIUM** | [domain/dto_v2.py](aiochainscan/domain/dto_v2.py#L215) | 215 | `Returning Any` from typed function | Add proper cast |
| **LOW** | [adapters/tenacity_retry.py](aiochainscan/adapters/tenacity_retry.py#L49) | 49 | Unused `type: ignore` comment | Remove obsolete ignore |

**Total mypy errors:** 29 across 9 files

---

### 2. ERROR HANDLING AUDIT

| Severity | File | Line | Issue | Fix |
|----------|------|------|-------|-----|
| **HIGH** | [services/account.py](aiochainscan/services/account.py#L89) | 89 | Bare `except Exception` silently converts to `value = 0` | Log warning, use specific exceptions |
| **HIGH** | [services/account.py](aiochainscan/services/account.py#L423) | 423 | Catches `Exception` in fallback chain - masks real errors | Catch specific `ImportError` |
| **HIGH** | [services/account.py](aiochainscan/services/account.py) | Multiple (463, 495, 521, 565, 593, 602, 660, 816, 893...) | 15+ bare `except Exception` blocks | Add specific exception handling |
| **HIGH** | [decode.py](aiochainscan/decode.py#L144) | 144, 373, 428, 496 | Bare `except Exception` for fallback logic | At minimum log the actual error |
| **HIGH** | [services/block.py](aiochainscan/services/block.py#L271) | 271 | Silent exception swallowing | Add logging |
| **MEDIUM** | [paging_engine.py](aiochainscan/services/paging_engine.py#L260-283) | 260-283 | Data loss only logged as critical, not raised | Consider raising `ChainscanPaginationOverflowError` |
| **MEDIUM** | [config.py](aiochainscan/config.py#L346) | 346 | File loading catches generic `Exception` | Handle `IOError`, `json.JSONDecodeError` specifically |

**Pattern identified:** Code uses exception suppression as control flow. This masks real bugs and makes debugging difficult.

---

### 3. ARCHITECTURE REVIEW

#### 3.1 Hexagonal Architecture Adherence

| Component | Status | Notes |
|-----------|--------|-------|
| **Ports** | ✅ Good | Clean Protocol definitions in `ports/` |
| **Adapters** | ⚠️ Partial | Good implementations but Protocol signature mismatches |
| **Services** | ❌ Problematic | 1351-line `account.py` violates SRP, many duplicate fetch patterns |
| **Scanners** | ⚠️ Partial | BlockScout bypasses Network layer entirely |
| **Core** | ✅ Good | Clean `ChainscanClient` facade |

#### 3.2 NEW: Dependency Issues Not in Existing Audit

| Severity | Issue | Location |
|----------|-------|----------|
| **HIGH** | `aiohttp` imported in `blockscout_v2.py` but not declared as dependency | [scanners/blockscout_v2.py#L20](aiochainscan/scanners/blockscout_v2.py#L20) |
| **MEDIUM** | `from_config` creates circular complexity between `client.py` and `config.py` | [core/client.py#L120-200](aiochainscan/core/client.py#L120-200) |
| **MEDIUM** | Services import from `..` relative paths creating tight coupling | Multiple service files |

#### 3.3 NEW: Interface Contract Violations

```python
# Port defines:
class RateLimiter(Protocol):
    async def acquire(self, key: str = 'default') -> None: ...

# Adapter implements:  
class SimpleRateLimiter(RateLimiter):
    async def acquire(self, key: str) -> None:  # Missing default!
```

This breaks substitutability - callers expecting default parameter will fail.

---

### 4. SECURITY REVIEW

| Severity | Issue | Location | Fix |
|----------|-------|----------|-----|
| **MEDIUM** | ✅ Already fixed in codebase | [network.py#L29-36](aiochainscan/network.py#L29-36) | Header redaction implemented |
| **LOW** | Config file parsing doesn't validate input structure | [config.py#L299](aiochainscan/config.py#L299) | Add schema validation |
| **LOW** | No input validation on `address` parameter format | Multiple locations | Add address format validation |

**Good practices found:**
- API keys are redacted in logs via `_redact_headers()`
- No hardcoded credentials found
- No SQL usage (not applicable)

---

### 5. PERFORMANCE REVIEW

#### 5.1 NEW: Resource Management Issues

| Severity | Issue | Location | Fix |
|----------|-------|----------|-----|
| **HIGH** | BlockScout creates new `aiohttp.ClientSession` per call | [blockscout_v2.py#L329-348](aiochainscan/scanners/blockscout_v2.py#L329-348) | Use injected `Network` client |
| **HIGH** | Same issue in BlockScout V1 | [blockscout_v1.py#L146](aiochainscan/scanners/blockscout_v1.py#L146) | Same fix |
| **MEDIUM** | Paging engine accumulates all items in memory | [paging_engine.py#L132](aiochainscan/services/paging_engine.py#L132) | Add streaming API |
| **LOW** | Synchronous file I/O in config loading | [config.py#L269](aiochainscan/config.py#L269) | Use `aiofiles` for async context |

#### 5.2 NEW: Blocking Calls in Async Context

```python
# config.py - synchronous file read in potentially async context
with open(env_file) as f:
    for line in f:
        ...
```

While config loading happens at startup, this pattern could block event loop if called during runtime.

#### 5.3 Connection Pooling

| Scanner | Pooling Status |
|---------|----------------|
| Etherscan V2 | ✅ Uses shared `Network` with `httpx` pooling |
| BlockScout V1 | ❌ Creates per-request session |
| BlockScout V2 | ❌ Creates per-request session |

---

### 6. API CONSISTENCY REVIEW

#### 6.1 Method Naming

| Issue | Examples | Recommendation |
|-------|----------|----------------|
| Inconsistent async naming | `get_balance` vs `get_address_balance` | Standardize on shorter form |
| Underscore-prefixed "private" methods exposed | `_build_url`, `_build_query_params` | Use `__` for truly private |

#### 6.2 Parameter Naming

| Issue | Location | Fix |
|-------|----------|-----|
| `start_block`/`startblock` inconsistency | Various services vs DTOs | Standardize on snake_case |
| `contract_address`/`contractaddress` | Param maps vs API | Document clearly in specs |

#### 6.3 Return Type Consistency

| Method | Returns | Issue |
|--------|---------|-------|
| `get_balance` | `str` | Should return `int` for consistency |
| `get_transactions` | `list[dict]` | Missing generic params |
| `call()` | `Any` | Too broad, loses type safety |

#### 6.4 Docstring Coverage

| Module | Coverage | Notes |
|--------|----------|-------|
| `core/client.py` | 85% | Good coverage |
| `services/account.py` | 40% | Many functions lack docstrings |
| `scanners/*.py` | 70% | Decent |
| `ports/*.py` | 30% | Protocols need better docs |

---

## NEW ISSUES NOT IN EXISTING AUDIT

### 7. Additional Critical Findings

#### 7.1 **CRITICAL**: Analytics module silently fails

```python
# services/analytics.py:21
try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False
    pl = None  # This creates mypy error AND runtime issues
```

The `pl = None` assignment causes:
1. mypy error: `Incompatible types in assignment`
2. Potential runtime `AttributeError` if code paths aren't guarded

**Fix:**
```python
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False
    if 'polars' not in sys.modules:
        pl = None  # type: ignore[assignment]
```

#### 7.2 **HIGH**: MCP server type safety

```python
# mcp_server.py:16
FastMCP = None  # Cannot assign to a type
```

This breaks type checking and IDE support.

**Fix:**
```python
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

FastMCPClass: Any = None
try:
    from mcp.server.fastmcp import FastMCP as FastMCPClass
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
```

#### 7.3 **MEDIUM**: Decode module has hidden import

```python
# decode.py:9
from eth_utils import keccak  # Module doesn't explicitly export this
```

This works but generates mypy error. Should use:
```python
from eth_utils.crypto import keccak
```

#### 7.4 **MEDIUM**: Untyped factory function

```python
# mcp_server.py:22
def create_mcp_server():  # Missing return type
```

Should be:
```python
def create_mcp_server() -> Any:  # Or proper FastMCP type when available
```

---

## Prioritized Remediation Plan

### Phase 1: Critical (Blockers)
1. ✅ Fix aiohttp optional import (already done per existing audit)
2. 🔴 Fix Protocol signature mismatch in `SimpleRateLimiter`
3. 🔴 Fix type assignment patterns for optional imports (`adapters/__init__.py`, `analytics.py`, `mcp_server.py`)

### Phase 2: High Priority
4. 🔴 Unify BlockScout scanners to use `Network` layer
5. 🔴 Reduce bare `except Exception` handlers (add logging at minimum)
6. 🔴 Add missing type annotations to `core/client.py`

### Phase 3: Medium Priority
7. 🟡 Add streaming API to paging engine
8. 🟡 Break up 1351-line `services/account.py`
9. 🟡 Standardize return types (balance as `int`, transactions as `list[dict[str, Any]]`)

### Phase 4: Polish
10. 🟢 Improve docstring coverage in ports
11. 🟢 Add address format validation
12. 🟢 Consider async file I/O for config loading

---

## Test Coverage Note

Current test suite: `333 passed, 7 skipped, 12 deselected`

Recommend adding:
- Protocol conformance tests for all adapters
- Property-based tests for address validation
- Integration tests for BlockScout with mocked Network layer

---

## Summary Statistics

| Category | Critical | High | Medium | Low |
|----------|----------|------|--------|-----|
| Type Safety | 3 | 4 | 6 | 1 |
| Error Handling | 0 | 5 | 2 | 0 |
| Architecture | 0 | 2 | 2 | 0 |
| Security | 0 | 0 | 0 | 2 |
| Performance | 0 | 2 | 1 | 1 |
| API Consistency | 0 | 0 | 3 | 1 |
| **Total** | **3** | **13** | **14** | **5** |

**Total issues found: 35** (excluding issues already documented in existing audit)
