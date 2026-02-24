# aiochainscan - AI Agent Skill Card

> **For AI Agents**: This document describes how to use the `aiochainscan` library to access blockchain data.

## What is this?

`aiochainscan` is a Python library that lets you query blockchain data (balances, transactions, tokens, logs, contracts, gas) from multiple networks using a unified API.

**Key Facts:**
- `blockscout_v2` — **no API key**, but only supports **6 methods** (balance, transactions, token portfolio, contract ABI, ENS reverse lookup, ENS batch reverse)
- `blockscout` (v1) — **no API key**, supports ~20 methods, but some endpoints may return 400 on certain networks
- `etherscan` — **requires `ETHERSCAN_KEY` env var**, supports ~12 methods, most reliable

---

## ⚠️ CRITICAL: Scanner Support Matrix

**Choose the right scanner for your task:**

| Method | `blockscout_v2` | `blockscout` (v1) | `etherscan` |
|--------|:--------------:|:-----------------:|:-----------:|
| `get_balance()` | ✅ | ✅ | ✅ |
| `get_transactions()` / `get_all_transactions()` | ✅ | ✅ | ✅ |
| `get_token_portfolio()` | ✅ | ✅ | ✅ |
| `get_nft_portfolio()` | ❌ | ✅ | ✅ |
| `get_contract_abi()` | ✅ | ✅ | ✅ |
| `get_internal_transactions()` | ❌ | ✅ | ✅ |
| `get_token_transfers()` | ❌ | ✅ | ✅ |
| `get_transaction()` | ❌ | ✅ | ✅ |
| `get_transaction_status()` | ❌ | ❌ | ✅ |
| `get_block()` | ❌ | ✅* | ✅ |
| `get_block_reward()` | ❌ | ✅* | ❌ |
| `get_block_countdown()` | ❌ | ❌ | ✅ |
| `get_block_by_timestamp()` | ❌ | ❌ | ✅ |
| `get_contract_source()` | ❌ | ✅ | ✅ |
| `get_token_balance()` | ❌ | ✅ | ✅ |
| `get_token_supply()` | ❌ | ✅ | ✅ |
| `get_token_info()` | ❌ | ✅ | ✅ |
| `get_eth_price()` | ❌ | ✅* | ✅ |
| `get_gas_oracle()` | ❌ | ✅* | ✅ |
| `get_eth_supply()` | ❌ | ✅* | ❌ |
| `get_logs()` / `get_all_logs()` | ❌ | ✅ | ✅ |
| `eth_call()` / `eth_get_balance()` | ❌ | ✅ | ✅ |
| `get_contract()` (SmartContract) | ✅ ABI only | ✅ | ✅ |
| `iter_events()` via SmartContract | ❌ | ✅ | ✅ |
| ENS: `lookup_address()` | ✅ | ❌ | ❌ |
| ENS: `resolve_name()` | ❌ | ❌ | ✅ |

> *`blockscout` (v1) works on Ethereum mainnet for these, but may return HTTP 400 on block proxy calls.

**Rule of thumb:**
- Need only balance/transactions/token portfolio? → `blockscout_v2` (no key needed)
- Need full data without API key? → `blockscout` (v1)
- Need gas oracle, logs, blocks, event decoding? → `etherscan` (set `ETHERSCAN_KEY`)
- Need ENS reverse lookup? → `blockscout_v2`

---

## Quick Start (Copy-Paste Ready)

### Basic — Balance & Transactions (no API key)
```python
import asyncio
from aiochainscan.core.client import ChainscanClient

async def get_wallet_info(address: str):
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        balance_wei = await client.get_balance(address)
        balance_eth = int(balance_wei) / 10**18
        txs = await client.get_transactions(address)          # single page (~50)
        tokens = await client.get_token_portfolio(address)    # all ERC-20 holdings
        return {
            "balance_eth": balance_eth,
            "recent_tx_count": len(txs),
            "token_count": len(tokens),
        }

result = asyncio.run(get_wallet_info("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"))
print(result)
```

### Full data — Gas, Logs, Blocks (requires ETHERSCAN_KEY)
```python
import asyncio, os
from aiochainscan.core.client import ChainscanClient

# Set: export ETHERSCAN_KEY="your_key_here"
async def full_data():
    async with ChainscanClient.from_config("etherscan", "ethereum") as client:
        price = await client.get_eth_price()        # {'ethusd': '1825.33', ...}
        gas = await client.get_gas_oracle()         # {'SafeGasPrice': '1', ...}
        block = await client.get_block(22000000)
        all_txs = await client.get_all_transactions("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
        return price, gas, block, len(all_txs)

asyncio.run(full_data())
```

---

## Available Methods (Complete Reference)

### Account Data
| Method | Description | Returns |
|--------|-------------|---------|
| `get_balance(address)` | Native token balance | `str` (Wei) |
| `get_transactions(address)` | Normal transactions (**single page ~50 items**) | `list[dict]` |
| `get_all_transactions(address)` | **ALL** transactions (auto-paginated) | `list[dict]` |
| `get_internal_transactions(address)` | Internal transactions | `list[dict]` |
| `get_all_internal_transactions(address)` | **ALL** internal txs | `list[dict]` |
| `get_token_transfers(address)` | ERC-20 transfers (single page) | `list[dict]` |
| `get_all_token_transfers(address)` | **ALL** ERC-20 transfers | `list[dict]` |
| `get_erc721_transfers(address)` | ERC-721 (NFT) transfers | `list[dict]` |
| `get_erc1155_transfers(address)` | ERC-1155 transfers | `list[dict]` |
| `get_token_portfolio(address)` | All ERC-20 holdings | `list[dict]` |
| `get_nft_portfolio(address)` | All NFT holdings | `list[dict]` |

### Transaction Data
| Method | Description | Returns |
|--------|-------------|---------|
| `get_transaction(tx_hash)` | Transaction details by hash | `dict` |
| `get_transaction_status(tx_hash)` | Receipt status | `dict` |
| `check_transaction_status(tx_hash)` | Execution status (isError) | `dict` |

### Block Data
| Method | Description | Returns |
|--------|-------------|---------|
| `get_block(block_number)` | Block info by number | `dict` |
| `get_block_reward(block_number)` | Mining reward info | `dict` |
| `get_block_countdown(target_block)` | ETA to block | `dict` |
| `get_block_by_timestamp(timestamp)` | Nearest block to timestamp | `dict` |

### Contract Data
| Method | Description | Returns |
|--------|-------------|---------|
| `get_contract_abi(address)` | Contract ABI | `str` (JSON) |
| `get_contract_source(address)` | Verified source code | `dict` |
| `get_contract_creation(addresses)` | Creator + creation tx | `list[dict]` |
| `get_contract(address)` | High-level SmartContract object | `SmartContract` |

### Token Data
| Method | Description | Returns |
|--------|-------------|---------|
| `get_token_balance(address, contract)` | Token balance (raw units) | `str` |
| `get_token_supply(contract)` | Total supply | `str` |
| `get_token_info(contract)` | Name, symbol, decimals | `dict` |

### Event Logs
| Method | Description | Returns |
|--------|-------------|---------|
| `get_logs(address, from_block, ...)` | Logs (≤1000, single page) | `list[dict]` |
| `get_all_logs(address, from_block, ...)` | **ALL** logs (auto-paginated) | `list[dict]` |

### Gas & Statistics
| Method | Description | Returns |
|--------|-------------|---------|
| `get_eth_price()` | ETH price (USD, BTC) | `dict` |
| `get_gas_oracle()` | Gas price recommendations | `dict` |
| `get_gas_estimate(gas_price)` | Estimated confirmation time | `str` |
| `get_eth_supply()` | Total ETH supply | `str` |

### Proxy / JSON-RPC
| Method | Description | Returns |
|--------|-------------|---------|
| `eth_call(to, data, tag)` | Read-only contract call | `str` (hex) |
| `eth_get_balance(address, tag)` | Balance via JSON-RPC | `str` (hex Wei) |

### ENS (Ethereum Name Service)
| Method | Description | Scanner |
|--------|-------------|---------|
| `lookup_address("0x...")` | Address → name (reverse) | `blockscout_v2` |
| `resolve_name("vitalik.eth")` | Name → address (forward) | `etherscan` |
| `lookup_addresses(["0x...", ...])` | Batch reverse | `blockscout_v2` |
| `resolve_names(["a.eth", ...])` | Batch forward | `etherscan` |

### Streaming (Memory Efficient — large datasets)
```python
# Requires: any scanner that supports ACCOUNT_TRANSACTIONS
async for batch in client.iter_transactions_streaming(address, batch_size=1000):
    bulk_insert(batch)   # ~10MB RAM regardless of total size

async for batch in client.iter_logs_streaming(address, from_block=0, batch_size=1000):
    analyze(batch)
```

### DataFrame Export (Polars)
```python
# Requires: pip install aiochainscan[data]
df = await client.get_transactions_df(address)    # ALL txs (auto-paginated!)
df = await client.get_token_portfolio_df(address)
```

---

## ⚠️ Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| `get_transactions()` returns only ~50 items | Use `get_all_transactions()` for complete data |
| `get_logs()` returns ≤1000 logs | Use `get_all_logs()` for complete data |
| Method raises `ValueError: not supported` | Wrong scanner — check support matrix above |
| Balance is a huge number | It's Wei — divide by `10**18` for ETH |
| Token balance is a huge number | Divide by `10**decimals` (get from `get_token_info()`) |
| BlockScout V2 `from`/`to` are dicts | Use `tx["from"]["hash"]` not `tx["from"]` |
| `get_eth_price()` fails on `blockscout_v2` | Use `etherscan` or `blockscout` (v1) |
| `get_block()` fails on `blockscout_v2` | Use `etherscan` or `blockscout` (v1) |
| `iter_events()` fails on `blockscout_v2` | Use `etherscan` (EVENT_LOGS not in blockscout_v2) |

---

## Response Schemas

### Transaction Object (BlockScout V2)
```python
{
    "hash": "0x47223a920c214b38...",
    "block_number": 24507269,
    "from": {"hash": "0xF8fc9A91349eBd..."},  # ⚠️ nested dict!
    "to": {"hash": "0xd8dA6BF26964aF..."},    # ⚠️ nested dict!
    "value": "50500000000000",                 # Wei as string
    "timestamp": "2026-02-21T19:15:35.000000Z",
    "gas_used": "21062",
    "status": "ok",
    "transaction_types": ["coin_transfer"],
}
```

### Transaction Object (Etherscan V2)
```python
{
    "hash": "0x...",
    "blockNumber": "22000000",       # string, not int
    "from": "0xF8fc9A91...",         # flat string (not nested!)
    "to": "0xd8dA6BF2...",           # flat string
    "value": "1000000000000000000",  # Wei as string
    "timeStamp": "1771935642",       # Unix timestamp string
    "isError": "0",                  # "0" = success, "1" = failed
}
```

### Token Holding Object (blockscout_v2 `get_token_portfolio()`)
```python
{
    "token": {
        "symbol": "USDT",
        "name": "Tether USD",
        "decimals": "6",
        "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    },
    "value": "1000000000",  # Raw amount (divide by 10**decimals)
}
```

---

## Supported Networks

### blockscout_v2 (no API key — 6 methods only)
`"ethereum"`, `"arbitrum"`, `"base"`, `"gnosis"` — reliably working

> ⚠️ `"polygon"` may return HTTP 500; `"optimism"` has moved to `explorer.optimism.io` (library may get 301). Treat these as best-effort.

### blockscout / v1 (no API key — ~20 methods)
`"ethereum"` (others may vary)

### etherscan (requires `ETHERSCAN_KEY` — 12 methods, most reliable)
`"ethereum"`, `"base"`, `"polygon"`, `"arbitrum"`, `"optimism"`, and more

---

## Error Handling for Agents

```python
from aiochainscan.exceptions import (
    ChainscanRateLimitError,
    ChainscanNetworkError,
    PaginationDataLossError,
)

try:
    result = await client.get_balance(address)
except ChainscanRateLimitError as e:
    await asyncio.sleep(3)
    result = await client.get_balance(address)  # Retry
except ChainscanNetworkError:
    pass  # Network issue, try another scanner
```

Errors include `[AI_INSTRUCTION]` hints in their messages.

---

## Common Patterns

### 1. Multi-Chain ETH Balance (no API key)
```python
async def get_multichain_balance(address: str):
    networks = ["ethereum", "polygon", "arbitrum", "optimism", "base"]
    results = {}
    for network in networks:
        async with ChainscanClient.from_config("blockscout_v2", network) as client:
            try:
                balance = await client.get_balance(address)
                results[network] = int(balance) / 10**18
            except Exception as e:
                results[network] = f"error: {e}"
    return results
```

### 2. Token Portfolio Summary
```python
async def token_summary(address: str):
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        holdings = await client.get_token_portfolio(address)
        for h in holdings[:5]:
            token = h["token"]
            decimals = int(token.get("decimals", 18))
            balance = int(h["value"]) / 10**decimals
            print(f"{token['symbol']}: {balance:,.4f}")
```

### 3. Gas + ETH Price (requires etherscan key OR blockscout v1)
```python
# Option A: etherscan (requires ETHERSCAN_KEY)
async with ChainscanClient.from_config("etherscan", "ethereum") as client:
    price = await client.get_eth_price()    # {'ethusd': '1825.33', ...}
    gas = await client.get_gas_oracle()     # {'SafeGasPrice': '1', ...}

# Option B: blockscout v1 (no key, but may be unreliable)
async with ChainscanClient.from_config("blockscout", "ethereum") as client:
    price = await client.get_eth_price()
```

### 4. ALL Transactions — Complete History
```python
async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
    # ✅ get_all_transactions handles pagination automatically
    all_txs = await client.get_all_transactions(address)
    print(f"Total: {len(all_txs)} transactions")

    # ✅ For large wallets (1M+ txs) use streaming to save RAM
    count = 0
    async for batch in client.iter_transactions_streaming(address, batch_size=1000):
        count += len(batch)
    print(f"Streamed: {count} transactions")
```

### 5. Export to CSV
```python
import csv

async def export_transactions(address: str, filename: str):
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        txs = await client.get_all_transactions(address)
        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["hash", "value_eth", "from", "to", "timestamp"])
            writer.writeheader()
            for tx in txs:
                writer.writerow({
                    "hash": tx.get("hash"),
                    "value_eth": int(tx.get("value", 0)) / 10**18,
                    "from": tx.get("from", {}).get("hash"),   # blockscout_v2: nested dict
                    "to": (tx.get("to") or {}).get("hash", ""),
                    "timestamp": tx.get("timestamp"),
                })
```

### 6. ENS Name Lookup
```python
async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
    name = await client.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    print(f"ENS: {name}")  # "vitalik.eth"
```

### 7. Decode Smart Contract Events (requires etherscan)
```python
# iter_events() uses EVENT_LOGS — only available on etherscan or blockscout v1
async with ChainscanClient.from_config("etherscan", "ethereum") as client:
    contract = await client.get_contract("0xdAC17F958D2ee523a2206206994597C13D831ec7")
    async for event in contract.iter_events("Transfer", limit=10):
        print(f"{event.args['from']} → {event.args['to']}: {event.args['value']}")
```

---

## Installation

```bash
pip install aiochainscan                 # Basic (BlockScout V2, no API key)
pip install aiochainscan[data]           # + Polars DataFrames
pip install aiochainscan[mcp]            # + MCP server support
```

## Environment Setup

```bash
export ETHERSCAN_KEY="your_key_here"     # Required for etherscan scanner
```

---

## Tips for AI Agents

1. **Check the support matrix first** — most methods are NOT available on `blockscout_v2`
2. **Use `blockscout_v2` for**: balance, recent transactions, token portfolio, ENS reverse lookup
3. **Use `etherscan` for**: gas oracle, ETH price, blocks, logs, full method coverage
4. **Balance is in Wei** — divide by `10**18` for ETH/MATIC
5. **Use `get_all_*` methods** — `get_transactions()` and `get_logs()` are single-page only
6. **BlockScout V2 tx schema**: `from`/`to` are dicts → use `tx["from"]["hash"]`
7. **Etherscan tx schema**: `from`/`to` are flat strings → use `tx["from"]` directly
8. **For large data** — use `iter_transactions_streaming()` (~10MB RAM) or `get_transactions_df()`
9. **Handle network errors** — blockscout endpoints sometimes return 400/500; wrap in try/except

---

## Version

Current: **0.4.1**
