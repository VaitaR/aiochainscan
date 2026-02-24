# SmartContract API - Quick Reference

## One-Line Setup

```python
from aiochainscan import ChainscanClient

client = ChainscanClient.from_config('etherscan', 'ethereum')
contract = await client.get_contract("0xContractAddress")
```

## Common Operations

### Get Contract Info
```python
contract = await client.get_contract("0x...")
print(contract.is_proxy)              # Check if proxy
print(contract.implementation_address) # Implementation if proxy
```

### Iterate Events
```python
# All Transfer events
async for event in contract.iter_events("Transfer", limit=100):
    print(event.args['from'], event.args['to'], event.args['value'])

# Events in block range
async for event in contract.iter_events(
    "Transfer",
    from_block=19000000,
    to_block=19001000
):
    print(event.block_number, event.args)

# All events (no filter)
async for event in contract.iter_events(limit=1000):
    print(event.name, event.args)
```

### Iterate Transactions
```python
# All transactions to the contract
async for tx in contract.iter_transactions(limit=100):
    print(tx.function_name, tx.args)
    print(tx.from_address, tx.value_wei)

# Transactions in block range
async for tx in contract.iter_transactions(
    from_block=19000000,
    to_block=19001000
):
    print(tx.block_number, tx.function_name)
```

### Get ABI Info
```python
# Get event ABI
transfer_abi = contract.get_event_abi("Transfer")
print(transfer_abi['inputs'])

# Get function ABI
transfer_func = contract.get_function_abi("transfer")
print(transfer_func['inputs'])
```

## Event Object

```python
event.name           # Event name (e.g., "Transfer")
event.args           # Dict of decoded arguments
event.block_number   # Block number
event.tx_hash        # Transaction hash
event.address        # Contract address
event.log_index      # Log index in transaction
event.raw_log        # Original raw log data
```

## Transaction Object

```python
tx.function_name     # Function called (e.g., "transfer")
tx.args              # Dict of decoded arguments
tx.from_address      # Sender address
tx.to_address        # Contract address
tx.value_wei         # ETH sent (in Wei)
tx.block_number      # Block number
tx.tx_hash           # Transaction hash
tx.gas               # Gas limit
tx.gas_price_wei     # Gas price (in Wei)
tx.raw_transaction   # Original raw transaction
```

## Common Patterns

### Process Events in Batches
```python
batch = []
async for event in contract.iter_events("Transfer", limit=10000):
    batch.append(event)
    if len(batch) >= 100:
        await process_batch(batch)
        batch = []
if batch:
    await process_batch(batch)
```

### Export to CSV
```python
import csv
with open('events.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['Block', 'From', 'To', 'Value'])
    async for event in contract.iter_events("Transfer", limit=1000):
        writer.writerow([
            event.block_number,
            event.args['from'],
            event.args['to'],
            event.args['value']
        ])
```

### Count Function Calls
```python
counts = {}
async for tx in contract.iter_transactions(limit=1000):
    counts[tx.function_name] = counts.get(tx.function_name, 0) + 1
print(counts)
```

### Filter by Value
```python
# Only large transfers
async for event in contract.iter_events("Transfer"):
    value = event.args['value']
    if value > 1000000 * 10**6:  # > 1M USDT
        print(f"Large transfer: {value / 10**6}M USDT")
```

## Error Handling

```python
try:
    contract = await client.get_contract("0x...")
except ValueError as e:
    print(f"Contract not found or ABI unavailable: {e}")

try:
    async for event in contract.iter_events("InvalidEvent"):
        pass
except ValueError as e:
    print(f"Event not in ABI: {e}")
```

## Performance Tips

✅ **DO**: Use `limit` to control memory usage
```python
async for event in contract.iter_events("Transfer", limit=1000):
    process(event)
```

✅ **DO**: Specify block ranges to reduce API calls
```python
async for event in contract.iter_events(
    "Transfer",
    from_block=19000000,
    to_block=19001000
):
    process(event)
```

❌ **DON'T**: Load all events into memory
```python
# Bad - may cause OOM
events = [e async for e in contract.iter_events("Transfer")]
```

✅ **DO**: Process events one at a time or in small batches
```python
async for event in contract.iter_events("Transfer"):
    await process(event)  # Process immediately
```

## Common Contracts

```python
# USDT (Proxy)
usdt = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")

# USDC (Proxy)
usdc = await client.get_contract("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")

# DAI
dai = await client.get_contract("0x6b175474e89094c44da98b954eedeac495271d0f")

# Uniswap V2 Router
router = await client.get_contract("0x7a250d5630b4cf539739df2c5dacb4c659f2488d")

# WETH
weth = await client.get_contract("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2")
```

## Full Example

```python
import asyncio
from aiochainscan import ChainscanClient

async def analyze_usdt():
    client = ChainscanClient.from_config('etherscan', 'ethereum')

    # Get USDT contract
    usdt = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")

    print(f"Proxy: {usdt.is_proxy}")
    print(f"Implementation: {usdt.implementation_address}")

    # Analyze recent transfers
    total_volume = 0
    count = 0

    async for event in usdt.iter_events("Transfer", limit=1000):
        value = event.args['value'] / 1e6  # USDT has 6 decimals
        total_volume += value
        count += 1

    print(f"Transfers: {count}")
    print(f"Volume: ${total_volume:,.2f}")

    await client.close()

asyncio.run(analyze_usdt())
```

---

**Full Documentation**: [docs/SMART_CONTRACT_API.md](SMART_CONTRACT_API.md)
**Examples**: [examples/smart_contract_demo.py](../examples/smart_contract_demo.py)
