# aiochainscan - AI Agent Skill Card

> **For AI Agents**: This document describes how to use the `aiochainscan` library to access blockchain data.

## What is this?

`aiochainscan` is a Python library that lets you query blockchain data (balances, transactions, tokens) from multiple networks (Ethereum, Polygon, Arbitrum, etc.) using a unified API.

**Key Feature**: Works without API keys using BlockScout V2!

---

## Quick Start (Copy-Paste Ready)

```python
import asyncio
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

async def get_wallet_info(address: str):
    # Use async with for automatic resource cleanup
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        # Get balance (returns Wei as string)
        balance_wei = await client.get_balance(address)
        balance_eth = int(balance_wei) / 10**18

        # Get transactions
        txs = await client.get_transactions(address)

        # Get token portfolio
        tokens = await client.get_token_portfolio(address)

        return {
            "balance_eth": balance_eth,
            "transaction_count": len(txs),
            "token_count": len(tokens),
        }

# Run it
result = asyncio.run(get_wallet_info("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"))
print(result)
```

---

## Available Methods

### Account Data
| Method | Description | Returns |
|--------|-------------|---------|
| `client.get_balance(address)` | Native token balance | `str` (Wei) |
| `client.get_transactions(address)` | Normal transactions (last 50) | `list[dict]` |
| `client.get_token_portfolio(address)` | ERC20 token holdings | `list[dict]` |
| `client.get_token_transfers(address)` | Token transfer history | `list[dict]` |

### Contract Data
| Method | Description | Returns |
|--------|-------------|---------|
| `client.get_contract_abi(address)` | Contract ABI | `str` (JSON) |

### Streaming (Memory Efficient)
```python
# For large wallets, use async generator to avoid OOM
async for tx in client.iter_transactions(address, batch_size=1000):
    process(tx)  # One transaction at a time
```

### DataFrame Export (Polars)
```python
# Requires: pip install aiochainscan[data]
df = await client.get_transactions_df(address)
df = await client.get_token_portfolio_df(address)
```

---

## Response Schemas

### Transaction Object
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
    # Error message contains: [AI_INSTRUCTION: Wait 5 seconds using asyncio.sleep(5), then retry...]
    await asyncio.sleep(e.retry_after)
    result = await client.get_balance(address)  # Retry
```

### Exception Types
- `ChainscanRateLimitError` - Rate limit hit, retry after `e.retry_after` seconds
- `ChainscanInvalidAddressError` - Invalid Ethereum address format
- `ChainscanNetworkError` - Network/connectivity issue

---

## MCP Server (For Claude Desktop / Cursor)

The library can run as an MCP server for direct AI integration:

```bash
# Run as MCP server
python -m aiochainscan.mcp_server
```

Available tools:
- `get_wallet_balance(address, network)` - Native token balance
- `get_recent_transactions(address, network, limit)` - Recent transactions
- `get_token_portfolio(address, network)` - ERC20 token holdings

---

## Installation

```bash
# Basic install (BlockScout V2, no API key needed)
pip install aiochainscan

# With data analysis features (Polars DataFrames)
pip install aiochainscan[data]

# With MCP server support
pip install aiochainscan[mcp]

# Everything
pip install aiochainscan[data,mcp]
```

---

## Common Patterns

### 1. Check Multiple Wallets
```python
import asyncio

async def check_wallets(addresses: list[str]):
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        tasks = [client.get_balance(addr) for addr in addresses]
        balances = await asyncio.gather(*tasks)
        return dict(zip(addresses, balances))
```

### 2. Multi-Chain Portfolio
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

### 3. Export to CSV
```python
import csv

async def export_transactions(address: str, filename: str):
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        txs = await client.get_transactions(address)

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

---

## Tips for AI Agents

1. **Always use `async with`** - Ensures proper resource cleanup
2. **Balance is in Wei** - Divide by `10**18` to get ETH/MATIC
3. **Use BlockScout V2** - No API key required, works immediately
4. **Handle rate limits** - Check for `ChainscanRateLimitError` and retry
5. **For large data** - Use `iter_transactions()` generator or `get_transactions_df()` for Polars

---

## Version

Current: **0.4.0**
