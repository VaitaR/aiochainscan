# BlockScout V2 Bulk Fetch Fix

## Summary

This document describes the fix for the "split-brain" bug in mass data fetching where BlockScout V2 API was silently bypassed in favor of the legacy V1 API.

## Problem

When a user configured `blockscout_v2` as their scanner:

```python
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
```

The high-level methods like `iter_transactions()` correctly used the V2 API. However, bulk fetching functions (`fetch_all()`, `fetch_all_transactions_streaming()`) bypassed the scanner abstraction entirely and went directly to legacy service functions that use V1 API parameters (`module=account&action=txlist`).

### Root Cause

1. `fetch_all()` in [unified_fetch.py](aiochainscan/services/unified_fetch.py) called `get_normal_transactions()` directly
2. `get_normal_transactions()` in [account.py](aiochainscan/services/account.py) uses `EndpointBuilder` with hardcoded V1 parameters
3. `EndpointBuilder` has no awareness of scanner type
4. BlockScoutV2Scanner's modern API (`/api/v2/addresses/{address}/transactions`) was never invoked

### Impact

- Users thought they were using V2 API but were silently using V1
- V2-specific features like cursor-based pagination (`next_page_params`) were not utilized
- V2 API benefits (better rate limiting, richer responses) were lost

## Solution

### Approach: Scanner-Aware Routing

The fix adds scanner-aware routing to bulk fetch functions:

1. **Detection Function**: `_is_blockscout_v2(api_kind, scanner)` determines if V2 should be used
2. **V2 Fetch Path**: `_fetch_all_via_v2_scanner()` uses scanner's native API with cursor pagination
3. **Optional Scanner Parameter**: `fetch_all()` and streaming functions accept a `scanner` parameter

### Key Changes

#### [aiochainscan/services/unified_fetch.py](aiochainscan/services/unified_fetch.py)

```python
# New detection function
def _is_blockscout_v2(api_kind: str, scanner: Scanner | None) -> bool:
    """Check if we should use BlockScout V2 API."""
    if scanner is not None:
        scanner_name = getattr(scanner, 'name', '')
        scanner_version = getattr(scanner, 'version', '')
        if scanner_name == 'blockscout' and scanner_version == 'v2':
            return True
    return api_kind == 'blockscout_v2'

# New V2 fetch function
async def _fetch_all_via_v2_scanner(
    data_type: DataType,
    address: str,
    scanner: Scanner,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    """Fetch all data using BlockScout V2 scanner's native API."""
    # Uses cursor-based pagination (next_page_params)
    ...

# Updated fetch_all signature
async def fetch_all(
    ...,
    scanner: Scanner | None = None,  # New parameter
) -> list[dict[str, Any]]:
    # Route to V2 when appropriate
    if _is_blockscout_v2(api_kind, scanner) and scanner is not None:
        if data_type == 'transactions':
            return await _fetch_all_via_v2_scanner(...)
    # Fall back to legacy path
    ...
```

#### [aiochainscan/services/fetch_all_streaming.py](aiochainscan/services/fetch_all_streaming.py)

```python
# New V2 streaming function
async def _stream_v2_transactions(
    address: str,
    scanner: Scanner,
    batch_size: int = 1000,
    ...
) -> AsyncIterator[list[dict[str, Any]]]:
    """Stream transactions using BlockScout V2's cursor pagination."""
    ...

# Updated streaming function signature
async def fetch_all_transactions_streaming(
    ...,
    scanner: Scanner | None = None,  # New parameter
) -> AsyncIterator[list[dict[str, Any]]]:
    # Route to V2 when appropriate
    if _is_blockscout_v2(api_kind, scanner) and scanner is not None:
        async for batch in _stream_v2_transactions(...):
            yield batch
        return
    # Fall back to legacy path
    ...
```

#### [aiochainscan/core/client.py](aiochainscan/core/client.py)

```python
# Updated iter_transactions_streaming to pass scanner
async for batch in fetch_all_transactions_streaming(
    ...,
    scanner=self._scanner,  # Now passed for proper V2 routing
):
    yield batch
```

#### [aiochainscan/services/scanner_fetcher.py](aiochainscan/services/scanner_fetcher.py) (New)

New module providing scanner-aware page fetching utilities:

```python
class ScannerAwarePageFetcher:
    """Scanner-aware page fetcher that routes through the scanner abstraction."""

    async def fetch_transactions_page(
        self,
        address: str,
        page: int = 1,
        offset: int = 100,
        next_page_params: dict | None = None,
    ) -> tuple[list[dict], dict | None]:
        """Fetch a page using the appropriate API version."""
        ...
```

## Verification

### Unit Tests

New test file [tests/test_split_brain_fix.py](tests/test_split_brain_fix.py):

- `TestBlockScoutV2Detection` - V2 detection via api_kind and scanner
- `TestScannerFetcher` - ScannerAwarePageFetcher properties
- `TestUnifiedFetchV2Routing` - fetch_all routes to V2 when scanner provided
- `TestV2PaginationFlow` - V2 cursor pagination works correctly

### Integration Test

```python
import asyncio
from aiochainscan.core.client import ChainscanClient

async def test():
    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # This now correctly uses V2 API with cursor pagination
    async for tx in client.iter_transactions('0xd8dA...'):
        print(tx['hash'])

    # Streaming also uses V2 API
    async for batch in client.iter_transactions_streaming('0xd8dA...'):
        process_batch(batch)

asyncio.run(test())
```

## Backward Compatibility

- **Public API unchanged**: No breaking changes to public methods
- **V1 APIs unaffected**: Etherscan and BlockScout V1 continue to work
- **Graceful fallback**: If V2 path fails, falls back to legacy path

## Related Files

- [aiochainscan/services/unified_fetch.py](aiochainscan/services/unified_fetch.py) - Main fix
- [aiochainscan/services/fetch_all_streaming.py](aiochainscan/services/fetch_all_streaming.py) - Streaming fix
- [aiochainscan/services/scanner_fetcher.py](aiochainscan/services/scanner_fetcher.py) - New utility module
- [aiochainscan/core/client.py](aiochainscan/core/client.py) - Client updates
- [tests/test_split_brain_fix.py](tests/test_split_brain_fix.py) - New tests
