---
name: aiochainscan
description: Query blockchain explorer APIs (Etherscan, BlockScout, NodeReal) from async Python with the aiochainscan library — balances, full transaction/transfer/log history, token holders, contract ABIs and decoded calls, across 36 chains. Use when writing or reviewing code that reads on-chain data through a block explorer, exports a wallet or token history, or needs provider failover and exact Wei/token amounts.
license: MIT
---

# aiochainscan

Async Python client for block-explorer APIs behind one interface.

```bash
pip install aiochainscan             # pure Python; ABI decoding needs no extra
pip install "aiochainscan[data]"     # + Polars DataFrame exports
pip install "aiochainscan[mcp]"      # + MCP server (python -m aiochainscan.mcp_server)
pip install "aiochainscan[fastabi]"  # + Rust ABI decoder (bulk decoding)
```

## The four rules that decide whether the code is correct

1. **`ChainscanClient` is the entire public API.** Construct it with
   `ChainscanClient.from_config(scanner, network)` inside `async with`.
   There is no legacy `Client`, no facade, no URL builder to call.
2. **`get_*` returns ONE page.** Complete data comes from `get_all_*`
   (materialized) or `iter_*_streaming` (constant memory). A single
   transactions page is ~50–100 items; a logs page is capped at ~1000.
3. **Money is a Wei string, never a float.** Convert with `wei_to_ether` /
   `to_decimal_amount` (exact `Decimal`). `int(wei) / 10**18` is a bug.
4. **Provider coverage differs; the interface does not.** A method the
   configured scanner does not declare raises `MethodNotDeclaredError` —
   pick the provider by the method you need
   ([references/provider-selection.md](references/provider-selection.md)).

```python
from aiochainscan import ChainscanClient, wei_to_ether

async with ChainscanClient.from_config('blockscout', 'ethereum') as client:
    wei = await client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
    eth = wei_to_ether(wei)                       # Decimal, exact
    txs = await client.get_all_transactions('0xd8dA…')   # every transaction
```

## Completeness is a guarantee, not a hope

`get_all_*` and `iter_*_streaming` take `guarantee_complete` (default
`True`): they return **every** matching record or raise. Providers cap
results (Etherscan: 10 000 per `page * offset`, 1000 per page) and a capped
answer is indistinguishable from the end of the data, so the library splits
block ranges adaptively rather than trusting a short page.

- `PaginationDataLossError` — a single block exceeds the cap.
- `CompletenessUnavailableError` — the endpoint has no range to split (token
  holders on Etherscan); `.alternatives` names providers that can serve it.
- `guarantee_complete=False` restores fast, possibly-truncated behaviour.

Never paginate by hand with `page=`/`offset=` to work around this.

## Choosing a provider

| Scanner | Key | Methods (of 33) | Pick it for |
|---|---|---|---|
| `etherscan` v2 | `ETHERSCAN_KEY` | 33 | full surface, all chains; holder endpoints need PRO |
| `blockscout` v1 | none | 31 | widest keyless surface |
| `blockscout_v2` | none | 11 | keyless, cursor-paginated, complete holder lists |
| `nodereal` v1 | `NODEREAL_KEY` | 25 (BSC only) | keyless-free BSC ABI/source/internal txs |

Keys are read from the environment or `.env` — never pass them as literals.
For automatic failover across providers on the same chain, use
`ChainscanPool.from_config([('etherscan', 'ethereum'), ('blockscout', 'ethereum')])`.

## Cross-provider field names

Raw responses stay provider-native (`timeStamp` vs `timestamp`). Code that
must work on more than one provider should use the `*_normalized` variants
(`get_all_transactions_normalized`, `iter_logs_normalized`, …): frozen
dataclasses from `aiochainscan.domain.normalized` with typed fields, `None`
where a provider genuinely has no equivalent, and the untouched provider dict
kept in `.provider_data`.

## Habits that keep the code correct

- Keep **one client open** for many requests — it owns the connection pool,
  rate limiter and retry policy. Close it via `async with`.
- Do **not** wrap calls in your own retry loop; retries and rate limiting are
  built in and a second layer doubles the request budget.
- ENS `lookup_address` returns `None` for unregistered addresses — guard it.
- In DataFrames, Wei belongs in a `Utf8` column: `Int64` overflows above
  ~9.2 ETH.

## References

- [references/provider-selection.md](references/provider-selection.md) —
  method-by-provider coverage, chains, keys, pagination caps.
- [references/recipes.md](references/recipes.md) — full history export,
  provider switching, exact amounts, logs, holders, contracts, errors,
  self-hosted instances, MCP server.

Authoritative source when a doc and the code disagree: the scanner
declarations in `aiochainscan/scanners/` (repo:
https://github.com/VaitaR/aiochainscan).
