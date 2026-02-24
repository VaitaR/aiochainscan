# Quick Reference: ChainscanClient vs Facade Functions

## 🚨 Important: Facade Functions are Deprecated

If you see this warning, migrate to `ChainscanClient`:
```
DeprecationWarning: get_balance() is deprecated and will be removed in v0.5.0
```

---

## Migration Quick Reference

### Pattern 1: Single Request

#### ❌ Old (Deprecated)
```python
from aiochainscan import get_balance

balance = await get_balance(
    address='0x...',
    api_kind='eth',
    network='main',
    api_key='YOUR_KEY'
)
```

#### ✅ New (Recommended)
```python
from aiochainscan import ChainscanClient
from aiochainscan.core.method import Method

client = ChainscanClient.from_config('etherscan', 'ethereum')
try:
    balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
finally:
    await client.close()
```

---

### Pattern 2: Multiple Requests (Critical!)

#### ❌ Old (Creates 100 HTTP clients - VERY SLOW!)
```python
from aiochainscan import get_balance
import asyncio

addresses = ['0x...' for _ in range(100)]

balances = await asyncio.gather(*[
    get_balance(address=addr, api_kind='eth', network='main', api_key=key)
    for addr in addresses
])
# Performance: ~15s, 100MB memory, 100 TCP connections
```

#### ✅ New (Shares 1 connection pool - FAST!)
```python
from aiochainscan import ChainscanClient
from aiochainscan.core.method import Method
import asyncio

addresses = ['0x...' for _ in range(100)]

client = ChainscanClient.from_config('etherscan', 'ethereum')
try:
    balances = await asyncio.gather(*[
        client.call(Method.ACCOUNT_BALANCE, address=addr)
        for addr in addresses
    ])
finally:
    await client.close()
# Performance: ~3s, 5MB memory, 1-5 TCP connections (5x faster!)
```

---

### Pattern 3: Context Manager (Best Practice)

#### ✅ Recommended Pattern
```python
from aiochainscan import ChainscanClient
from aiochainscan.core.method import Method

async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    # Multiple operations, all share the same connection pool
    balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
    txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address='0x...')
    tokens = await client.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address='0x...')
    # Automatically closes on exit
```

---

## Function Migration Map

| Deprecated Function | ChainscanClient Method |
|---------------------|------------------------|
| `get_balance(address=...)` | `client.call(Method.ACCOUNT_BALANCE, address=...)` |
| `get_block(tag=...)` | `client.call(Method.BLOCK_BY_NUMBER, block_number=...)` |
| `get_logs(...)` | `client.call(Method.LOGS, ...)` |
| `get_transaction(txhash=...)` | `client.call(Method.TX_BY_HASH, txhash=...)` |
| `get_normal_transactions(address=...)` | `client.call(Method.ACCOUNT_TRANSACTIONS, address=...)` |
| `get_token_balance(...)` | `client.call(Method.TOKEN_BALANCE, ...)` |
| `get_gas_oracle()` | `client.call(Method.GAS_ORACLE)` |
| `get_contract_abi(address=...)` | `client.call(Method.CONTRACT_ABI, address=...)` |

---

## Available Methods

```python
from aiochainscan.core.method import Method

# Account methods
Method.ACCOUNT_BALANCE           # Get ETH/native balance
Method.ACCOUNT_BALANCE_MULTI     # Get multiple balances
Method.ACCOUNT_TRANSACTIONS      # Get normal transactions
Method.ACCOUNT_INTERNAL_TRANSACTIONS  # Get internal txs
Method.ACCOUNT_TOKEN_PORTFOLIO   # Get all ERC20 tokens
Method.ACCOUNT_NFT_PORTFOLIO     # Get all NFTs

# Block methods
Method.BLOCK_BY_NUMBER          # Get block by number

# Transaction methods
Method.TX_BY_HASH               # Get transaction by hash
Method.TX_RECEIPT_STATUS        # Get tx receipt

# Log methods
Method.LOGS                     # Get event logs

# Contract methods
Method.CONTRACT_ABI             # Get contract ABI
Method.CONTRACT_SOURCE          # Get source code

# Stats methods
Method.GAS_ORACLE              # Get gas prices
Method.ETH_PRICE               # Get ETH price
```

---

## Scanner Configuration

### BlockScout V2 (No API Key Required)
```python
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
```

Supported networks:
- `ethereum`, `polygon`, `arbitrum`, `optimism`, `base`
- `gnosis`, `zksync`, `scroll`, `linea`, `celo`

### Etherscan (API Key Required)
```python
client = ChainscanClient.from_config('etherscan', 'ethereum')
```

Set API key via environment variable:
```bash
export ETHERSCAN_KEY="your_key_here"
```

---

## Performance Comparison

| Operation | Facade Functions | ChainscanClient | Improvement |
|-----------|------------------|-----------------|-------------|
| 100 balance queries | ~15s | ~3s | **5x faster** |
| Memory usage | ~100MB | ~5MB | **20x less** |
| TCP connections | 100 | 1-5 | **20x less** |
| TLS handshakes | 100 | 1 | **100x less** |

---

## Common Mistakes

### ❌ Don't do this
```python
# Creating new client for each request (defeats the purpose!)
for address in addresses:
    client = ChainscanClient.from_config('etherscan', 'ethereum')
    balance = await client.call(Method.ACCOUNT_BALANCE, address=address)
    await client.close()
```

### ✅ Do this instead
```python
# Create client once, reuse for all requests
client = ChainscanClient.from_config('etherscan', 'ethereum')
try:
    for address in addresses:
        balance = await client.call(Method.ACCOUNT_BALANCE, address=address)
finally:
    await client.close()
```

---

## Need Help?

- Full guide: [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
- Technical details: [CONNECTION_POOLING_FIX.md](CONNECTION_POOLING_FIX.md)
- Examples: [../examples/](../examples/)
- GitHub issues: https://github.com/VaitaR/aiochainscan/issues
