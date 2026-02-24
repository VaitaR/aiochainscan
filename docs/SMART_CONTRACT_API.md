# SmartContract API - High-Level Contract Abstraction

## Overview

The SmartContract API provides a high-level abstraction for interacting with smart contracts on EVM-compatible blockchains. It automatically handles:

- ✅ **Automatic ABI Fetching** - No need to manually retrieve contract ABIs
- ✅ **Proxy Contract Resolution** - Automatically detects and resolves proxy contracts to their implementation
- ✅ **Event Decoding** - Iterate through decoded event logs with human-readable arguments
- ✅ **Transaction Decoding** - Iterate through decoded function calls with parsed parameters
- ✅ **Memory-Efficient Streaming** - Process large datasets without loading everything into memory

## Quick Start

```python
import asyncio
from aiochainscan import ChainscanClient

async def main():
    # Create client
    client = ChainscanClient.from_config('etherscan', 'ethereum')

    # Get contract (auto-fetches ABI, resolves proxy)
    usdt = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")

    # Iterate through Transfer events
    async for event in usdt.iter_events("Transfer", limit=10):
        print(f"{event.args['from']} → {event.args['to']}: {event.args['value']}")

    await client.close()

asyncio.run(main())
```

## Features

### 1. Automatic Proxy Detection and Resolution

The SmartContract API automatically detects proxy contracts and fetches the ABI from the implementation contract:

```python
# USDT is a proxy contract
usdt = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")

print(f"Is Proxy: {usdt.is_proxy}")  # True
print(f"Implementation: {usdt.implementation_address}")  # The real implementation address
```

### 2. Event Iteration

Stream and decode events with a clean async iterator interface:

```python
# Get Transfer events from a specific block range
async for event in contract.iter_events(
    event_name="Transfer",
    from_block=19000000,
    to_block=19001000,
    limit=100
):
    print(f"Block: {event.block_number}")
    print(f"From: {event.args['from']}")
    print(f"To: {event.args['to']}")
    print(f"Value: {event.args['value']}")
    print(f"Tx Hash: {event.tx_hash}")
```

**Key Features:**
- Automatically decodes event arguments
- Supports block range filtering
- Memory-efficient streaming (doesn't load all events at once)
- Limit parameter to control how many events to fetch

### 3. Transaction Iteration

Stream and decode contract function calls:

```python
# Iterate through function calls to the contract
async for tx in contract.iter_transactions(limit=50):
    print(f"Function: {tx.function_name}")
    print(f"Args: {tx.args}")
    print(f"From: {tx.from_address}")
    print(f"Value: {tx.value_wei / 1e18} ETH")
    print(f"Block: {tx.block_number}")
```

**Key Features:**
- Automatically decodes function call data
- Filters to only show transactions TO the contract (not FROM)
- Provides decoded function arguments
- Includes all transaction metadata (gas, value, etc.)

### 4. ABI Helper Methods

Access event and function ABIs directly:

```python
# Get event ABI
transfer_event = contract.get_event_abi("Transfer")
print(transfer_event['inputs'])

# Get function ABI
transfer_func = contract.get_function_abi("transfer")
print(transfer_func['inputs'])
```

## API Reference

### `ChainscanClient.get_contract(address)`

Creates a SmartContract instance with automatic ABI fetching and proxy resolution.

**Parameters:**
- `address` (str): Contract address

**Returns:**
- `SmartContract`: Fully initialized contract instance

**Raises:**
- `ValueError`: If contract ABI cannot be fetched

**Example:**
```python
contract = await client.get_contract("0x...")
```

### `SmartContract.from_address(address, client)`

Alternative factory method for creating SmartContract instances.

**Parameters:**
- `address` (str): Contract address
- `client` (ChainscanClient): Client instance

**Returns:**
- `SmartContract`: Fully initialized contract instance

### `SmartContract.iter_events(event_name=None, from_block=0, to_block='latest', limit=None)`

Asynchronous iterator for decoded event logs.

**Parameters:**
- `event_name` (str | None): Event name to filter (e.g., "Transfer"). If None, returns all events.
- `from_block` (int): Starting block number (default: 0)
- `to_block` (int | str): Ending block number or 'latest' (default: 'latest')
- `limit` (int | None): Maximum events to return (default: None = unlimited)

**Yields:**
- `DecodedEvent`: Decoded event with args, block number, tx hash, etc.

**Example:**
```python
async for event in contract.iter_events("Transfer", limit=1000):
    process(event)
```

### `SmartContract.iter_transactions(from_block=0, to_block=None, limit=None)`

Asynchronous iterator for decoded transactions to this contract.

**Parameters:**
- `from_block` (int): Starting block number (default: 0)
- `to_block` (int | None): Ending block number (default: None = latest)
- `limit` (int | None): Maximum transactions to return (default: None = unlimited)

**Yields:**
- `DecodedTransaction`: Decoded transaction with function name, args, and metadata

**Example:**
```python
async for tx in contract.iter_transactions(limit=100):
    process(tx)
```

### `SmartContract.get_event_abi(event_name)`

Get ABI definition for a specific event.

**Parameters:**
- `event_name` (str): Event name

**Returns:**
- `dict | None`: Event ABI dict or None if not found

### `SmartContract.get_function_abi(function_name)`

Get ABI definition for a specific function.

**Parameters:**
- `function_name` (str): Function name

**Returns:**
- `dict | None`: Function ABI dict or None if not found

## Data Classes

### `DecodedEvent`

Represents a decoded event log.

**Attributes:**
- `name` (str): Event name (e.g., "Transfer")
- `args` (dict): Decoded event arguments
- `address` (str): Contract address that emitted the event
- `block_number` (int): Block number
- `tx_hash` (str): Transaction hash
- `log_index` (int): Log index in transaction
- `raw_log` (dict): Original raw log data

### `DecodedTransaction`

Represents a decoded transaction.

**Attributes:**
- `function_name` (str): Called function name (e.g., "transfer")
- `args` (dict): Decoded function arguments
- `tx_hash` (str): Transaction hash
- `from_address` (str): Sender address
- `to_address` (str): Recipient address (contract)
- `value_wei` (int): ETH value sent in Wei
- `block_number` (int): Block number
- `gas` (int): Gas limit
- `gas_price_wei` (int): Gas price in Wei
- `raw_transaction` (dict): Original raw transaction data

## Complete Examples

### Example 1: Analyze USDT Transfers

```python
import asyncio
from aiochainscan import ChainscanClient

async def analyze_usdt_transfers():
    client = ChainscanClient.from_config('etherscan', 'ethereum')

    # USDT contract (proxy)
    usdt = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")

    total_volume = 0
    transfer_count = 0

    # Analyze last 1000 transfers
    async for event in usdt.iter_events("Transfer", limit=1000):
        value = event.args.get('value', 0)
        if isinstance(value, int):
            # USDT has 6 decimals
            total_volume += value / 1e6
            transfer_count += 1

    print(f"Transfers: {transfer_count}")
    print(f"Volume: ${total_volume:,.2f}")

    await client.close()

asyncio.run(analyze_usdt_transfers())
```

### Example 2: Monitor Uniswap Swaps

```python
async def monitor_uniswap_swaps():
    client = ChainscanClient.from_config('etherscan', 'ethereum')

    # Uniswap V2 Router
    router = await client.get_contract("0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")

    # Track function calls
    function_counts = {}

    async for tx in router.iter_transactions(limit=500):
        func = tx.function_name
        function_counts[func] = function_counts.get(func, 0) + 1

    print("Function Call Distribution:")
    for func, count in sorted(function_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {func}: {count}")

    await client.close()

asyncio.run(monitor_uniswap_swaps())
```

### Example 3: Export Events to CSV

```python
import csv
import asyncio
from aiochainscan import ChainscanClient

async def export_events_to_csv():
    client = ChainscanClient.from_config('etherscan', 'ethereum')

    contract = await client.get_contract("0x...")

    with open('events.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Block', 'Tx Hash', 'Event', 'Args'])

        async for event in contract.iter_events(limit=10000):
            writer.writerow([
                event.block_number,
                event.tx_hash,
                event.name,
                str(event.args)
            ])

    await client.close()

asyncio.run(export_events_to_csv())
```

## Error Handling

```python
from aiochainscan import ChainscanClient

async def safe_contract_access():
    client = ChainscanClient.from_config('etherscan', 'ethereum')

    try:
        # This will raise ValueError if contract not verified
        contract = await client.get_contract("0xinvalid...")
    except ValueError as e:
        print(f"Error: {e}")
        return

    try:
        # This will raise ValueError if event doesn't exist
        async for event in contract.iter_events("NonExistentEvent"):
            pass
    except ValueError as e:
        print(f"Error: {e}")

    finally:
        await client.close()
```

## Performance Tips

1. **Use `limit` parameter** to avoid fetching too much data at once
2. **Specify block ranges** to reduce API calls
3. **Process events in batches** instead of loading all at once
4. **Reuse client instances** to benefit from connection pooling

```python
# Good: Memory-efficient streaming
async for event in contract.iter_events("Transfer", limit=1000):
    await process(event)  # Process one at a time

# Bad: Loading everything into memory
events = [e async for e in contract.iter_events("Transfer")]  # May OOM
```

## Supported Scanners

The SmartContract API works with any scanner that supports:
- `CONTRACT_SOURCE` method (for proxy detection)
- `CONTRACT_ABI` method (for ABI fetching)
- `EVENT_LOGS` method (for event iteration)
- `ACCOUNT_TRANSACTIONS` method (for transaction iteration)

Tested scanners:
- ✅ Etherscan (all networks)
- ✅ BlockScout V2
- ✅ BlockScout V1

## Migration from Manual ABI Management

**Before (v0.3.x):**
```python
# Manual ABI fetching and decoding
abi_json = await client.call(Method.CONTRACT_ABI, address="0x...")
abi = json.loads(abi_json)

# Manual transaction decoding
txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address="0x...")
for tx in txs:
    decoded = decode_transaction_input(tx, abi)
    if decoded.get('decoded_func'):
        print(decoded['decoded_func'], decoded['decoded_data'])
```

**After (v0.4.0):**
```python
# Automatic!
contract = await client.get_contract("0x...")
async for tx in contract.iter_transactions():
    print(tx.function_name, tx.args)
```

## Changelog

### v0.4.0 (2026-02-23)
- ✨ **NEW**: SmartContract high-level API
- ✨ **NEW**: Automatic proxy detection and resolution
- ✨ **NEW**: Event iteration with `iter_events()`
- ✨ **NEW**: Transaction iteration with `iter_transactions()`
- ✨ **NEW**: `ChainscanClient.get_contract()` method
- ✨ **NEW**: `DecodedEvent` and `DecodedTransaction` data classes

## See Also

- [Examples](../examples/smart_contract_demo.py) - Full working examples
- [API Reference](../README.md) - Complete API documentation
- [Architecture](ARCHITECTURE_REFACTOR.md) - System architecture overview
