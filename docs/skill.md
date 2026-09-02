# aiochainscan - AI Agent Skill Card

> **For AI Agents**: how to use the `aiochainscan` library to query blockchain
> data (balances, transactions, tokens, logs, contracts, gas) over a unified API.
> Version facts below reflect **0.6.0**; method↔scanner declarations in
> `aiochainscan/scanners/` are authoritative.

## Ground rules

- **Public API is `ChainscanClient`-only.** Construct with
  `ChainscanClient.from_config(scanner, network)` or the keyword form
  `ChainscanClient(chain=..., provider=..., api_key=...)`.
- Balance/value/supply results are **Wei strings**. Convert with the exact
  `Decimal` helpers — never `int(wei) / 10**18` float division:

```python
from aiochainscan import format_ether, hex_to_int, to_iso, to_decimal_amount, wei_to_ether

ether  = wei_to_ether('1500000000000000000')       # Decimal('1.5')
usdc   = to_decimal_amount('1500000', decimals=6)  # Decimal('1.5')
n      = hex_to_int('0x1a')                        # 26 (hex | decimal | int)
iso    = to_iso('1609459200')                      # '2021-01-01T00:00:00+00:00'
```

## Scanner selection

| Scanner | Key | Declared methods | Notes |
|---------|-----|------------------|-------|
| `etherscan` v2 | `ETHERSCAN_KEY` required | **all 33** | most complete; holder list endpoints are PRO |
| `blockscout` v1 | none | 30 (Etherscan-like minus token holders) | some proxy calls may 400 per instance |
| `blockscout_v2` | none | 7: balance, transactions, token portfolio, contract ABI, block-by-number, token holders, holder count | cursor-paginated — the only provider that can serve a **complete** holder list |
| `nodereal` v1 | `NODEREAL_KEY` | 22, **BSC only** | JSON-RPC based |

Rule of thumb: quick keyless lookups → `blockscout_v2`; full keyless surface →
`blockscout` v1; anything else (logs on all networks, verify, stats, holders
top-N) → `etherscan`.

## Quick start (copy-paste ready)

```python
import asyncio
from aiochainscan import ChainscanClient

async def wallet_info(address: str):
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        balance_wei = await client.get_balance(address)
        txs = await client.get_transactions(address)          # single page (~50)
        tokens = await client.get_token_portfolio(address)    # all ERC-20 holdings
        return {"balance_eth": str(wei_to_ether(balance_wei)), "recent_tx": len(txs), "tokens": len(tokens)}

print(asyncio.run(wallet_info("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")))
```

With an Etherscan key: `export ETHERSCAN_KEY=...` **before** `from_config('etherscan', ...)`
— the key is validated at construction.

## Complete method surface (33 `Method` values)

| Convenience method | Returns |
|---|---|
| `get_balance(address)` | `str` (Wei) |
| `get_transactions(address)` / `get_all_transactions(address)` | `list[dict]` |
| `get_internal_transactions(address)` / `get_all_internal_transactions(...)` | `list[dict]` |
| `get_token_transfers(address)` / `get_all_token_transfers(...)` | `list[dict]` |
| `get_erc721_transfers(address)` / `get_erc1155_transfers(address)` | `list[dict]` |
| `get_token_portfolio(address)` / `get_nft_portfolio(address)` | `list[dict]` |
| `get_transaction(tx_hash)` / `get_transaction_status(tx_hash)` / `check_transaction_status(tx_hash)` | `dict` |
| `get_block(n)` / `get_block_reward(n)` / `get_block_countdown(n)` / `get_block_by_timestamp(ts)` | `dict` |
| `get_contract_abi(addr)` / `get_contract_source(addr)` / `get_contract_creation([addr])` | `str`/`dict`/`list[dict]` |
| `get_token_balance(wallet, token)` / `get_token_supply(token)` / `get_token_info(token)` | `str`/`str`/`dict` |
| `get_token_holders(token)` / `get_all_token_holders(token)` / `get_top_token_holders(token, limit)` / `get_token_holder_count(token)` | `list[dict]`/`int` |
| `get_logs(addr, from_block=...)` / `get_all_logs(...)` | `list[dict]` |
| `get_eth_price()` / `get_gas_oracle()` / `get_gas_estimate(gas_price)` / `get_eth_supply()` | `dict`/`dict`/`str`/`str` |
| `eth_call(to, data)` / `eth_get_balance(addr)` | `str` (hex) |
| `lookup_address(addr)` / `resolve_name(name)` / `lookup_addresses([...])` / `resolve_names([...])` | `str \| None`, `dict[str, str]` — ENS via BlockScout V2 |
| `wait_for_transaction(hash)` / `wait_for_verification(guid)` / `wait_for_block(n)` | poll until final; `ChainscanWaitTimeoutError` on expiry |
| `get_contract(addr)` → `.iter_events(name, limit=...)` | decoded events (needs EVENT_LOGS provider) |

Single-page getters return **one page**. `get_all_*()` materializes everything
(streaming aggregation underneath); for 1M+ item datasets prefer the constant-RAM
streaming form:

```python
async for batch in client.iter_transactions_streaming(address, batch_size=1000):
    await db.bulk_insert(batch)   # ~10MB RAM regardless of total size
```

`get_all_*` / `iter_*_streaming` take `guarantee_complete=True` (default): every
matching record is returned **or an exception is raised** — never silent
truncation. On a capped provider (Etherscan, 10k window) a token with ≥10k
holders raises `CompletenessUnavailableError` naming `blockscout_v2` as the
provider that can serve it completely; pass `guarantee_complete=False` only to
accept truncation deliberately.

## Response shapes differ per provider

```python
# blockscout_v2 transaction: from/to are NESTED dicts
tx["from"]["hash"], tx["to"]["hash"], tx["value"]  # Wei str, ISO timestamp

# etherscan transaction: FLAT strings
tx["from"], tx["to"], tx["value"], tx["timeStamp"]  # Wei str, unix-seconds str
```

## Errors

```python
from aiochainscan.exceptions import (
    ChainscanRateLimitError,        # retry with backoff
    ChainscanNetworkError,          # transport issues
    PaginationDataLossError,        # a single block exceeds the provider cap
    CompletenessUnavailableError,   # no splittable dimension on this provider
    MethodNotDeclaredError,         # ValueError subclass: scanner lacks the method
    ProviderPoolExhaustedError,     # failover pool: every member failed
)
```

`MethodNotDeclaredError` at call time = wrong scanner for that method — switch
scanner per the table above.

## Common patterns

```python
# Multi-chain keyless balance
for network in ("ethereum", "arbitrum", "base", "gnosis"):
    async with ChainscanClient.from_config("blockscout_v2", network) as client:
        print(network, format_ether(await client.get_balance(addr)))

# ENS
async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
    name = await client.lookup_address(addr)      # None when unregistered — guard it
    addr2 = await client.resolve_name("vitalik.eth")

# DataFrame export (pip install aiochainscan[data])
df = await client.get_transactions_df(address)    # ALL txs, auto-paginated
```

## Installation

```bash
pip install aiochainscan                 # pure Python, no Rust toolchain
pip install aiochainscan[fastabi]        # + Rust ABI decoder (optional accelerator)
pip install aiochainscan[data]           # + Polars DataFrames
pip install aiochainscan[mcp]            # + MCP server
pip install aiochainscan[fallback]       # + native keccak without fastabi
```

Note: a bare install decodes ABI/calldata on the pure-Python floor — no extra
needed. `[fallback]` only accelerates keccak; `[fastabi]` accelerates both.

## Tips for AI agents

1. `from_config` (or `chain=`/`provider=` kwargs) only; do not guess internal
   constructor fields.
2. Check the scanner table first — `blockscout_v2` declares only 7 methods.
3. `get_transactions`/`get_logs`/`get_token_holders` are single-page; use the
   `get_all_*`/`iter_*_streaming` forms for complete data.
4. Keep one client open for many requests — it reuses the connection pool, rate
   limiter, and retry policy. Close it (context manager) when done.
5. Wei values are strings; convert with `wei_to_ether`/`to_decimal_amount`, never
   float division.
6. ENS lookups return `None` for unregistered names — always guard.
7. Multi-provider failover: `ChainscanPool.from_config([(scanner, chain), ...])`
   gives the same surface with sticky routing and cooldowns.
