# ENS Quick Reference

## Installation

```bash
pip install git+https://github.com/VaitaR/aiochainscan.git
```

## Quick Start (30 seconds)

### Reverse Lookup (No API Key Required)

```python
import asyncio
from aiochainscan import ChainscanClient

async def main():
    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Reverse lookup
    name = await client.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    print(name)  # "vitalik.eth"

    await client.close()

asyncio.run(main())
```

### Forward Resolution (Requires Etherscan API Key)

```python
import asyncio
from aiochainscan import ChainscanClient

async def main():
    client = ChainscanClient.from_config('etherscan', 'ethereum')

    # Forward resolution
    address = await client.resolve_name("vitalik.eth")
    print(address)  # "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

    await client.close()

asyncio.run(main())
```

## API Methods

### Client Methods

| Method | Description | Returns | Scanner Support |
|--------|-------------|---------|-----------------|
| `resolve_name(name)` | Name → Address | `str \| None` | Etherscan only |
| `lookup_address(addr)` | Address → Name | `str \| None` | BlockScout V2, Etherscan |
| `resolve_names(names)` | Batch name → address | `dict[str, str]` | Etherscan only |
| `lookup_addresses(addrs)` | Batch address → name | `dict[str, str]` | BlockScout V2, Etherscan |

### ENS Resolver Properties

| Property/Method | Description |
|-----------------|-------------|
| `client.ens` | Get ENS resolver instance |
| `resolver.cache_ttl` | Cache TTL in seconds (default: 3600) |
| `resolver.enable_cache` | Whether caching is enabled |
| `await resolver.clear_cache()` | Clear the cache |

## Scanner Comparison

| Feature | BlockScout V2 | Etherscan |
|---------|---------------|-----------|
| Reverse Lookup | ✅ Free, Fast | ✅ Requires API key |
| Forward Resolution | ❌ Not supported | ✅ Requires API key |
| API Key | ❌ Not required | ✅ Required |
| Rate Limits | 🟢 Generous | 🟡 Moderate |

## Common Patterns

### Pattern 1: Enrich Transaction Data with ENS Names

```python
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

txs = await client.get_transactions(address)

for tx in txs[:10]:
    from_name = await client.lookup_address(tx['from'])
    to_name = await client.lookup_address(tx['to'])

    print(f"{from_name or tx['from'][:10]+'...'} → {to_name or tx['to'][:10]+'...'}")
```

### Pattern 2: Batch Lookup for Performance

```python
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

# Get all unique addresses
txs = await client.get_transactions(whale_address)
unique_addresses = set(tx['from'] for tx in txs) | set(tx['to'] for tx in txs)

# Batch lookup (parallel)
ens_names = await client.lookup_addresses(list(unique_addresses))

# Use lookup table
for tx in txs:
    from_name = ens_names.get(tx['from'], tx['from'][:10]+'...')
    to_name = ens_names.get(tx['to'], tx['to'][:10]+'...')
    print(f"{from_name} → {to_name}")
```

### Pattern 3: SmartContract + ENS Integration

```python
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

# Get contract
usdt = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")

# Iterate events with ENS names
async for event in usdt.iter_events("Transfer", limit=20):
    from_name = await client.lookup_address(event.args['from'])
    to_name = await client.lookup_address(event.args['to'])

    print(f"Block {event.block_number}: {from_name or 'Unknown'} → {to_name or 'Unknown'}")
```

### Pattern 4: Custom Cache Settings

```python
from aiochainscan import ChainscanClient, ENSResolver

client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

# Create custom resolver with 2-hour cache
custom_resolver = ENSResolver(
    client,
    cache_ttl=7200,  # 2 hours
    enable_cache=True
)

name = await custom_resolver.lookup_address("0xd8dA...")
```

## Error Handling

### Pattern: Graceful Degradation

```python
async def safe_lookup(client, address):
    """Lookup with fallback to short address."""
    try:
        name = await client.lookup_address(address)
        return name if name else address[:10] + "..."
    except ValueError as e:
        # ENS not supported on this network
        return address[:10] + "..."
    except Exception as e:
        # Other errors
        return address[:10] + "..."

# Use in loop
for tx in transactions:
    from_display = await safe_lookup(client, tx['from'])
    to_display = await safe_lookup(client, tx['to'])
    print(f"{from_display} → {to_display}")
```

## Performance Tips

1. **Use Batch Operations**: 10x faster for multiple addresses
   ```python
   # ❌ Slow
   for addr in addresses:
       name = await client.lookup_address(addr)

   # ✅ Fast
   names = await client.lookup_addresses(addresses)
   ```

2. **Enable Caching**: 2-100x speedup on repeated lookups
   ```python
   # Cache is enabled by default
   assert client.ens.enable_cache == True
   ```

3. **Pre-fetch Common Names**: Reduce latency for known addresses
   ```python
   common_addresses = ["0xd8dA...", "0xb8c2..."]
   names = await client.lookup_addresses(common_addresses)
   # Now cached for future use
   ```

## Limitations

| Limitation | Workaround |
|------------|------------|
| Only Ethereum mainnet | Check `client.chain_id == 1` before using |
| Forward resolution needs Etherscan | Use Etherscan scanner for name → address |
| Rate limits apply | Use built-in rate limiter |
| No subdomain support | Full implementation in future version |

## Network Support

```python
# ✅ Supported
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

# ❌ Not supported (will raise ValueError)
client = ChainscanClient.from_config('blockscout_v2', 'polygon')
await client.lookup_address("0x...")  # Raises: ValueError: ENS is only supported on Ethereum mainnet
```

## Examples

| Example | Location | Description |
|---------|----------|-------------|
| Simple Demo | `examples/ens_simple_demo.py` | Quick start (reverse lookup) |
| Full Demo | `examples/ens_demo.py` | All features with 7 use cases |
| Integration | `docs/ENS_INTEGRATION.md` | Complete guide |

## Troubleshooting

### Problem: Forward resolution returns None
**Solution:** Use Etherscan instead of BlockScout V2
```python
# Change from:
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

# To:
client = ChainscanClient.from_config('etherscan', 'ethereum')
```

### Problem: ValueError about unsupported network
**Solution:** Verify you're using Ethereum mainnet
```python
print(f"Chain ID: {client.chain_id}")  # Must be 1
print(f"Network: {client.network}")    # Must be 'ethereum' or 'main'
```

### Problem: Slow performance
**Solutions:**
1. Enable caching (enabled by default)
2. Use batch operations
3. Pre-fetch common addresses

## More Information

- 📚 [Full Documentation](../docs/ENS_INTEGRATION.md)
- 🎯 [Examples](../examples/)
- 🐛 [GitHub Issues](https://github.com/VaitaR/aiochainscan/issues)

---

**Version:** aiochainscan v0.4.0
**Status:** ✅ Production Ready
**License:** MIT
