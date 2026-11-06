# Multi-provider failover pool (`core/pool.py`)

Agent reference for `ChainscanPool`. Read it before touching `core/pool.py`, failure
classification (`classify_failure` / `FailureKind` / an exception's `failure_kind`), or
anything the pool forwards. User-facing version:
[../PAGINATION_AND_FAILOVER.md](../PAGINATION_AND_FAILOVER.md#multi-provider-failover).

```python
from aiochainscan import ChainscanPool

# Priority order: etherscan preferred, blockscout rescues. Providers serve the
# SAME chain; kwargs (timeout, proxy, rate_limiter, ...) forward to every member.
async with ChainscanPool.from_config(
    [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]
) as pool:
    await pool.get_balance('0x...')          # full ChainscanClient surface, with failover
    async for batch in pool.iter_transactions_streaming('0x...'):
        ...                                   # pinned to ONE provider per call

    pool.last_provider                       # who answered last (sticky)
    pool.provider_states()                   # {label: available/cooldown/...}
    pool.reset_cooldowns()                   # operational escape hatch
```

## Failure classification

Fallback-eligible: rate limit, network/5xx after transport retries, missing key
(including HTTP 401/403 from the transport raise site, e.g. NodeReal's 401 on an invalid
path key or a WAF/proxy 403), plan restriction, method-not-declared. Fatal (propagate, no
switch): arguments, not-found, data contract. Classification is a lookup of the
exception's `failure_kind`, with a regex fallback. The pool never duplicates retries — it
reacts only to exceptions that survived each member client's tenacity `Network`.

## Semantics

- **Sticky**: the last successful provider keeps serving (no yo-yo when a higher-priority
  provider leaves cooldown).
- **Cooldown**: rate limit → `max(retry_after, 30s)`; transient → 10s; auth → 600s; plan
  restriction → 3600s (all constructor-tunable). Cooling providers are skipped without an
  HTTP attempt; after expiry they get one half-open trial (failure re-enters cooldown).
- **Pagination pinning**: `get_all_*` / `iter_*` / `iter_*_streaming` bind to one provider
  per call; only a first-page failure may restart on the next provider (cursor state is
  still empty then). Mid-pagination errors propagate but still cool the provider.
- **`from_config`** excludes unconstructible providers with a warning (missing key etc.);
  raises only when NO provider could be built.
- **Labels** are unique by construction: `scanner/network`, qualified with the version on
  a collision and then with an ordinal. Two members rendering one label make
  `last_provider`, the progress stamp and the switch warnings unreadable.
- **Transparency**: `last_provider`, a `provider=<label>` stamp in progress callbacks,
  `ChainscanProviderSwitchWarning` on switches, `ProviderPoolExhaustedError.attempts =
  [(provider, exception), ...]`. A switch that only stepped over a provider which never
  declared the method is routing, not failure, and warns about nothing — the same silence
  covers guaranteed calls routed straight to a completeness-capable member.
- All state is per-pool-instance — nothing global. `guarantee_complete` is forwarded to
  member clients.
