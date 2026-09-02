# Streaming Pattern for Memory-Efficient Data Fetching

## Overview

The Streaming Pattern provides AsyncIterator-based batch fetching to handle whale addresses with millions of transactions without running out of memory (OOM).

### Problem: Traditional Bulk Fetch

```python
# Materialized approach: loads all data into memory
transactions = await client.get_all_transactions(whale_address)
# For 1M transactions: ~2GB RAM required
# For 10M transactions: OOM crash
```

### Solution: Streaming Pattern

```python
# Streaming approach: processes one batch at a time
async for batch in client.iter_transactions_streaming(whale_address, batch_size=1000):
    # Process 1000 transactions at a time
    # Memory usage: ~10MB (constant, regardless of total dataset size)
    await process_batch(batch)
```

## When to Use Streaming

Use streaming when:
- **Whale addresses**: Addresses with 100k+ transactions
- **Large block ranges**: Fetching years of historical data
- **Memory-constrained environments**: Cloud functions, containers with limited RAM
- **Batch processing**: ETL pipelines, data exports, analytics

Use traditional bulk fetch when:
- **Small datasets**: < 10k items
- **Need all data at once**: For sorting, grouping, or in-memory analysis
- **Simple scripts**: When memory is not a concern

## API Reference

### Client Methods

#### `iter_transactions_streaming()`

Stream normal transactions in batches.

```python
async def iter_transactions_streaming(
    self,
    address: str,
    from_block: int = 0,
    to_block: int | str | None = 'latest',
    batch_size: int = 1000,
    on_progress: ProgressCallback | None = None,
) -> AsyncIterator[list[dict[str, Any]]]
```

**Parameters:**
- `address`: Wallet address to fetch transactions for
- `from_block`: Starting block number (default: 0)
- `to_block`: Ending block number or 'latest' (default: 'latest')
- `batch_size`: Number of transactions per batch (default: 1000)
- `on_progress`: Optional callback for progress updates

**Yields:**
- Batches of transaction dictionaries (`list[dict]`)

**Example:**
```python
client = ChainscanClient.from_config('etherscan', 'ethereum')

total = 0
async for batch in client.iter_transactions_streaming(
    '0xWhaleAddress',
    batch_size=1000
):
    total += len(batch)
    print(f"Processed {total} transactions so far...")

    # Process batch (e.g., insert to database)
    await db.bulk_insert(batch)

print(f"Total: {total} transactions")
```

#### `iter_internal_transactions_streaming()`

Stream internal transactions (contract calls) in batches.

```python
async for batch in client.iter_internal_transactions_streaming(
    '0xContractAddress',
    from_block=15000000,
    to_block=16000000,
    batch_size=500
):
    for tx in batch:
        print(f"Internal call: {tx['from']} -> {tx['to']}")
```

#### `iter_token_transfers_streaming()`

Stream ERC20 token transfers in batches.

```python
# All token transfers for an address
async for batch in client.iter_token_transfers_streaming(
    '0xWhaleAddress',
    batch_size=1000
):
    await process_transfers(batch)

# Filter by specific token
async for batch in client.iter_token_transfers_streaming(
    '0xWhaleAddress',
    contract_address='0xUSDC',  # Only USDC transfers
    batch_size=1000
):
    await process_usdc_transfers(batch)
```

#### `iter_logs_streaming()`

Stream event logs in batches.

```python
# All Transfer events from USDC contract
async for batch in client.iter_logs_streaming(
    address='0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',  # USDC
    topic0='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',  # Transfer
    from_block=15000000,
    batch_size=500
):
    for log in batch:
        print(f"Transfer event: {log}")
```

## Performance Comparison

### Memory Usage

| Method | 10k txs | 100k txs | 1M txs | 10M txs |
|--------|---------|----------|---------|---------|
| **Bulk fetch** | 20 MB | 200 MB | 2 GB | 20 GB (OOM) |
| **Streaming (batch=1000)** | 5 MB | 5 MB | 5 MB | 5 MB |

### Processing Time

Streaming has minimal overhead (~5-10%) compared to bulk fetch due to:
- Incremental deduplication
- Per-batch sorting
- Generator overhead

For whale addresses, streaming is **faster** because:
- No final sort of millions of items
- No large memory allocations
- Better cache locality

## Advanced Usage

### Progress Tracking

```python
async def on_progress(fetched, total_expected, current_block, current_page, operation):
    print(f"Progress: {fetched} items fetched, block {current_block}")

async for batch in client.iter_transactions_streaming(
    whale_address,
    on_progress=on_progress,
    batch_size=1000
):
    await process_batch(batch)
```

### Early Termination

```python
# Process only first 50k transactions
total = 0
async for batch in client.iter_transactions_streaming(whale_address, batch_size=1000):
    await process_batch(batch)
    total += len(batch)
    if total >= 50_000:
        break  # Stop fetching
```

### Batch Size Tuning

Choose batch size based on:
- **Network latency**: Larger batches (2000-5000) for high latency
- **Memory constraints**: Smaller batches (100-500) for limited RAM
- **Processing time**: Match batch size to processing speed

```python
# Fast processing, high memory
async for batch in client.iter_transactions_streaming(address, batch_size=5000):
    await fast_process(batch)

# Slow processing, low memory
async for batch in client.iter_transactions_streaming(address, batch_size=100):
    await slow_heavy_process(batch)
```

### Database Export

```python
import aiocsv
import aiofiles

async def export_to_csv(address: str, filename: str):
    """Export all transactions to CSV using streaming."""
    async with aiofiles.open(filename, 'w') as f:
        writer = aiocsv.AsyncWriter(f)

        # Write header
        await writer.writerow(['hash', 'from', 'to', 'value', 'blockNumber'])

        # Stream and write batches
        async for batch in client.iter_transactions_streaming(
            address,
            batch_size=1000
        ):
            for tx in batch:
                await writer.writerow([
                    tx['hash'],
                    tx['from'],
                    tx['to'],
                    tx['value'],
                    tx['blockNumber'],
                ])

await export_to_csv('0xWhale', 'whale_transactions.csv')
```

### Multi-Address Processing

```python
whale_addresses = ['0xWhale1', '0xWhale2', '0xWhale3']

for address in whale_addresses:
    print(f"Processing {address}...")
    total = 0

    async for batch in client.iter_transactions_streaming(
        address,
        batch_size=1000
    ):
        await db.bulk_insert(batch)
        total += len(batch)

    print(f"  Processed {total} transactions")
```

## ABI Decoding While Streaming

Streaming batches can be combined with ABI decoding via `iter_transactions(abi=...)`
(the standalone `StreamingDecoder` service was removed — decoding now lives in
`ChainscanClient`):

```python
# Use existing iter_transactions() for decoding
abi = json.loads(await client.get_contract_abi(contract_address))

async for tx in client.iter_transactions(
    whale_address,
    abi=abi,
    batch_size=1000  # Decoder uses streaming internally
):
    # Each transaction is decoded
    print(f"Function: {tx['decoded_func']}")
    print(f"Args: {tx['decoded_data']}")
```

## Low-Level Pagination

The legacy standalone streaming services (`services/fetch_all_streaming.py`,
`StreamingDecoder`, `ChunkedBlockFetcher`) were removed. Pagination is
implemented once in `services/pagination.py` (`iter_pages` / `iter_items` /
`collect_all` over `Scanner.fetch_page` cursors) and consumed by the
`ChainscanClient` streaming methods — use those instead of any direct
service-level entrypoint.

## Migration Guide

### From Bulk Fetch to Streaming

**Before:**
```python
# Old approach - all in memory
transactions = await client.get_all_transactions(whale_address)

for tx in transactions:
    await process_transaction(tx)
```

**After:**
```python
# New approach - streaming
async for batch in client.iter_transactions_streaming(
    whale_address,
    from_block=0,
    to_block='latest',
    batch_size=1000
):
    for tx in batch:
        await process_transaction(tx)
```

### Backward Compatibility

All existing bulk fetch methods remain available and work as before:
```python
# Still works - uses streaming internally but returns all at once
transactions = await client.get_all_transactions(whale_address)
```

## Best Practices

1. **Use appropriate batch size**
   - Default (1000) works for most cases
   - Increase for high-throughput pipelines (2000-5000)
   - Decrease for memory-constrained environments (100-500)

2. **Handle errors per batch**
   ```python
   async for batch in client.iter_transactions_streaming(address):
       try:
           await process_batch(batch)
       except Exception as e:
           logger.error(f"Failed to process batch: {e}")
           # Continue with next batch
   ```

3. **Monitor progress**
   ```python
   async def on_progress(fetched, **kwargs):
       if fetched % 10000 == 0:
           print(f"Checkpoint: {fetched} items processed")
   ```

4. **Use streaming for exports**
   - CSV exports
   - Database inserts
   - Data transformations
   - Analytics pipelines

## Technical Details

### Memory Efficiency

Streaming achieves constant memory by:
1. Fetching pages from API
2. Deduplicating within batch window
3. Sorting batch
4. Yielding batch
5. Discarding batch after yield
6. Repeating for next batch

Peak memory = `batch_size * avg_item_size + internal_buffers`

### Deduplication

Deduplication is performed incrementally:
- Items are deduplicated across batches (global seen set)
- No duplicates are yielded
- Dedup state is maintained throughout iteration

### Sorting

Items are sorted per batch before yielding:
- Each batch is sorted by (blockNumber, transactionIndex)
- Overall order is maintained across batches
- Final result is fully sorted

### Paging Strategies

All paging strategies supported:
- **Paged**: Standard page-based pagination
- **Sliding**: Sliding window for Etherscan
- **Sliding_bi**: Bidirectional sliding (if available)

## Troubleshooting

**Q: Streaming is slow**
- Increase `batch_size` to reduce API calls
- Check network latency
- Verify rate limiting isn't throttling requests

**Q: Running out of memory despite streaming**
- Reduce `batch_size`
- Check for accumulation in processing code
- Verify batch processing doesn't store results

**Q: Getting duplicates**
- This should not happen - file a bug report
- Deduplication is handled automatically

**Q: Need to access all items at once**
- Accumulate batches manually if needed:
  ```python
  all_items = []
  async for batch in client.iter_transactions_streaming(address):
      all_items.extend(batch)
  ```
- Or use traditional bulk fetch:
  ```python
  all_items = await client.get_all_transactions(address)
  ```

## See Also

- [Progress Callbacks](PROGRESS_CALLBACKS.md)
