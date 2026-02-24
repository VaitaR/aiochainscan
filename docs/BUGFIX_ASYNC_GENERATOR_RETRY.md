# Bugfix: Async Generator Retry Architecture

**Date**: 2026-02-24
**Status**: ✅ Fixed

---

## 🎯 Problem Statement

Retry decorators don't work properly with async generators because Tenacity considers
the generator "successful" as soon as the generator object is returned:

```python
@retry(...)  # This wraps GENERATOR CREATION, not iteration!
async def iter_transactions(...) -> AsyncIterator[dict]:
    yield tx  # Errors here are NOT retried!
```

If a network error occurs on page 100 during `async for`, the error escapes to the user -
Tenacity already finished.

---

## ✅ Solution Applied

### 1. Architecture Verification

The codebase already had the correct architecture:
- **`iter_transactions()`** for BlockScout V2 uses `self._network.request()` for each page
- **`iter_transactions()`** for Etherscan uses `self.call()` which goes through scanner → network
- **`Network.request()`** wraps calls with `self._retry_policy.run(do_request)`
- **`StreamingDecoder`** wraps batch fetches with `self.retry.run(_do_fetch)`

### 2. Bug Found: Missing Exception Type

The default `TenacityRetryAdapter` in `Network.__init__` was missing `ChainscanNetworkError`
from its retry exceptions list.

**Fix**: Added `ChainscanNetworkError` to the default retry exceptions in [network.py](../aiochainscan/network.py#L117-L132):

```python
# Before:
retry_exceptions=(
    ChainscanRateLimitError,
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
),

# After:
retry_exceptions=(
    ChainscanRateLimitError,
    ChainscanNetworkError,  # Added!
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
),
```

---

## 📁 Files Modified

1. **[network.py](../aiochainscan/network.py)**
   - Added `ChainscanNetworkError` import
   - Added `ChainscanNetworkError` to default retry exceptions

2. **[test_iter_transactions_retry.py](../tests/test_iter_transactions_retry.py)**
   - Added comprehensive tests verifying:
     - Network layer has `ChainscanNetworkError` in retry exceptions
     - Each page fetch goes through retry-wrapped `Network.request()`
     - Integration test showing retry fires on transient error at page 3
     - Test verifying retry exhaustion propagates error to user

---

## 🧪 Test Results

```
pytest tests/test_iter_transactions_retry.py -v
========== 11 passed in 0.20s ==========
```

All tests pass including:
- `test_network_layer_has_retry_configured` - verifies ChainscanNetworkError in retry exceptions
- `test_retry_fires_on_transient_error_during_iteration` - proves retry works at page 3
- `test_retry_exhaustion_propagates_error` - verifies proper error propagation after retries exhausted

---

## 🔍 Architecture Summary

The retry architecture is correctly designed:

```
User Code
    ↓
client.iter_transactions()
    ↓ (for each page)
Network.request()
    ↓
_retry_policy.run(do_request)  ← Retry happens HERE (per-page)
    ↓
httpx.get/post
    ↓
API Response
```

Key points:
1. **BlockScout V2**: Each page calls `self._network.request()` which has retry
2. **Etherscan**: Each page calls `self.call()` → `scanner.call()` → `network.get()` → retry
3. **StreamingDecoder**: Uses `self.retry.run(_do_fetch)` for each batch
4. **No decorator on generator**: Retry happens INSIDE the loop, not on generator creation

---

## ⚠️ Known Issue (Out of Scope)

The code passes `self._network._http2` (a boolean flag) where `HttpClient` is expected:
```python
http_client = self._network._http2  # This is a boolean, not an HttpClient!
decoder = StreamingDecoder(..., http=http_client, ...)  # type: ignore[arg-type]
```

This is a pre-existing issue that doesn't affect retry behavior since the retry
happens at a higher layer. Marked for future cleanup.
