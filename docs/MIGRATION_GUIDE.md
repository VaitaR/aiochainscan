# Migration guide

The supported public entrypoint is `ChainscanClient`. Earlier top-level facade
functions, the legacy `Client` class, module objects, context helpers, and URL
builder entrypoints have been removed.

## Replace top-level functions

Before:

```python
from aiochainscan import get_balance

balance = await get_balance('eth', 'main', address)
```

After:

```python
from aiochainscan import ChainscanClient


async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    balance = await client.get_balance(address)
```

Keeping one client open reuses its connection pool, rate limiter, and retry
policy across requests.

## Replace the legacy client and modules

Before:

```python
client = Client.from_config('eth', 'main')
transactions = await client.account.get_transactions(address)
await client.close()
```

After:

```python
async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    transactions = await client.get_transactions(address)
```

Use methods on `ChainscanClient` directly. There is no public `account`,
`contract`, `block`, `token`, `stats`, or `proxy` module object.

## Scanner configuration

The factory takes a scanner and a chain name or chain ID:

```python
etherscan = ChainscanClient.from_config('etherscan', 'ethereum')
blockscout_v1 = ChainscanClient.from_config('blockscout', 'ethereum')
blockscout_v2 = ChainscanClient.from_config('blockscout_v2', 1)
```

Defaults:

- `etherscan` selects v2.
- `blockscout` selects v1.
- `blockscout_v2` is an alias for Blockscout v2.

Pass `scanner_version='v1'` or `scanner_version='v2'` only when an explicit
version is required.

## Pagination changes

Single-page methods remain single-page operations:

```python
page = await client.get_transactions(address)
logs = await client.get_logs(contract_address, from_block=20_000_000)
```

Use `get_all_*()` to collect an entire result, or a streaming iterator for large
histories:

```python
all_transactions = await client.get_all_transactions(address)

async for batch in client.iter_transactions_streaming(address, batch_size=1_000):
    await store(batch)
```

The same distinction applies to logs and other paginated endpoints. Streaming
does not make an unsupported provider endpoint available.

## Low-level operations

If no convenience method exists, use `Method` with `client.call()`:

```python
from aiochainscan import Method

result = await client.call(Method.CONTRACT_VERIFY_STATUS, guid=guid)
```

## Imports

Use public imports from the package root:

```python
from aiochainscan import (
    ChainscanClient,
    ChainscanClientApiError,
    ChainscanNetworkError,
    Method,
    PaginationDataLossError,
)
```

Internal modules may change without a deprecation cycle.
