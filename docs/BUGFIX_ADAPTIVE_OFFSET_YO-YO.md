# Bugfix: Adaptive Offset Yo-Yo Effect

**Date**: 2026-02-23
**Severity**: CRITICAL - Data Efficiency Bug
**Status**: FIXED ✅

## Problem Description

### The Yo-Yo Effect Bug

When fetching blockchain data from BlockScout instances with large offsets (10,000 items), the system implemented adaptive offset reduction to handle gateway timeouts (502/504 errors). However, the reduction was **not persistent across page fetches**, causing a "yo-yo effect":

```
Page 1: Try 10k → Fail (502) → Retry 5k → Success
Page 2: Try 10k → Fail (502) → Retry 5k → Success  ← BUG: Reset to 10k!
Page 3: Try 10k → Fail (502) → Retry 5k → Success  ← BUG: Reset to 10k!
...
```

### Impact

- **Doubled API Requests**: Every page required 2 requests instead of 1
- **Wasted API Quota**: Half the requests were predictable failures
- **Increased Latency**: Each failed request added timeout delays
- **Gateway Hammering**: Repeatedly sending requests destined to fail

### Root Cause

The `current_offset` variable was **local to the `_fetch_page` function**, resetting on each page:

```python
async def _fetch_page(*, page: int, start_block: int, end_block: int, offset: int):
    current_offset = int(offset)  # ← Resets to original offset every page!
    attempts_left = 3
    while True:
        try:
            return await get_internal_transactions(..., offset=current_offset, ...)
        except HTTPStatusError as exc:
            if exc.response.status_code in {502, 503, 504, 520, 524}:
                current_offset = max(1000, current_offset // 2)  # Reduced but lost!
                continue
            raise
```

## Solution

### Persistent Adaptive State

Moved `current_offset` to **parent scope** using a state class that persists across all page fetches:

```python
async def fetch_all_internal_basic(..., max_offset: int = 10_000, ...):
    # Persistent state for adaptive offset reduction across ALL page fetches
    class _AdaptiveOffsetState:
        def __init__(self, initial_offset: int):
            self.current_offset = initial_offset
            self.reduction_count = 0

        def reduce_offset(self) -> None:
            old_offset = self.current_offset
            self.current_offset = max(1000, self.current_offset // 2)
            self.reduction_count += 1
            if telemetry:
                telemetry.log(
                    f'adaptive_offset_reduction: {old_offset} -> {self.current_offset} '
                    f'(reduction #{self.reduction_count})'
                )

    offset_state = _AdaptiveOffsetState(max_offset)

    async def _fetch_page(*, page: int, start_block: int, end_block: int, offset: int):
        effective_offset = offset_state.current_offset  # ← Persistent!
        attempts_left = 3
        while True:
            try:
                return await get_internal_transactions(..., offset=effective_offset, ...)
            except HTTPStatusError as exc:
                if exc.response.status_code in {502, 503, 504, 520, 524}:
                    attempts_left -= 1
                    offset_state.reduce_offset()  # ← Persists across iterations!
                    effective_offset = offset_state.current_offset
                    continue
                raise
```

### New Behavior

With the fix, offset reduction **persists for the entire fetch operation**:

```
Page 1: Try 10k → Fail (502) → Retry 5k → Success
Page 2: Try 5k → Success  ← FIX: Uses persistent reduced offset!
Page 3: Try 5k → Success  ← FIX: Continues with 5k!
...
```

## Files Modified

1. **[aiochainscan/services/fetch_all.py](../aiochainscan/services/fetch_all.py#L217-L289)**
   - `fetch_all_internal_basic()` - Added `_AdaptiveOffsetState` class

2. **[aiochainscan/services/unified_fetch.py](../aiochainscan/services/unified_fetch.py#L207-L304)**
   - `fetch_all()` - Added `_AdaptiveOffsetState` class for internal_transactions with strategy='basic'

3. **[tests/test_adaptive_offset_persistence.py](../tests/test_adaptive_offset_persistence.py)** ✨ NEW
   - Comprehensive test suite verifying offset persistence
   - Tests multi-page scenarios that would expose the yo-yo bug
   - Tests multiple reduction levels (10k → 5k → 2.5k → 1.25k → 1k)
   - Tests telemetry logging of offset changes

## Testing

All tests pass including 4 new tests specifically for this fix:

```bash
$ pytest tests/test_adaptive_offset_persistence.py -v
✅ test_adaptive_offset_multiple_page_scenario
✅ test_adaptive_offset_unified_fetch_multi_page
✅ test_adaptive_offset_reduction_multiple_levels
✅ test_adaptive_offset_telemetry_logging
```

Full test suite: **372 passed, 7 skipped** ✅

## Benefits

### Efficiency Gains

For a fetch operation with 3 pages encountering timeouts:

**Before (Buggy)**:
- Requests: 6 (3 failures + 3 successes)
- API calls wasted: 3 (50%)
- Time: 3× timeout delay + 3× successful requests

**After (Fixed)**:
- Requests: 4 (1 failure + 3 successes)
- API calls wasted: 1 (25%)
- Time: 1× timeout delay + 3× successful requests

**Improvement**: 33% fewer requests, 67% fewer timeout delays

### Operational Benefits

- **Reduced Gateway Load**: No repeated failing requests
- **Better API Quota Usage**: Fewer wasted calls
- **Faster Data Fetching**: Fewer timeout delays
- **Observable Behavior**: Telemetry logs track offset reductions

## Telemetry

When offset reduction occurs, the system now logs:

```
adaptive_offset_reduction: 10000 -> 5000 (reduction #1)
adaptive_offset_reduction: 5000 -> 2500 (reduction #2)
```

This enables monitoring and debugging of API instability patterns.

## Related

- Original issue: User report about "doubling requests" on BlockScout
- Context: BlockScout gateways often can't handle 10k offsets but work fine with 5k
- Pattern: Adaptive offset reduction is a survival mechanism for API instability
- Lesson: State that changes based on runtime conditions must persist across iterations

## Verification

To verify the fix is working in production:

1. Check telemetry logs for `adaptive_offset_reduction` messages
2. Verify offset stays reduced (no repeated reductions at same level)
3. Monitor API request counts (should see reduction from yo-yo elimination)

---

**Fix implemented**: 2026-02-23
**All tests passing**: ✅
**Production ready**: ✅
