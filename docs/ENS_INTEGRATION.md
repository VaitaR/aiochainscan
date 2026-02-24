# ENS Integration

## Overview

aiochainscan v0.4.0+ includes native support for ENS (Ethereum Name Service), allowing you to:

- **Forward resolution**: Resolve ENS names (like `vitalik.eth`) to Ethereum addresses
- **Reverse lookup**: Find the ENS name associated with an Ethereum address
- **Batch operations**: Resolve multiple names or addresses in parallel
- **Automatic caching**: Intelligent caching with TTL for improved performance
- **Multi-scanner support**: Works with BlockScout V2, Etherscan, and other scanners

## Quick Start

```python
import asyncio
from aiochainscan import ChainscanClient

async def main():
    # Create client (ENS only works on Ethereum mainnet)
    # Use BlockScout V2 for reverse lookup (no API key required)
    client = ChainscanClient.from_config('blockscout_v2', 'ethereum')

    # Reverse lookup: address → name (works with BlockScout V2)
    name = await client.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    print(f"Name: {name}")
    # Output: Name: vitalik.eth

    # Note: Forward resolution (name → address) requires Etherscan
    # because BlockScout V2 doesn't expose eth_call

    # For forward resolution, use Etherscan (requires API key)
    client_etherscan = ChainscanClient.from_config('etherscan', 'ethereum')
    address = await client_etherscan.resolve_name("vitalik.eth")
    print(f"Address: {address}")
    # Output: Address: 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045

asyncio.run(main())
```

## Features

### 1. Forward Resolution

Resolve ENS names to Ethereum addresses:

```python
# Single name resolution
address = await client.resolve_name("vitalik.eth")

# Batch resolution (parallel)
addresses = await client.resolve_names([
    "vitalik.eth",
    "uniswap.eth",
    "ens.eth"
])
# Returns: {"vitalik.eth": "0xd8dA...", "uniswap.eth": "0x1f98...", ...}
```

### 2. Reverse Lookup

Find ENS names from Ethereum addresses:

```python
# Single address lookup
name = await client.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")

# Batch lookup (parallel)
names = await client.lookup_addresses([
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"
])
# Returns: {"0xd8dA...": "vitalik.eth", "0x1f98...": "uniswap.eth"}
```

### 3. Advanced ENS Resolver Access

For advanced use cases, access the ENS resolver directly:

```python
# Get ENS resolver instance
resolver = client.ens

# Check cache status
print(f"Cache enabled: {resolver.enable_cache}")
print(f"Cache TTL: {resolver.cache_ttl} seconds")

# Clear cache
await resolver.clear_cache()

# Custom resolver with different settings
from aiochainscan.services.ens_resolver import ENSResolver

custom_resolver = ENSResolver(
    client,
    cache_ttl=7200,  # 2 hours
    enable_cache=True
)
address = await custom_resolver.resolve_name("vitalik.eth")
```

## How It Works

### Scanner Support

ENS resolution uses different strategies depending on the scanner:

#### BlockScout V2 (Recommended for Reverse Lookup)
- **Reverse lookup**: ✅ Uses the `ens_domain_name` field from address info API (fast and free)
- **Forward resolution**: ❌ Not supported (would require `eth_call` which BlockScout V2 doesn't expose)
- **Advantages**: Fast reverse lookups, no API key required, works out of the box

#### Etherscan (Required for Forward Resolution)
- **Both directions**: ✅ Uses direct ENS contract calls via `eth_call`
- **Requires**: API key for `eth_call` support
- **Advantages**: Works for both forward and reverse resolution
- **Note**: Forward resolution requires the PROXY module to be enabled

**Important**: For forward resolution (name → address), you must use Etherscan or another scanner that supports `eth_call`. BlockScout V2 only supports reverse lookup (address → name).

```python
# ✅ Reverse lookup works with BlockScout V2 (no API key)
client = ChainscanClient.from_config('blockscout_v2', 'ethereum')
name = await client.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
# Returns: "vitalik.eth"

# ❌ Forward resolution NOT supported with BlockScout V2
address = await client.resolve_name("vitalik.eth")
# Returns: None (requires eth_call)

# ✅ Use Etherscan for forward resolution (requires API key)
client = ChainscanClient.from_config('etherscan', 'ethereum')
address = await client.resolve_name("vitalik.eth")
# Returns: "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
```

#### ENS Contract Calls (Fallback)
When scanner-specific methods aren't available, aiochainscan directly queries the ENS smart contracts:

- **ENS Registry**: `0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e`
- **Public Resolver**: `0x4976fb03C32e5B8cfe2b6cCB31c09Ba78EBaBa41`

The library implements:
- Namehash algorithm (EIP-137)
- EIP-55 checksum address conversion
- ABI encoding/decoding for contract calls

### Caching Strategy

ENS resolution results are cached aggressively because:
- ENS names are relatively stable
- Resolution can be slow (requires API calls or contract queries)
- Same names are often resolved multiple times

**Cache features**:
- Default TTL: 1 hour (configurable)
- Bidirectional: Caching forward resolution also caches reverse
- LRU eviction: Least recently used entries removed first
- In-memory: No persistence (cleared on restart)
- Optional: Can be disabled via `enable_cache=False`

**Cache warming**:
Common ENS names are pre-cached:
- `vitalik.eth`
- `nick.eth`

## Network Support

### Ethereum Mainnet Only

ENS is **only available on Ethereum mainnet** (chain_id = 1).

Attempting to use ENS on other networks will raise a `ValueError`:

```python
client = ChainscanClient.from_config('blockscout_v2', 'polygon')
await client.resolve_name("vitalik.eth")
# Raises: ValueError: ENS is only supported on Ethereum mainnet
```

### Future: Other Name Services

Other blockchains have their own name services:
- **BNB Chain**: BNS (BNB Name Service)
- **Polygon**: Unstoppable Domains
- **Arbitrum**: Arbitrum Name Service

These may be added in future versions.

## Integration Examples

### With SmartContract API

Combine ENS with the SmartContract API:

```python
# Resolve ENS name to contract address
contract_address = await client.resolve_name("uniswap.eth")

# Get contract instance
contract = await client.get_contract(contract_address)

# Iterate through events
async for event in contract.iter_events("Transfer", limit=100):
    # Reverse lookup to get ENS names for addresses
    from_name = await client.lookup_address(event.args['from'])
    to_name = await client.lookup_address(event.args['to'])

    print(f"{from_name or event.args['from']} → {to_name or event.args['to']}")
```

### With Transaction Analysis

Enrich transaction data with ENS names:

```python
# Get transactions
txs = await client.get_transactions(address)

# Add ENS names to addresses
for tx in txs[:10]:  # First 10 transactions
    from_name = await client.lookup_address(tx['from'])
    to_name = await client.lookup_address(tx['to'])

    print(f"{from_name or tx['from'][:10]+'...'} → {to_name or tx['to'][:10]+'...'}")
```

### Batch Processing

For whale addresses with many counterparties:

```python
# Get all transactions
txs = await client.get_transactions(whale_address)

# Extract unique addresses
unique_addresses = set()
for tx in txs:
    unique_addresses.add(tx['from'])
    unique_addresses.add(tx['to'])

# Batch reverse lookup (parallel)
ens_names = await client.lookup_addresses(list(unique_addresses))

# Create lookup table
print(f"Found ENS names for {len(ens_names)}/{len(unique_addresses)} addresses")
for addr, name in ens_names.items():
    print(f"  {name}: {addr}")
```

## Error Handling

### Invalid Inputs

Invalid inputs return `None` instead of raising errors:

```python
# Invalid name formats
assert await client.resolve_name("") is None
assert await client.resolve_name("invalid") is None
assert await client.resolve_name("test.com") is None  # Not .eth

# Invalid addresses
assert await client.lookup_address("") is None
assert await client.lookup_address("0x123") is None
```

### Network Errors

Network-related errors are handled gracefully:

```python
try:
    address = await client.resolve_name("vitalik.eth")
except ValueError as e:
    print(f"ENS not supported: {e}")
except Exception as e:
    print(f"Resolution failed: {e}")
```

### Unsupported Networks

Attempting ENS on non-Ethereum networks raises `ValueError`:

```python
from aiochainscan.exceptions import ChainscanClientApiError

try:
    client = ChainscanClient.from_config('blockscout_v2', 'polygon')
    await client.resolve_name("vitalik.eth")
except ValueError as e:
    print(f"Error: {e}")
    # Error: ENS is only supported on Ethereum mainnet
```

## Performance Considerations

### Caching Impact

Caching provides significant performance improvements:

```python
import time

# First resolution (cache miss)
start = time.time()
await client.resolve_name("vitalik.eth")
first_time = time.time() - start
print(f"First: {first_time:.3f}s")

# Second resolution (cache hit)
start = time.time()
await client.resolve_name("vitalik.eth")
cached_time = time.time() - start
print(f"Cached: {cached_time:.3f}s")

# Typical speedup: 10-100x
```

### Batch Operations

Batch operations use parallel requests:

```python
# Sequential (slow)
for name in names:
    await client.resolve_name(name)  # One by one

# Parallel (fast)
await client.resolve_names(names)  # All at once
```

Speedup scales with number of names (up to connection limits).

## API Reference

### ChainscanClient Methods

#### `resolve_name(name: str) -> str | None`

Resolve ENS name to Ethereum address.

**Parameters**:
- `name` (str): ENS name (e.g., "vitalik.eth")

**Returns**:
- `str | None`: Ethereum address or None if not found

**Raises**:
- `ValueError`: If ENS not supported on this network

**Example**:
```python
address = await client.resolve_name("vitalik.eth")
```

#### `lookup_address(address: str) -> str | None`

Reverse lookup: Ethereum address to ENS name.

**Parameters**:
- `address` (str): Ethereum address

**Returns**:
- `str | None`: ENS name or None if not found

**Raises**:
- `ValueError`: If ENS not supported on this network

**Example**:
```python
name = await client.lookup_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
```

#### `resolve_names(names: list[str]) -> dict[str, str]`

Batch resolve multiple ENS names (parallel).

**Parameters**:
- `names` (list[str]): List of ENS names

**Returns**:
- `dict[str, str]`: Mapping of names to addresses (only successful)

**Example**:
```python
result = await client.resolve_names(["vitalik.eth", "uniswap.eth"])
```

#### `lookup_addresses(addresses: list[str]) -> dict[str, str]`

Batch reverse lookup (parallel).

**Parameters**:
- `addresses` (list[str]): List of Ethereum addresses

**Returns**:
- `dict[str, str]`: Mapping of addresses to names (only successful)

**Example**:
```python
result = await client.lookup_addresses(["0xd8dA...", "0x1f98..."])
```

#### `ens` (property)

Get ENS resolver instance.

**Returns**:
- `ENSResolver`: Resolver instance (lazy-initialized)

**Example**:
```python
resolver = client.ens
await resolver.clear_cache()
```

### ENSResolver Class

#### `__init__(client, cache_ttl=3600, enable_cache=True)`

Create ENS resolver instance.

**Parameters**:
- `client` (ChainscanClient): Client instance
- `cache_ttl` (int): Cache TTL in seconds (default: 3600)
- `enable_cache` (bool): Enable caching (default: True)

#### `clear_cache() -> None`

Clear the resolution cache.

**Example**:
```python
await resolver.clear_cache()
```

## Troubleshooting

### ENS Not Found

If resolution returns `None`:

1. **Verify name format**: Must end with `.eth`
2. **Check if name exists**: Use etherscan.io to verify
3. **Try reverse lookup**: Some names may not have forward resolution set up
4. **Clear cache**: `await client.ens.clear_cache()`

### Slow Performance

If resolution is slow:

1. **Enable caching**: Default is enabled, but check `client.ens.enable_cache`
2. **Use batch operations**: `resolve_names()` instead of multiple `resolve_name()`
3. **Increase cache TTL**: For static environments, use longer TTL
4. **Check network latency**: ENS contracts are on Ethereum mainnet

### Network Not Supported

If you get `ValueError: ENS is only supported on Ethereum mainnet`:

1. **Verify network**: Must be Ethereum mainnet (chain_id = 1)
2. **Check client config**: `client.chain_id` should be 1
3. **Use correct network**: `from_config('blockscout_v2', 'ethereum')`

## Examples

See [`examples/ens_demo.py`](../examples/ens_demo.py) for comprehensive examples including:

- Forward resolution
- Reverse lookup
- Batch operations
- Caching behavior
- Integration with SmartContract API
- Error handling
- Performance testing

Run the demo:
```bash
python examples/ens_demo.py
```

## Related Documentation

- [SMART_CONTRACT_API.md](SMART_CONTRACT_API.md) - SmartContract integration
- [STREAMING_DECODER.md](STREAMING_DECODER.md) - Transaction/event decoding
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - API overview

## Future Enhancements

Planned improvements:

- [ ] Support for other name services (BNS, etc.)
- [ ] Persistent cache with Redis
- [ ] Subdomain resolution
- [ ] Text records (avatar, description, etc.)
- [ ] Contenthash resolution (IPFS/Swarm)
- [ ] ENS name registration status
- [ ] Expiration date lookup

## Contributing

Found a bug or have a feature request? Please open an issue on GitHub!
