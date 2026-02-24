# Whale Block Data Loss Fix

**Date**: 2026-02-23
**Severity**: CRITICAL
**Status**: FIXED

## Problem

The pagination engine in `aiochainscan/services/paging_engine.py` had a critical data loss bug when encountering "whale blocks" - blocks that contain more transactions than the API's pagination limit (typically 10,000).

### The Bug

When using sliding window pagination, if a single block contained 10,000+ transactions:

1. The engine would fetch the first 10,000 transactions from that block
2. Detect that all items were from the same block (whale detection)
3. **Log a critical warning but continue execution**
4. Skip to the next block via `current_start = max(current_start, last_block + 1)`
5. **Permanently lose all transactions beyond the first 10,000**

### Example Scenario

```
Block #100: 15,000 transactions
- Fetch page 1: Get 10,000 transactions from block #100
- Hit API limit (10,000 items)
- Detect: first_block == last_block == 100
- Log: "PAGINATION DATA LOSS: Block 100 contains >= 10000 items..."
- Jump to: current_start = 101  ← DATA LOSS!
- Result: 5,000 transactions permanently lost
```

## Root Cause

The code detected the whale scenario and logged it, but then **silently continued** by advancing to the next block. This was a fail-silent approach that violated the principle of "fail fast on data integrity issues."

## The Fix

### 1. New Exception: `PaginationDataLossError`

Added a new exception in `aiochainscan/exceptions.py`:

```python
class PaginationDataLossError(ChainscanClientError):
    """Raised when a single block contains more transactions than the API's pagination limit.

    This is the "whale block" problem: when a block has 10,000+ transactions and the API
    only allows fetching 10,000 items per request. Without per-transaction pagination
    or GraphQL support, we cannot retrieve all data without loss.

    This exception prevents silent data loss by failing loudly when this scenario is detected.
    """
```

### 2. Fail-Fast Behavior

Modified `aiochainscan/services/paging_engine.py` (line ~260):

**Before:**
```python
if len(items) >= effective_offset_for_provider and first_block == last_block:
    logger.critical('PAGINATION DATA LOSS: Block %d contains >= %d items...', ...)
    # Continue silently - DATA LOSS!

current_start = max(current_start, last_block + 1)
```

**After:**
```python
if len(items) >= effective_offset_for_provider and first_block == last_block:
    # Record telemetry
    if telemetry is not None:
        await telemetry.record_event('paging.whale_block_detected', {...})

    # FAIL FAST - prevent data loss
    raise PaginationDataLossError(
        block_number=last_block,
        items_fetched=len(items),
        api_limit=effective_offset_for_provider,
        suggested_action=(
            'This block contains more transactions than the API limit. '
            'Options: (1) Use GraphQL API if supported (BlockScout), '
            '(2) Apply topic/address filters to reduce result set, '
            '(3) Use a different data provider, or '
            '(4) Fetch this block separately via block-by-number endpoint.'
        ),
    )

current_start = max(current_start, last_block + 1)
```

### 3. Comprehensive Test Coverage

Added `tests/test_whale_block_pagination.py` with 5 test cases:

1. **`test_whale_block_raises_pagination_error`**: Verifies exception is raised for whale blocks
2. **`test_whale_block_not_triggered_when_below_limit`**: Ensures false positives don't occur
3. **`test_whale_block_not_triggered_when_multiple_blocks`**: 10k items across multiple blocks is OK
4. **`test_whale_block_exception_message`**: Validates helpful error messages
5. **`test_whale_block_with_telemetry`**: Verifies telemetry event is recorded

All tests pass.

## Impact

### Before Fix
- **Silent data loss** when encountering whale blocks
- No way for users to know they were missing data
- Corrupted analytics and transaction histories
- Violated data integrity guarantees

### After Fix
- **Loud failure** with actionable error message
- Users are immediately aware of the limitation
- Provides clear guidance on resolution strategies
- Maintains data integrity guarantees

## Resolution Strategies

When users encounter `PaginationDataLossError`, they have several options:

### Option 1: Use GraphQL API (Recommended for BlockScout)

BlockScout V2 has GraphQL support that can handle large blocks:

```python
# aiochainscan already has GraphQL infrastructure
# Future enhancement: Auto-fallback to GraphQL for whale blocks
```

### Option 2: Apply Filters

Reduce the result set by filtering:

```python
# Filter by event topic
await client.get_logs(
    address=whale_contract,
    topics=['0x...'],  # Specific event signature
    start_block=100,
    end_block=100,
)
```

### Option 3: Use Alternative Endpoints

Some APIs provide block-specific endpoints:

```python
# Fetch block with all transactions
block = await client.get_block_by_number(100, full_transactions=True)
```

### Option 4: Split the Query

Break the whale block into smaller time windows if the API supports timestamp filtering.

## Testing

Run whale block tests:

```bash
python -m pytest tests/test_whale_block_pagination.py -v
```

Run full test suite:

```bash
python -m pytest tests/ -v --tb=short -x
```

## Verification

All existing tests continue to pass, confirming backward compatibility.

## Related Files

- `aiochainscan/exceptions.py`: New exception
- `aiochainscan/services/paging_engine.py`: Fail-fast logic
- `tests/test_whale_block_pagination.py`: Test coverage

## Future Enhancements

1. **Auto-GraphQL Fallback**: When whale block detected and GraphQL available, automatically switch
2. **Transaction Index Pagination**: If API supports it, paginate within a block
3. **Whale Block Cache**: Remember known whale blocks to optimize retry strategies
4. **Configurable Behavior**: Allow users to choose between fail-fast vs. best-effort

## References

- Issue: Whale block data loss bug
- PR: Whale block pagination fix
- Related: GraphQL support plan (docs/GRAPHQL_SUPPORT_PLAN.md)
