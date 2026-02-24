# aiochainscan - AI Agent Skill Card

> **For AI Agents**: This document describes how to use the `aiochainscan` library to access blockchain data.

## What is this?

`aiochainscan` is a Python library that lets you query blockchain data (balances, transactions, tokens, logs, contracts, gas) from multiple networks (Ethereum, Polygon, Arbitrum, etc.) using a unified API.

**Key Feature**: Works without API keys using BlockScout V2!

---

## Quick Start (Copy-Paste Ready)

```python
import asyncio
from aiochainscan.core.client import ChainscanClient

async def get_wallet_info(address: str):
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        balance_wei = await client.get_balance(address)
        balance_eth = int(balance_wei) / 10**18
        txs = await client.get_transactions(address)
        tokens = await client.get_token_portfolio(address)
        return {
            "balance_eth": balance_eth,
            "transaction_count": len(txs),
            "token_count": len(tokens),
        }

result = asyncio.run(get_wallet_info("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"))
print(result)
```

---

## Available Methods (Complete Reference)

### Account Data
| Method | Description | Returns |
|--------|-------------|---------|
| `get_balance(address)` | Native token balance | `str` (Wei) |
| `get_transactions(address)` | Normal transactions (single page) | `list[dict]` |
| `get_all_transactions(address)` | **ALL** transactions (auto-paginated) | `list[dict]` |
| `get_internal_transactions(address)` | Internal transactions (single page) | `list[dict]` |
| `get_all_internal_transactions(address)` | **ALL** internal txs (auto-paginated) | `list[dict]` |
| `get_token_transfers(address)` | ERC-20 transfers (single page) | `list[dict]` |
| `get_all_token_transfers(address)` | **ALL** ERC-20 transfers (auto-paginated) | `list[dict]` |
| `get_erc721_transfers(address)` | ERC-721 (NFT) transfers | `list[dict]` |
| `get_erc1155_transfers(address)` | ERC-1155 (multi-token) transfers | `list[dict]` |
| `get_token_portfolio(address)` | All ERC-20 token holdings | `list[dict]` |
| `get_nft_portfolio(address)` | All NFT holdings | `list[dict]` |

### Transaction Data
| Method | Description | Returns |
|--------|-------------|---------|
| `get_transaction(tx_hash)` | Transaction details by hash | `dict` |
| `get_transaction_status(tx_hash)` | Receipt status (success/fail) | `dict` |
| `check_transaction_status(tx_hash)` | Execution status (isError) | `dict` |

### Block Data
| Method | Description | Returns |
|--------|-------------|---------|
| `get_block(block_number)` | Block info by number | `dict` |
| `get_block_reward(block_number)` | Mining reward info | `dict` |
| `get_block_countdown(target_block)` | Estimated time to target block | `dict` |
| `get_block_by_timestamp(timestamp)` | Nearest block to timestamp | `dict` |

### Contract Data
| Method | Description | Returns |
|--------|-------------|---------|
| `get_contract_abi(address)` | Contract ABI | `str` (JSON) |
| `get_contract_source(address)` | Verified source code | `dict` |
| `get_contract_creation(addresses)` | Creator address + creation tx | `list[dict]` |
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
| `get_logs(address, from_block, ...)` | Logs (single page, ≤1000) | `list[dict]` |
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
| Method | Description | Returns |
|--------|-------------|---------|
| `resolve_name("vitalik.eth")` | Name → address | `str \| None` |
| `lookup_address("0x...")` | Address → name | `str \| None` |
| `resolve_names(["a.eth", ...])` | Batch forward resolution | `dict[str, str]` |
| `lookup_addresses(["0x...", ...])` | Batch reverse lookup | `dict[str, str]` |

### Streaming (Memory Efficient)
```python
# For large wallets — constant ~10MB RAM regardless of data size
async for tx in client.iter_transactions(address, batch_size=1000):
    process(tx)  # One transaction at a time

async for batch in client.iter_transactions_streaming(address, batch_size=1000):
    bulk_insert(batch)  # Batches of dicts

async for batch in client.iter_logs_streaming(address, from_block=0, batch_size=1000):
    analyze(batch)
```

### DataFrame Export (Polars)
```python
# Requires: pip install aiochainscan[data]
df = await client.get_transactions_df(address)       # ALL txs (auto-paginated!)
df = await client.get_token_portfolio_df(address)
```

---

## ⚠️ Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| `get_transactions()` returns only ~50-100 items | Use `get_all_transactions()` for complete data |
| `get_logs()` returns ≤1000 logs | Use `get_all_logs()` for complete data |
| Balance is a huge number | It's Wei — divide by `10**18` for ETH |
| Token balance is a huge number | Divide by `10 ** decimals` (get decimals from `get_token_info()`) |
| BlockScout V2 wraps in `{items: [...]}` | Convenience methods handle this — use them instead of `client.call()` |

---

## Response Schemas

### Transaction Object (BlockScout V2)
```python
{
    "hash": "0x47223a920c214b38...",
    "block_number": 24507269,
    "from": {"hash": "0xF8fc9A91349eBd..."},  # Note: nested object!
    "to": {"hash": "0xd8dA6BF26964aF..."},    # Note: nested object!
    "value": "50500000000000",                 # Wei as string
    "timestamp": "2026-02-21T19:15:35.000000Z",
    "gas_used": "21062",
    "status": "ok",
    "transaction_types": ["coin_transfer"],
}
```

### Token Holding Object
```python
{
    "token": {
        "symbol": "USDT",
        "name": "Tether USD",
        "decimals": "6",
        "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    },
    "value": "1000000000",  # Raw amount (divide by 10^decimals)
}
```

---

## Supported Networks

| Network | Scanner | API Key Required? |
|---------|---------|-------------------|
| `ethereum` | blockscout_v2 | ❌ No |
| `polygon` | blockscout_v2 | ❌ No |
| `arbitrum` | blockscout_v2 | ❌ No |
| `optimism` | blockscout_v2 | ❌ No |
| `base` | blockscout_v2 | ❌ No |
| `gnosis` | blockscout_v2 | ❌ No |
| `ethereum` | etherscan | ✅ Yes |

---

## Error Handling for Agents

Errors include `[AI_INSTRUCTION]` blocks with recovery guidance:

```python
from aiochainscan.exceptions import ChainscanRateLimitError

try:
    result = await client.get_balance(address)
except ChainscanRateLimitError as e:
    await asyncio.sleep(e.retry_after)
    result = await client.get_balance(address)  # Retry
```

### Exception Types
- `ChainscanRateLimitError` - Rate limit hit, retry after `e.retry_after` seconds
- `ChainscanInvalidAddressError` - Invalid Ethereum address format
- `ChainscanNetworkError` - Network/connectivity issue
- `PaginationDataLossError` - Whale block detected, data may be incomplete

---

## Common Patterns

### 1. Get ALL Logs for a Contract
```python
# ✅ CORRECT — auto-paginated, handles all edge cases
all_logs = await client.get_all_logs(
    address="0xdAC17F958D2ee523a2206206994597C13D831ec7",
    from_block=0,
    topic0="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",  # Transfer
)

# ❌ WRONG — capped at ~1000 logs, silently truncated
logs = await client.get_logs(address="0x...", from_block=0)
```

### 2. Check Multiple Wallets
```python
async def check_wallets(addresses: list[str]):
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        tasks = [client.get_balance(addr) for addr in addresses]
        balances = await asyncio.gather(*tasks)
        return dict(zip(addresses, balances))
```

### 3. Multi-Chain Portfolio
```python
async def get_multichain_balance(address: str):
    networks = ["ethereum", "polygon", "arbitrum", "optimism", "base"]
    results = {}
    for network in networks:
        async with ChainscanClient.from_config("blockscout_v2", network) as client:
            balance = await client.get_balance(address)
            results[network] = int(balance) / 10**18
    return results
```

### 4. Export Transactions to CSV
```python
import csv

async def export_transactions(address: str, filename: str):
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        txs = await client.get_all_transactions(address)  # ALL txs!
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["hash", "value", "from", "to"])
            writer.writeheader()
            for tx in txs:
                writer.writerow({
                    "hash": tx.get("hash"),
                    "value": int(tx.get("value", 0)) / 10**18,
                    "from": tx.get("from", {}).get("hash"),
                    "to": tx.get("to", {}).get("hash") if tx.get("to") else "",
                })
```

### 5. Decode Smart Contract Events
```python
async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
    contract = await client.get_contract("0xdAC17F958D2ee523a2206206994597C13D831ec7")
    async for event in contract.iter_events("Transfer", limit=100):
        print(f"{event.args['from']} → {event.args['to']}: {event.args['value']}")
```

---

## Tips for AI Agents

1. **Always use `async with`** — Ensures proper resource cleanup
2. **Balance is in Wei** — Divide by `10**18` for ETH/MATIC
3. **Use BlockScout V2** — No API key required, works immediately
4. **Use `get_all_*` methods** — `get_transactions()` and `get_logs()` are single-page only!
5. **Handle rate limits** — Check for `ChainscanRateLimitError` and retry
6. **For large data** — Use `iter_transactions_streaming()` or `get_transactions_df()` for Polars
7. **Don't reinvent pagination** — The library handles it in `get_all_*` and `iter_*_streaming` methods

---

## Installation

```bash
pip install aiochainscan                 # Basic (BlockScout V2, no API key)
pip install aiochainscan[data]           # + Polars DataFrames
pip install aiochainscan[mcp]            # + MCP server support
pip install aiochainscan[data,mcp]       # Everything
```

---

## Version

Current: **0.4.1**
