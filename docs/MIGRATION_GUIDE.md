# Migration Guide: v0.2.x to v0.3.0

This guide helps you migrate from the legacy `Client` class to the modern `ChainscanClient` architecture.

## Breaking Changes in v0.3.0

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
from aiochainscan import get_address_balance, get_block_by_number

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
