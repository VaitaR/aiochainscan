# Feature Implementation: Chunked Block Fetcher

## Summary

Successfully implemented automatic block range chunking to prevent database timeouts on blockchain explorers.

## What Was Implemented

### 1. Core Module: `chunked_fetcher.py`
- **Location**: `aiochainscan/services/chunked_fetcher.py`
- **Class**: `ChunkedBlockFetcher`
- **Features**:
  - Automatic block range splitting into configurable chunks
  - Parallel chunk fetching with semaphore-based concurrency control
  - Automatic deduplication of results at chunk boundaries
  - Support for 'latest' block resolution
  - Progress callback support
  - Works for both logs and transactions

### 2. Integration: `unified_fetch.py`
- **Location**: `aiochainscan/services/unified_fetch.py`
- **Changes**:
  - Added `'chunked'` to `Strategy` type (now `'basic' | 'fast' | 'chunked'`)
  - Integrated `ChunkedBlockFetcher` into `fetch_all()` function
  - Automatic fallback to 'fast' for unsupported data types
  - Uses `max_offset` parameter as chunk_size
  - Uses `max_concurrent` parameter for parallel chunk limit

### 3. Comprehensive Tests
- **Location**: `tests/test_chunked_fetcher.py` (20 tests)
- **Coverage**:
  - ✅ Chunk splitting logic (5 tests)
  - ✅ Latest block resolution (2 tests)
  - ✅ Log fetching (6 tests)
  - ✅ Transaction fetching (2 tests)
  - ✅ Progress callbacks (1 test)
  - ✅ Concurrency control (1 test)
  - ✅ Edge cases (3 tests)

- **Integration Tests**: `tests/test_chunked_integration.py` (3 tests)
  - Tests integration with `unified_fetch`
  - Tests fallback behavior

### 4. Documentation
- **User Guide**: `docs/CHUNKED_STRATEGY.md` - Comprehensive documentation
- **Example Demo**: `examples/chunked_fetcher_demo.py` - 5 working examples

## Usage Examples

### Basic Usage
```python
from aiochainscan.services.fetch_all import fetch_all

logs = await fetch_all(
    data_type='logs',
    address='0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT
    start_block=0,
    end_block=20_000_000,
    api_kind='eth',
    network='ethereum',
    api_key='your_key',
    http=http_client,
    endpoint_builder=endpoint_builder,
    strategy='chunked',       # NEW parameter
    max_offset=100_000,       # Chunk size (100k blocks)
    max_concurrent=3,         # Max parallel chunks
)
```

### Direct Fetcher Usage
```python
from aiochainscan.services.chunked_fetcher import ChunkedBlockFetcher

fetcher = ChunkedBlockFetcher(
    http=http_client,
    endpoint_builder=endpoint_builder,
    chunk_size=100_000,
    max_concurrent_chunks=3,
)

logs = await fetcher.fetch_logs(
    address='0x...',
    from_block=0,
    to_block='latest',
    api_kind='eth',
    network='ethereum',
    api_key='key',
)
```

## Key Features

### 1. Automatic Range Splitting
```python
# Input: 0 to 300,000 blocks, chunk_size=100,000
# Output: [(0, 99999), (100000, 199999), (200000, 300000)]
```

### 2. Parallel Fetching
- Fetches multiple chunks concurrently
- Semaphore controls max concurrent requests
- Respects rate limiting

### 3. Deduplication
- Uses `transactionHash:logIndex` as unique key for logs
- Uses `hash` for transactions
- Ensures no duplicates at chunk boundaries

### 4. Stable Sorting
- Results sorted by `(blockNumber, logIndex)` for logs
- Results sorted by `(blockNumber, transactionIndex)` for transactions

### 5. Progress Monitoring
```python
def on_progress(chunk_num, total_chunks, items_fetched):
    print(f"Progress: {chunk_num}/{total_chunks}")

logs = await fetcher.fetch_logs(
    ...,
    on_chunk_complete=on_progress,
)
```

## When to Use

### ✅ Use `strategy='chunked'` when:
- Block range > 500k blocks
- Querying from block 0 to latest
- Getting gateway timeout errors (502, 503, 504)
- Popular contracts (USDT, USDC, Uniswap, etc.)
- Need complete historical data

### ❌ Don't use chunked when:
- Recent blocks only (< 100k blocks) - use `'fast'`
- Low-activity contracts - use `'fast'`
- Real-time monitoring - use `'fast'`

## Performance Characteristics

### Time Complexity
- **Setup**: O(n/chunk_size) - splitting chunks
- **Network**: O(n/chunk_size) - API calls
- **Deduplication**: O(m) where m = total results
- **Sorting**: O(m log m)

### Memory Usage
- All chunks loaded into memory before deduplication
- For 10M blocks with 100k chunk_size = 100 chunks
- Worst case: ~1M items in memory

## Supported Data Types

| Data Type | Supported |
|-----------|-----------|
| `logs` | ✅ Yes |
| `transactions` | ✅ Yes |
| `internal_transactions` | ❌ No (falls back to 'fast') |
| `token_transfers` | ❌ No (falls back to 'fast') |

## Testing Results

```
tests/test_chunked_fetcher.py::TestChunkSplitting           5 passed
tests/test_chunked_fetcher.py::TestLatestBlockResolution    2 passed
tests/test_chunked_fetcher.py::TestLogsFetching            6 passed
tests/test_chunked_fetcher.py::TestTransactionsFetching    2 passed
tests/test_chunked_fetcher.py::TestProgressCallback        1 passed
tests/test_chunked_fetcher.py::TestConcurrencyControl      1 passed
tests/test_chunked_fetcher.py::TestEdgeCases               3 passed
tests/test_chunked_integration.py                          3 passed
------------------------------------------------------------
Total:                                                     23 passed
```

All existing tests still pass (421 passed, 7 skipped).

## Files Created/Modified

### Created
1. `aiochainscan/services/chunked_fetcher.py` (500 lines)
2. `tests/test_chunked_fetcher.py` (500 lines)
3. `tests/test_chunked_integration.py` (100 lines)
4. `examples/chunked_fetcher_demo.py` (450 lines)
5. `docs/CHUNKED_STRATEGY.md` (400 lines)

### Modified
1. `aiochainscan/services/unified_fetch.py` - Added chunked strategy support

## Future Enhancements

1. **Smart Chunk Sizing**: Auto-adjust chunk size based on result density
2. **Resume Support**: Save progress and resume interrupted fetches
3. **More Data Types**: Extend to internal_transactions and token_transfers
4. **Adaptive Concurrency**: Automatically adjust based on rate limits
5. **Chunk Caching**: Cache individual chunks to avoid re-fetching

## Version

- **Feature Version**: aiochainscan v0.4.0
- **Implementation Date**: February 23, 2026
- **Status**: ✅ Complete and tested
