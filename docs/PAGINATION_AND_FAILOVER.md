# Pagination, completeness and failover

Two guarantees that are easy to state and expensive to implement by hand: a
`get_all_*` call returns *everything*, and a provider that stops working does
not stop the program. This file is the contract behind both.

For the memory-side view of the same machinery — batches, backpressure,
progress — see [Streaming pattern](STREAMING_PATTERN.md).

## What returns one page and what returns everything

- `get_transactions()` returns one page.
- `get_logs()` returns one page, subject to provider limits.
- `get_token_holders()` returns one page.
- `get_all_*()` collects all pages into a list.
- `iter_*_streaming()` yields batches and avoids materializing the full result.

## The completeness guarantee

`get_all_*()` and `iter_*_streaming()` take `guarantee_complete`, which
defaults to `True`: the call returns every matching record or raises.

Explorers cap a result window — Etherscan and Blockscout v1 both at
`page * offset` 10 000 — and answer a capped query with a short page that is
indistinguishable from the end of the data. There is no error to catch and no
flag in the payload, which is why a hand-written page loop over a busy address
silently returns part of the history. The library detects the cap and splits
the block range until every part fits under it.

```python
# Complete, or an exception — the default.
transfers = await client.get_all_token_transfers(address)

# Opt out: fewer requests on wide ranges, truncation possible and silent.
transfers = await client.get_all_token_transfers(address, guarantee_complete=False)
```

Detection is scanner-declared, never guessed: each scanner declares the window
it was *measured* to enforce, and a cursor-paginated provider (Blockscout v2,
NodeReal) declares none, because an opaque server cursor runs to exhaustion and
has nothing to overflow. On those providers the flag is inert — there is no cap
to work around.

Two failures can end the walk, and they mean different things:

- **`PaginationDataLossError`** — the range was narrowed until a *single block*
  still exceeded the cap. Splitting worked and ran out. Carries `start_block`,
  `end_block`, `api_limit`, `items_fetched`.
- **`CompletenessUnavailableError`** — the endpoint has no range to split on
  this provider. A token-holder list has no block dimension, so narrowing
  cannot apply at all. `exc.alternatives` names the providers that serve the
  method completely, computed from the scanner registry rather than hardcoded.

Both carry `confirmed`: `True` means records were definitely cut off (the
provider offered a continuation at the cap, or refused the request outright),
`False` means the window came back exactly full and the API offers no way to
tell truncation from a clean end. Calling that second case confirmed loss would
be a false error on possibly-correct data, so the message says *possibly*
truncated.

The visible break this creates: `get_all_token_holders()` on Etherscan for a
token with 10 000 or more holders now raises instead of quietly returning the
first 10 000. The remedy is in the message — switch to Blockscout or NodeReal,
which serve the list to exhaustion, or pass `guarantee_complete=False` to
accept truncation deliberately.

### Costs

Up to one extra pass over each overflowing window (the truncated attempt is
discarded rather than yielded, so nothing duplicates), a buffer bounded by the
provider's window, and one unnecessary split for a range holding exactly the
cap.

## Streaming and DataFrames

Use streaming for large histories — memory stays flat regardless of account
size:

```python
async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
    async for batch in client.iter_transactions_streaming(address, batch_size=1_000):
        await store(batch)
```

The `data` extra adds DataFrame exports. These methods paginate and materialize
their result:

```python
async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    frame = await client.get_transactions_df(address)
```

## Multi-provider failover

`ChainscanPool` composes several providers for the same chain into one client
with the full `ChainscanClient` surface. Providers are listed in priority
order; the pool routes every call to the best available one:

```python
from aiochainscan import ChainscanPool

async with ChainscanPool.from_config(
    [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]
) as pool:
    balance = await pool.get_balance(address)  # served by etherscan
    pool.last_provider                        # 'etherscan/ethereum'
```

[`examples/08_provider_failover.py`](../examples/08_provider_failover.py) runs
this end to end, including the switch.

### Routing semantics

- **Sticky provider.** The provider that last answered keeps serving while it
  is healthy — no ping-ponging between providers.
- **Classified failover.** Rate limits, network/5xx errors (after the
  transport retries are exhausted), missing API keys and plan restrictions
  ("chain not on the free plan") switch to the next provider with a
  `ChainscanProviderSwitchWarning`. Bad arguments, not-found answers and data
  errors are fatal and propagate immediately.
- **Cooldown.** A failed provider is skipped without a single HTTP attempt for
  a class-specific window — rate limit `max(retry_after, 30s)`, transient 10s,
  auth 600s, plan restriction 3600s, all constructor-tunable. After the
  cooldown the provider gets one half-open trial.
- **Capability routing.** A provider that does not declare a method is routed
  around silently; the pool's coverage is the union of its members.
- **Pagination binding.** `get_all_*` / `iter_*_streaming` calls are pinned to
  one provider for their whole run — switching mid-pagination would corrupt
  opaque cursors. Failover happens only if the very first page fails.
- **No duplicated retries.** The pool reacts only to exceptions that survived
  each member client's own retry policy.

`from_config` excludes providers it cannot even construct (an unconfigured API
key, say) with a warning, and raises only when no provider could be built at
all.

When every provider fails or is cooling, `ProviderPoolExhaustedError` carries
the ordered `(provider, exception)` attempts. All pool state is per-instance;
`last_provider`, `provider_states()` and `reset_cooldowns()` expose and reset
it.
