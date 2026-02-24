# Chunked Block Fetcher Strategy

## Overview

The **chunked strategy** is a new fetching strategy designed to prevent database timeouts when querying large block ranges on blockchain explorers like Etherscan and BlockScout.

## Problem Statement

When fetching logs or transactions across very large block ranges (e.g., from block 0 to latest) for popular contracts, blockchain explorers often return **gateway timeout errors (502, 503, 504)** BEFORE the pagination limit (10k results) is reached. This happens because:

1. The database query itself times out on the explorer's backend
2. Popular contracts have millions of events/transactions
3. Wide block ranges create expensive database queries

## Solution: Block Range Chunking

The chunked fetcher splits large block ranges into smaller, manageable chunks and fetches them in parallel with controlled concurrency:

```python
# User requests: blocks 0 to 20,000,000
# System automatically splits into chunks:
# Chunk 1: 0 - 99,999
# Chunk 2: 100,000 - 199,999
# Chunk 3: 200,000 - 299,999
# ... and so on (200 chunks total)
```

Each chunk is small enough that the database query completes successfully, then all results are combined, deduplicated, and sorted.

## When to Use Chunked Strategy

### ✅ Use `strategy='chunked'` when:

- **Block range > 500k blocks** (especially for active contracts)
- **Querying from block 0 to latest** for historical analysis
- **Getting gateway timeout errors** (502, 503, 504) with other strategies
- **Popular contracts** like USDT, USDC, Uniswap, etc.
- **Need complete historical data** without missing records

### ❌ Don't use chunked when:

- **Recent blocks only** (< 100k blocks) - use `fast` strategy instead
- **Low-activity contracts** - use `fast` strategy
- **Quick queries** - chunked adds overhead for splitting/combining
- **Real-time monitoring** - use `fast` for lower latency

## Usage Examples

### Basic Usage

```python
from aiochainscan.core.client import ChainscanClient
from aiochainscan.services.fetch_all import fetch_all

client = ChainscanClient.from_config('etherscan', 'ethereum')

# Fetch all USDT Transfer events from deployment to block 20M
logs = await fetch_all(
    data_type='logs',
    address='0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT
    start_block=4_634_748,  # USDT deployment block
    end_block=20_000_000,
    api_kind='eth',
    network='ethereum',
    api_key=client.api_key,
    http=client._network._http,
    endpoint_builder=client._network._url_builder,
    strategy='chunked',       # Enable chunked strategy
    max_offset=100_000,       # Chunk size (100k blocks per chunk)
    max_concurrent=3,         # Max parallel chunks
)

print(f"Fetched {len(logs):,} events")
```

### Advanced: Direct Fetcher Usage

For more control, use `ChunkedBlockFetcher` directly:

```python
from aiochainscan.services.chunked_fetcher import ChunkedBlockFetcher

fetcher = ChunkedBlockFetcher(
    http=client._network._http,
    endpoint_builder=client._network._url_builder,
    chunk_size=50_000,           # 50k blocks per chunk
    rate_limiter=client._rate_limiter,
    retry=client._retry_policy,
    max_concurrent_chunks=4,     # Fetch 4 chunks in parallel
)

# Progress tracking
def on_progress(chunk_num, total_chunks, items_fetched):
    print(f"Chunk {chunk_num}/{total_chunks}: {items_fetched} items")

logs = await fetcher.fetch_logs(
    address='0x...',
    from_block=0,
    to_block='latest',          # Automatically resolved to current block
    api_kind='eth',
    network='ethereum',
    api_key='your_key',
    on_chunk_complete=on_progress,
)
```

### Progress Monitoring

```python
# Track progress with callback
def track_progress(chunk_num, total_chunks, items_fetched):
    percent = (chunk_num / total_chunks) * 100
    print(f"Progress: {percent:.1f}% - Chunk {chunk_num}/{total_chunks} ({items_fetched} items)")

logs = await fetcher.fetch_logs(
    address='0x...',
    from_block=0,
    to_block=10_000_000,
    api_kind='eth',
    network='ethereum',
    api_key='key',
    on_chunk_complete=track_progress,
)
```

## Configuration Parameters

### `chunk_size` (via `max_offset`)

Controls how many blocks to fetch per chunk.

**Guidelines:**
- **Very active contracts** (USDT, USDC): `25_000 - 50_000` blocks
- **Moderately active**: `100_000 - 200_000` blocks
- **Less active**: `250_000 - 500_000` blocks

**Default:** `100_000` blocks

### `max_concurrent` (via `max_concurrent`)

Controls how many chunks to fetch in parallel.

**Guidelines:**
- **Free API keys**: `1 - 2` (avoid rate limits)
- **Paid API keys**: `3 - 5` (balance speed vs rate limits)
- **High-tier accounts**: `5 - 10` (maximum speed)

**Default:** `3` concurrent chunks

## How It Works

### 1. Block Range Splitting

```python
# Input: from_block=0, to_block=250_000, chunk_size=100_000
# Output chunks:
[
    (0, 99_999),
    (100_000, 199_999),
    (200_000, 250_000)
]
```

### 2. Parallel Fetching

Chunks are fetched in parallel with a semaphore controlling concurrency:

```python
async with semaphore:  # Max 3 concurrent
    chunk_1_data = await fetch_chunk(0, 99_999)
    chunk_2_data = await fetch_chunk(100_000, 199_999)
    # etc.
```

### 3. Deduplication

Results are deduplicated using `transactionHash:logIndex` as the unique key:

```python
# If a transaction spans chunk boundaries, it might appear in both
# Deduplication ensures it only appears once in final results
```

### 4. Sorting

Final results are sorted by `(blockNumber, logIndex)` for stable ordering:

```python
logs.sort(key=lambda x: (x['blockNumber'], x['logIndex']))
```

## Comparison with Other Strategies

| Strategy | Best For | Speed | Memory | Timeout Risk |
|----------|----------|-------|--------|--------------|
| **chunked** | Large ranges, historical data | Medium | High | Very Low |
| **fast** | Recent blocks, moderate ranges | Fast | Low | Medium |
| **basic** | Debugging, unreliable networks | Slow | Low | Low |

### Example Scenarios

#### Scenario A: Recent 10k blocks
```python
# Best: fast strategy
logs = await fetch_all(..., strategy='fast', start_block=19_000_000, end_block=19_010_000)
```

#### Scenario B: 5 million blocks
```python
# Best: chunked strategy
logs = await fetch_all(..., strategy='chunked', start_block=0, end_block=5_000_000)
```

#### Scenario C: Network issues
```python
# Best: basic strategy
logs = await fetch_all(..., strategy='basic')
```

## Performance Characteristics

### Time Complexity
- **Setup overhead**: O(n/chunk_size) - splitting into chunks
- **Network calls**: O(n/chunk_size) - one call per chunk
- **Deduplication**: O(m) where m = total results
- **Sorting**: O(m log m)

### Memory Usage
- All chunks are fetched into memory before deduplication
- For 10M blocks with 100k chunk_size = 100 chunks
- Each chunk might return up to 10k results
- Worst case: ~1M items in memory (manageable)

### Network Efficiency
- Parallel fetching reduces total time
- Semaphore prevents overwhelming rate limits
- Each chunk is an independent API call

## Error Handling

The chunked fetcher inherits error handling from the underlying HTTP client:

1. **Rate limiting**: Controlled by `rate_limiter` parameter
2. **Retries**: Controlled by `retry` policy
3. **Timeouts**: Each chunk has independent timeout
4. **Gateway errors**: Small chunks avoid most timeout issues

## Limitations

1. **Not for internal_transactions**: Chunked strategy currently supports:
   - ✅ Logs (`data_type='logs'`)
   - ✅ Transactions (`data_type='transactions'`)
   - ❌ Internal transactions (falls back to `fast`)
   - ❌ Token transfers (falls back to `fast`)

2. **Memory consumption**: All results loaded into memory before deduplication

3. **API quota**: More chunks = more API calls (consider rate limits)

## Real-World Example

Fetching all Uniswap V2 Swap events from deployment to present:

```python
# Uniswap V2: UniswapV2Router02
uniswap_router = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
swap_signature = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"

client = ChainscanClient.from_config('etherscan', 'ethereum')

logs = await fetch_all(
    data_type='logs',
    address=uniswap_router,
    start_block=10_000_835,  # Uniswap V2 deployment
    end_block='latest',
    api_kind='eth',
    network='ethereum',
    api_key=client.api_key,
    http=client._network._http,
    endpoint_builder=client._network._url_builder,
    topics=[swap_signature],
    strategy='chunked',
    max_offset=50_000,  # 50k blocks/chunk (very active contract)
    max_concurrent=3,    # 3 parallel chunks
)

print(f"Fetched {len(logs):,} Swap events")
# Typical: 5M+ events, ~200 chunks, ~10-15 minutes with API key
```

## Best Practices

1. **Start conservative**: Begin with smaller `chunk_size` and increase if no timeouts
2. **Monitor rate limits**: Watch your API quota, adjust `max_concurrent` accordingly
3. **Use progress callback**: Implement `on_chunk_complete` for long-running queries
4. **Estimate first**: Query a small range to estimate total results before full fetch
5. **Cache results**: Store results to avoid re-fetching the same data

## See Also

- [examples/chunked_fetcher_demo.py](../examples/chunked_fetcher_demo.py) - Complete working examples
- [SMART_CONTRACT_API.md](SMART_CONTRACT_API.md) - Using chunked with SmartContract API
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - All strategy options

## Version

Added in: **aiochainscan v0.4.0**
