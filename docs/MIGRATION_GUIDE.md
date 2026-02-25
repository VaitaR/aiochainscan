# Migration Guide

This guide helps you migrate between versions of aiochainscan and understand architectural changes.

---

## 🚨 v0.4.0 → v0.5.0: Facade Functions Deprecation (Connection Pooling Fix)

### Critical Architectural Issue: Why Facade Functions Are Deprecated

**The Problem**: All facade functions (`get_balance`, `get_logs`, `get_transaction`, etc.) create and destroy HTTP clients on every call:

```python
async def get_balance(...):
    http = http or HttpxClientAdapter()  # ❌ New client every call
    try:
        return await get_address_balance(...)
    finally:
        await http.aclose()  # ❌ Closes connection immediately
```

**Impact on Bulk Operations**:
```python
# ❌ BAD - Creates 100 separate HTTP clients!
balances = await asyncio.gather(*[
    get_balance(address=addr, api_kind='eth', network='main', api_key=key)
    for addr in addresses  # 100 addresses
])
```

This causes:
- **100 TCP connection establishments** (slow!)
- **100 TLS handshakes** (expensive!)
- **Loss of HTTP/2 multiplexing** (no connection reuse)
- **High CPU load** (encryption overhead)
- **API rate limits/blocks** (SNI/TCP limits per IP)
- **Memory waste** (100 connection pools in memory)

### ✅ Solution: Use ChainscanClient

```python
from aiochainscan import ChainscanClient
from aiochainscan.core.method import Method

# ✅ GOOD - Single persistent connection pool
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
try:
    # All calls share the same HTTP client and connection pool
    balances = await asyncio.gather(*[
        client.call(Method.ACCOUNT_BALANCE, address=addr)
        for addr in addresses  # 100 addresses
    ])
finally:
    await client.close()
```

**Benefits**:
- ✅ **1 TCP connection pool** shared across all calls
- ✅ **HTTP/2 multiplexing** for concurrent requests
- ✅ **Connection reuse** (keep-alive)
- ✅ **Lower CPU usage** (persistent TLS session)
- ✅ **Better rate limiting** (single client tracking)

### Migration Examples

#### Example 1: Single Balance Query

**Before (Deprecated)**:
```python
from aiochainscan import ChainscanClient

balance = await get_balance(
    address='0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3',
    api_kind='blockscout_eth',
    network='ethereum',
    api_key=''
)
```

**After (Recommended)**:
```python
from aiochainscan import ChainscanClient
from aiochainscan.core.method import Method

client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
try:
    balance = await client.call(
        Method.ACCOUNT_BALANCE,
        address='0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3'
    )
finally:
    await client.close()
```

#### Example 2: Bulk Operations (Critical!)

**Before (Deprecated - Creates 100 HTTP clients!)**:
```python
from aiochainscan import ChainscanClient
import asyncio

addresses = ['0x...' for _ in range(100)]

# ❌ Creates 100 separate HTTP clients - VERY SLOW
balances = await asyncio.gather(*[
    get_balance(
        address=addr,
        api_kind='blockscout_eth',
        network='ethereum',
        api_key=''
    )
    for addr in addresses
])
```

**After (Recommended - Shares 1 connection pool)**:
```python
from aiochainscan import ChainscanClient
from aiochainscan.core.method import Method
import asyncio

addresses = ['0x...' for _ in range(100)]

client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
try:
    # ✅ All calls share the same connection pool
    balances = await asyncio.gather(*[
        client.call(Method.ACCOUNT_BALANCE, address=addr)
        for addr in addresses
    ])
finally:
    await client.close()
```

#### Example 3: Context Manager (Best Practice)

```python
from aiochainscan import ChainscanClient
from aiochainscan.core.method import Method

async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
    # Multiple operations sharing connection pool
    balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
    txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address='0x...')
    tokens = await client.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address='0x...')
    # Automatically closes on exit
```

### Facade Function Migration Map

| Deprecated Facade Function | ChainscanClient Method |
|----------------------------|------------------------|
| `get_balance(...)` | `client.call(Method.ACCOUNT_BALANCE, address=...)` |
| `get_block(...)` | `client.call(Method.BLOCK_BY_NUMBER, block_number=...)` |
| `get_logs(...)` | `client.call(Method.LOGS, ...)` |
| `get_transaction(...)` | `client.call(Method.TX_BY_HASH, txhash=...)` |
| `get_normal_transactions(...)` | `client.call(Method.ACCOUNT_TRANSACTIONS, address=...)` |
| `get_token_balance(...)` | `client.call(Method.TOKEN_BALANCE, ...)` |
| `get_gas_oracle(...)` | `client.call(Method.GAS_ORACLE)` |
| `get_contract_abi(...)` | `client.call(Method.CONTRACT_ABI, address=...)` |

### Timeline

- **v0.4.0** (Current): Facade functions emit `DeprecationWarning`
- **v0.5.0** (Next): Facade functions will be removed

---

## v0.2.x → v0.3.0: Legacy Client Deprecation

- **Removed**: Legacy `Client` class and module-based API (`.account`, `.proxy`, `.stats`, etc.)
- **Removed**: Moralis and RoutScan scanner implementations
- **Kept**: Etherscan and Blockscout scanners only
- **New**: `ChainscanClient` with unified `Method` enum-based API

## Quick Migration

### Before (Legacy - v0.2.x)

```python
from aiochainscan import Client

# Create client
client = Client(api_key='YOUR_KEY', api_kind='eth', network='main')

# Or from config
client = Client.from_config('eth', 'main')

# Module-based calls
balance = await client.account.balance('0x...')
txs = await client.account.normal_txs('0x...')
price = await client.stats.eth_price()
block = await client.proxy.block_number()

# Close client
await client.close()
```

### After (Modern - v0.3.0)

```python
from aiochainscan import ChainscanClient, Method

# Create client from config
client = ChainscanClient.from_config('etherscan', 'ethereum')

# Method-based calls
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address='0x...')
price = await client.call(Method.ETH_PRICE)
block = await client.call(Method.BLOCK_BY_NUMBER, block='latest')

# Close client
await client.close()
```

## Method Mapping Reference

| Legacy Module Call | Modern Method |
|-------------------|---------------|
| `client.account.balance(addr)` | `client.call(Method.ACCOUNT_BALANCE, address=addr)` |
| `client.account.normal_txs(addr)` | `client.call(Method.ACCOUNT_TRANSACTIONS, address=addr)` |
| `client.account.internal_txs(addr)` | `client.call(Method.ACCOUNT_INTERNAL_TXS, address=addr)` |
| `client.account.erc20_transfers(addr)` | `client.call(Method.ACCOUNT_ERC20_TRANSFERS, address=addr)` |
| `client.account.erc721_transfers(addr)` | `client.call(Method.ACCOUNT_ERC721_TRANSFERS, address=addr)` |
| `client.stats.eth_price()` | `client.call(Method.ETH_PRICE)` |
| `client.stats.eth_supply()` | `client.call(Method.ETH_SUPPLY)` |
| `client.contract.contract_abi(addr)` | `client.call(Method.CONTRACT_ABI, address=addr)` |
| `client.contract.contract_source_code(addr)` | `client.call(Method.CONTRACT_SOURCE, address=addr)` |
| `client.proxy.block_number()` | `client.call(Method.BLOCK_BY_NUMBER, block='latest')` |
| `client.transaction.tx_receipt_status(hash)` | `client.call(Method.TX_RECEIPT_STATUS, txhash=hash)` |

## Scanner Name Changes

| Legacy `api_kind` | Modern Scanner Name |
|-------------------|---------------------|
| `eth` | `etherscan` |
| `bsc` | `bscscan` |
| `polygon` | `polygonscan` |
| ... | ... |

## Using Facade Functions (Alternative)

The library still provides high-level facade functions that don't require creating a client:

```python
from aiochainscan import ChainscanClient

# These functions handle client creation/cleanup internally
balance = await get_address_balance(
    address='0x...',
    api_kind='eth',
    network='main',
    api_key='YOUR_KEY'
)
```

## Context Manager Pattern

For multiple operations, use the context manager pattern:

```python
from aiochainscan import ChainscanClient, Method

async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
    txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address='0x...')
    # Client is automatically closed when exiting the context
```

## Need Help?

- Check the [examples/](../examples/) directory for more usage patterns
- Refer to [ARCHITECTURE_REFACTOR.md](ARCHITECTURE_REFACTOR.md) for design details
- Open an issue on GitHub for migration assistance
