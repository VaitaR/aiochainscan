# Progress Callbacks

**Feature Status**: ✅ Implemented in v0.4.0+

Progress callbacks provide real-time feedback during long-running data fetching operations, allowing you to track progress, display progress bars, or log status updates.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Built-in Helpers](#built-in-helpers)
- [Custom Callbacks](#custom-callbacks)
- [Integration Points](#integration-points)
- [Performance Considerations](#performance-considerations)
- [Error Handling](#error-handling)
- [Examples](#examples)

## Overview

When fetching large datasets (e.g., all transactions for an old address), operations can take 1-2 minutes with no feedback, leaving users staring at a frozen terminal. Progress callbacks solve this by providing periodic updates during the fetch operation.

### Key Features

- **Non-blocking**: Callbacks are invoked asynchronously without blocking the fetch
- **Error-tolerant**: Exceptions in callbacks are caught and logged, not propagated
- **Flexible**: Support for console output, progress bars (tqdm/rich), logging, and custom solutions
- **Lightweight**: Callbacks are invoked once per page fetch (not per item)
- **Rate-limiting**: Built-in support for throttling expensive callbacks

## Quick Start

### Simple Console Progress

```python
from aiochainscan import ChainscanClient
from aiochainscan.utils.progress_helpers import console_progress

async def fetch_with_progress():
    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Use console_progress() for simple terminal output
    txs = await client.get_all_transactions(
        address='0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        on_progress=console_progress()
    )

    print(f"\n✅ Fetched {len(txs)} transactions")
    await client.close()
```

**Output**:
```
Progress: 5000/10000 (50.0%) - Block 18500000
```

### tqdm Progress Bar

```python
from aiochainscan.utils.progress_helpers import tqdm_progress

txs = await client.get_all_transactions(
    address=address,
    on_progress=tqdm_progress(desc="Fetching transactions")
)
```

**Output**:
```
Fetching transactions: 50%|█████     | 5000/10000 [00:30<00:30, 166.67it/s, block=18500000]
```

## Built-in Helpers

The `aiochainscan.utils.progress_helpers` module provides several ready-to-use progress callbacks:

### `console_progress(file=sys.stdout)`

Simple console output with carriage return (overwrites same line).

```python
from aiochainscan.utils.progress_helpers import console_progress

callback = console_progress()
```

**When to use**:
- Simple scripts
- Terminal applications
- Quick debugging

### `tqdm_progress(desc="Fetching", **tqdm_kwargs)`

Professional progress bar using tqdm (requires `pip install tqdm`).

```python
from aiochainscan.utils.progress_helpers import tqdm_progress

callback = tqdm_progress(
    desc="Fetching transactions",
    unit="tx",
    colour="green"
)
```

**When to use**:
- User-facing applications
- Data analysis scripts
- Jupyter notebooks

### `rich_progress(description="Fetching")`

Beautiful progress bars using rich (requires `pip install rich`).

```python
from aiochainscan.utils.progress_helpers import rich_progress

callback = rich_progress("Fetching transactions")
```

**When to use**:
- Modern terminal UIs
- Dashboard applications
- When aesthetics matter

### `logging_progress(logger_name="aiochainscan.progress")`

Logs progress updates using Python's logging module.

```python
import logging
from aiochainscan.utils.progress_helpers import logging_progress

logging.basicConfig(level=logging.INFO)
callback = logging_progress("myapp.progress")
```

**When to use**:
- Production applications
- Headless services
- When you need persistent logs

### `silent_progress()`

No-op callback that does nothing (useful as a default).

```python
from aiochainscan.utils.progress_helpers import silent_progress

callback = silent_progress()
```

**When to use**:
- Automated scripts
- Background jobs
- Testing

### `callback_with_interval(callback, min_interval_seconds=1.0)`

Rate-limits an existing callback to prevent overwhelming the system.

```python
from aiochainscan.utils.progress_helpers import (
    logging_progress,
    callback_with_interval
)

# Only log once per 5 seconds (instead of after every page)
callback = callback_with_interval(
    logging_progress(),
    min_interval_seconds=5.0
)
```

**When to use**:
- Expensive callbacks (database updates, network requests)
- High-frequency operations
- Resource-constrained environments

## Custom Callbacks

### Protocol Definition

All progress callbacks must adhere to the `ProgressCallback` protocol:

```python
from typing import Protocol

class ProgressCallback(Protocol):
    async def __call__(
        self,
        fetched: int,
        total_expected: int | None,
        current_block: int | None = None,
        current_page: int | None = None,
        operation: str = "fetch",
    ) -> None:
        """
        Args:
            fetched: Number of items fetched so far
            total_expected: Expected total (None if unknown)
            current_block: Current block number being processed
            current_page: Current page number
            operation: Operation type ("fetch", "decode", "chunk")
        """
        ...
```

### Example: Custom Callback

```python
async def my_progress_callback(
    fetched: int,
    total_expected: int | None,
    current_block: int | None = None,
    current_page: int | None = None,
    operation: str = "fetch",
) -> None:
    """Custom progress callback that logs to a file."""

    with open("progress.log", "a") as f:
        timestamp = datetime.now().isoformat()
        f.write(f"{timestamp} | {operation} | {fetched} items | block {current_block}\n")

# Use it
txs = await client.get_all_transactions(
    address=address,
    on_progress=my_progress_callback
)
```

### Example: Database Integration

```python
from sqlalchemy.ext.asyncio import AsyncSession

class DatabaseProgressTracker:
    def __init__(self, session: AsyncSession, job_id: str):
        self.session = session
        self.job_id = job_id

    async def __call__(
        self,
        fetched: int,
        total_expected: int | None,
        **kwargs
    ) -> None:
        """Update job progress in database."""

        await self.session.execute(
            "UPDATE jobs SET progress = :progress WHERE id = :id",
            {"progress": fetched, "id": self.job_id}
        )
        await self.session.commit()

# Use it
tracker = DatabaseProgressTracker(session, job_id="123")
txs = await client.get_all_transactions(
    address=address,
    on_progress=tracker
)
```

### Example: WebSocket Updates

```python
import websockets

async def websocket_progress_callback(
    fetched: int,
    total_expected: int | None,
    **kwargs
) -> None:
    """Send progress updates via WebSocket."""

    async with websockets.connect("ws://localhost:8765") as websocket:
        await websocket.send(json.dumps({
            "type": "progress",
            "fetched": fetched,
            "total": total_expected,
            "percentage": (fetched / total_expected * 100) if total_expected else None
        }))

# Use it
txs = await client.get_all_transactions(
    address=address,
    on_progress=websocket_progress_callback
)
```

## Integration Points

Progress callbacks are supported in the following methods:

### ChainscanClient Methods

```python
# High-level client methods (coming soon)
txs = await client.get_all_transactions(address, on_progress=callback)
logs = await client.get_all_logs(address, on_progress=callback)

# Streaming methods
async for tx in client.iter_transactions(address, on_progress=callback):
    process(tx)

async for log in client.iter_logs(address, on_progress=callback):
    process(log)
```

### Low-Level Services

```python
from aiochainscan.services.fetch_all import fetch_all_transactions_fast

# Direct service usage
txs = await fetch_all_transactions_fast(
    address=address,
    start_block=0,
    end_block=None,
    api_kind='eth',
    network='ethereum',
    api_key=api_key,
    http=http_client,
    endpoint_builder=endpoint_builder,
    on_progress=callback
)
```

### Chunked Block Fetcher

```python
from aiochainscan.services.chunked_fetcher import ChunkedBlockFetcher

fetcher = ChunkedBlockFetcher(
    http=http_client,
    endpoint_builder=endpoint_builder,
    chunk_size=100_000
)

logs = await fetcher.fetch_logs(
    address="0x...",
    from_block=0,
    to_block="latest",
    api_kind="eth",
    network="ethereum",
    api_key=api_key,
    on_chunk_complete=lambda chunk_num, total, items: print(f"Chunk {chunk_num}/{total}")
)
```

### Streaming Decoder

```python
from aiochainscan.services.streaming_decoder import StreamingDecoder

decoder = StreamingDecoder(
    api_kind='eth',
    network='ethereum',
    api_key=api_key,
    http=http_client,
    endpoint_builder=endpoint_builder
)

async for tx in decoder.stream_transactions(
    address=address,
    abi=contract_abi,
    on_progress=callback
):
    process(tx)
```

## Performance Considerations

### Callback Frequency

Progress callbacks are invoked **once per page fetch**, not per item. This means:

- **Etherscan**: ~1 call per 10,000 items (typical page size)
- **BlockScout**: ~1 call per 50-1000 items (varies by endpoint)
- **Chunked fetcher**: ~1 call per chunk (typically 100,000 blocks)

### Callback Performance

Your callback should be **lightweight and fast**:

✅ **Good** (fast operations):
- Console output (`print`)
- In-memory updates (counters, lists)
- Simple calculations

⚠️ **Be careful** (potentially slow):
- Database writes
- Network requests
- File I/O

❌ **Avoid** (blocking operations):
- Synchronous database calls
- Heavy computations
- Long-running HTTP requests

For expensive operations, use `callback_with_interval()` to rate-limit:

```python
from aiochainscan.utils.progress_helpers import callback_with_interval

# Expensive callback (database update)
async def update_db(fetched, total, **kwargs):
    await db.execute("UPDATE progress SET count = ?", (fetched,))
    await db.commit()

# Rate-limit to once per 5 seconds
limited_callback = callback_with_interval(update_db, min_interval_seconds=5.0)

txs = await client.get_all_transactions(address, on_progress=limited_callback)
```

### Memory Usage

Progress callbacks do not affect memory usage of the fetch operation itself. The callback only receives metadata (counts, block numbers), not the actual data.

## Error Handling

### Exception Handling

Exceptions in progress callbacks are **caught and logged** but do not stop the fetch operation:

```python
async def buggy_callback(fetched, total, **kwargs):
    if fetched > 5000:
        raise ValueError("Oops!")  # This won't crash the fetch

# Fetch continues despite callback error
txs = await client.get_all_transactions(address, on_progress=buggy_callback)
```

**Log output**:
```
WARNING:aiochainscan.services.paging_engine:Progress callback error: Oops!
```

### Best Practices

1. **Use try/except in your callback** for critical operations:

```python
async def safe_callback(fetched, total, **kwargs):
    try:
        await update_external_service(fetched, total)
    except Exception as e:
        logger.error(f"Failed to update external service: {e}")
        # Continue without crashing
```

2. **Test your callback separately** before integrating:

```python
# Unit test your callback
async def test_callback():
    await my_callback(100, 1000, current_block=18000000)
    # Verify expected behavior
```

3. **Use logging for debugging**:

```python
import logging

logger = logging.getLogger(__name__)

async def debug_callback(fetched, total, **kwargs):
    logger.debug(f"Progress: {fetched}/{total}, kwargs: {kwargs}")
```

## Examples

### Example 1: Multi-Stage Progress

Track progress across multiple stages (fetch → decode → save):

```python
class MultiStageProgress:
    def __init__(self):
        self.stage = "fetch"
        self.fetch_count = 0
        self.decode_count = 0

    async def __call__(self, fetched, total, operation="fetch", **kwargs):
        if operation == "fetch":
            self.fetch_count = fetched
            print(f"\r[FETCH] {fetched} items", end="", flush=True)
        elif operation == "decode":
            self.decode_count = fetched
            print(f"\r[DECODE] {fetched}/{self.fetch_count} items", end="", flush=True)

progress = MultiStageProgress()

# Fetch with progress
txs = await client.get_all_transactions(address, on_progress=progress)

# Later, during decoding
for i, tx in enumerate(txs):
    decoded = decode_transaction(tx, abi)
    if i % 100 == 0:
        await progress(i, len(txs), operation="decode")
```

### Example 2: Percentage-Based Updates

Only update when percentage changes significantly:

```python
class PercentageProgress:
    def __init__(self, update_interval=5):
        self.last_pct = 0
        self.update_interval = update_interval  # Update every 5%

    async def __call__(self, fetched, total, **kwargs):
        if total is None:
            return

        current_pct = int((fetched / total) * 100)

        if current_pct - self.last_pct >= self.update_interval:
            print(f"Progress: {current_pct}%")
            self.last_pct = current_pct

txs = await client.get_all_transactions(
    address=address,
    on_progress=PercentageProgress(update_interval=10)  # Every 10%
)
```

### Example 3: Combined Progress Tracking

Send progress to multiple destinations:

```python
class CombinedProgress:
    def __init__(self, *callbacks):
        self.callbacks = callbacks

    async def __call__(self, fetched, total, **kwargs):
        # Call all callbacks in parallel
        await asyncio.gather(*[
            cb(fetched, total, **kwargs)
            for cb in self.callbacks
        ])

# Combine console output, logging, and database updates
combined = CombinedProgress(
    console_progress(),
    logging_progress(),
    DatabaseProgressTracker(session, job_id)
)

txs = await client.get_all_transactions(address, on_progress=combined)
```

### Example 4: Conditional Progress

Different behavior based on context:

```python
async def smart_progress(fetched, total, current_block=None, **kwargs):
    """
    Show detailed progress in development, minimal in production.
    """
    if os.getenv("ENV") == "production":
        # Production: only log major milestones
        if fetched % 10000 == 0:
            logger.info(f"Fetched {fetched} items")
    else:
        # Development: detailed console output
        if total:
            pct = (fetched / total) * 100
            print(f"\rProgress: {fetched}/{total} ({pct:.1f}%) - Block {current_block}", end="")
        else:
            print(f"\rFetched: {fetched} items - Block {current_block}", end="")

txs = await client.get_all_transactions(address, on_progress=smart_progress)
```

## See Also

- [Examples](../examples/progress_callback_demo.py) - Complete working examples
- [Tests](../tests/test_progress_callbacks.py) - Unit tests demonstrating usage
- [Paging Engine](../aiochainscan/services/paging_engine.py) - Implementation details
- [Progress Helpers](../aiochainscan/utils/progress_helpers.py) - Built-in callback functions

---

**Next Steps**:
- Try `examples/progress_callback_demo.py` for hands-on examples
- Read `STREAMING_DECODER.md` for streaming data processing
- See `CHUNKED_STRATEGY.md` for handling large block ranges
