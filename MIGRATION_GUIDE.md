# Migration Guide: Provider-First API (v0.3.0)

## Overview

Version 0.3.0 introduces a new **provider-first API** that provides a cleaner, more intuitive way to work with blockchain scanner APIs. The new API:

- ✅ Clear separation between **provider** (Etherscan, BlockScout) and **chain** (Ethereum, BSC)
- ✅ Support for **chain IDs** (aligns with Etherscan V2 API)
- ✅ Flexible chain selection: by ID, name, alias, or enum
- ✅ Type-safe with IDE autocomplete
- ✅ Discoverable APIs for listing chains and providers
- ✅ **Zero breaking changes** - old APIs still work

## Quick Start

### New API (Recommended)

```python
from aiochainscan import ChainProvider

# By chain ID (most explicit)
client = ChainProvider.etherscan(chain_id=1)  # Ethereum
client = ChainProvider.blockscout(chain_id=11155111)  # Sepolia

# By chain name
client = ChainProvider.etherscan(chain='ethereum')
client = ChainProvider.blockscout(chain='sepolia')

# By Chain enum (type-safe)
from aiochainscan import Chain
client = ChainProvider.etherscan(chain=Chain.ETHEREUM)
client = ChainProvider.blockscout(chain=Chain.SEPOLIA)

# Make API calls (same across all providers)
from aiochainscan.core.method import Method
balance = await client.call(Method.ACCOUNT_BALANCE, address='0x...')
```

### Old API (Still Supported)

```python
from aiochainscan import Client

# Old way still works
client = Client.from_config('eth', 'main')
balance = await client.account.balance('0x...')
```

## Migration Paths

### Scenario 1: Migrating from Legacy Client

**Before:**
```python
from aiochainscan import Client

# Ethereum mainnet
client = Client.from_config('eth', 'main')
balance = await client.account.balance(address)

# BSC
client = Client.from_config('bsc', 'main')
balance = await client.account.balance(address)
```

**After:**
```python
from aiochainscan import ChainProvider
from aiochainscan.core.method import Method

# Ethereum mainnet
client = ChainProvider.etherscan(chain_id=1)
balance = await client.call(Method.ACCOUNT_BALANCE, address=address)

# BSC
client = ChainProvider.etherscan(chain_id=56)
balance = await client.call(Method.ACCOUNT_BALANCE, address=address)
```

### Scenario 2: Migrating BlockScout Usage

**Before:**
```python
from aiochainscan import Client

# BlockScout Sepolia (confusing naming)
client = Client.from_config('blockscout_sepolia', 'sepolia')
balance = await client.account.balance(address)
```

**After:**
```python
from aiochainscan import ChainProvider

# Clear: BlockScout provider + Sepolia chain
client = ChainProvider.blockscout(chain='sepolia')
balance = await client.call(Method.ACCOUNT_BALANCE, address=address)
```

### Scenario 3: Working with Multiple Chains

**Before:**
```python
chains = [
    ('eth', 'main'),
    ('bsc', 'main'),
    ('polygon', 'main'),
]

for api_kind, network in chains:
    client = Client.from_config(api_kind, network)
    # ...
```

**After:**
```python
from aiochainscan import ChainProvider, Chain

chains = [Chain.ETHEREUM, Chain.BSC, Chain.POLYGON]

for chain in chains:
    client = ChainProvider.etherscan(chain=chain)
    # ...
```

### Scenario 4: Dynamic Chain Discovery

**Before:**
```python
# Had to know exact scanner names
available = Client.get_supported_scanners()
# Returns: ['eth', 'bsc', 'blockscout_eth', 'blockscout_sepolia', ...]
```

**After:**
```python
from aiochainscan import ChainProvider

# List all providers
providers = ChainProvider.list_providers()
# Returns: ['etherscan', 'blockscout', 'moralis']

# List all chains
chains = ChainProvider.list_chains()
# Returns: [ChainInfo(chain_id=1, name='ethereum', ...), ...]

# List chains by provider
blockscout_chains = ChainProvider.list_chains(provider='blockscout')

# List mainnets only
mainnets = ChainProvider.list_chains(testnet=False)
```

## API Reference

### ChainProvider Factory Methods

```python
class ChainProvider:
    @staticmethod
    def etherscan(
        chain: int | str | Chain | None = None,
        chain_id: int | None = None,
        api_key: str | None = None,
        **kwargs
    ) -> ChainscanClient:
        """Create Etherscan client for any supported chain."""

    @staticmethod
    def blockscout(
        chain: int | str | Chain | None = None,
        chain_id: int | None = None,
        api_key: str | None = None,
        **kwargs
    ) -> ChainscanClient:
        """Create BlockScout client (no API key required)."""

    @staticmethod
    def moralis(
        chain: int | str | Chain | None = None,
        chain_id: int | None = None,
        api_key: str | None = None,
        **kwargs
    ) -> ChainscanClient:
        """Create Moralis Web3 Data API client."""

    @staticmethod
    def list_providers() -> list[str]:
        """Get list of available providers."""

    @staticmethod
    def list_chains(
        provider: str | None = None,
        testnet: bool | None = None
    ) -> list[ChainInfo]:
        """List all supported chains, optionally filtered."""

    @staticmethod
    def get_chain_info(chain: int | str | Chain) -> ChainInfo:
        """Get detailed information about a specific chain."""
```

### Chain Identification

Three ways to specify a chain:

1. **By Chain ID** (recommended for production):
   ```python
   client = ChainProvider.etherscan(chain_id=1)  # Ethereum
   client = ChainProvider.etherscan(chain_id=56)  # BSC
   client = ChainProvider.etherscan(chain_id=137)  # Polygon
   ```

2. **By Name or Alias** (convenient for scripts):
   ```python
   client = ChainProvider.etherscan(chain='ethereum')
   client = ChainProvider.etherscan(chain='eth')  # alias
   client = ChainProvider.etherscan(chain='mainnet')  # alias
   ```

3. **By Chain Enum** (type-safe, IDE-friendly):
   ```python
   from aiochainscan import Chain

   client = ChainProvider.etherscan(chain=Chain.ETHEREUM)
   client = ChainProvider.etherscan(chain=Chain.BSC)
   client = ChainProvider.etherscan(chain=Chain.POLYGON)
   ```

### Supported Chains

#### Ethereum Networks
- **Ethereum Mainnet** - ID: 1, names: `ethereum`, `eth`, `mainnet`
- **Sepolia** - ID: 11155111, names: `sepolia`, `eth-sepolia`
- **Goerli** (deprecated) - ID: 5, names: `goerli`, `eth-goerli`
- **Holesky** - ID: 17000, names: `holesky`

#### Layer 2 Networks
- **Optimism** - ID: 10, names: `optimism`, `op`
- **Arbitrum One** - ID: 42161, names: `arbitrum`, `arb`
- **Base** - ID: 8453, names: `base`
- **Blast** - ID: 81457, names: `blast`
- **Scroll** - ID: 534352, names: `scroll`
- **Linea** - ID: 59144, names: `linea`
- **Mode** - ID: 34443, names: `mode`

#### Other EVM Networks
- **BSC** - ID: 56, names: `bsc`, `binance`, `bnb`
- **Polygon** - ID: 137, names: `polygon`, `matic`
- **Avalanche** - ID: 43114, names: `avalanche`, `avax`
- **Fantom** - ID: 250, names: `fantom`, `ftm`
- **Gnosis** - ID: 100, names: `gnosis`, `xdai`

See `ChainProvider.list_chains()` for full list.

## Provider Comparison

| Provider | API Key Required | Chains Supported | Key Features |
|----------|------------------|------------------|--------------|
| **Etherscan** | ✅ Yes | 14+ | Most comprehensive, V2 API supports 50+ chains |
| **BlockScout** | ❌ No | 9 | Free, public APIs, great for development |
| **Moralis** | ✅ Yes | 7 | Rich metadata, modern REST API |

## Environment Variables

The library automatically reads API keys from environment variables:

```bash
# Etherscan (works for all Etherscan-based scanners after V2 migration)
export ETHERSCAN_KEY=your_etherscan_api_key

# Moralis
export MORALIS_API_KEY=your_moralis_api_key

# BlockScout (optional, most instances don't require keys)
export BLOCKSCOUT_API_KEY=your_blockscout_key
```

Or pass explicitly:

```python
client = ChainProvider.etherscan(chain_id=1, api_key='YOUR_KEY')
```

## Error Handling

### Chain Not Supported

```python
try:
    # Try to use Avalanche with BlockScout (not supported)
    client = ChainProvider.blockscout(chain='avalanche')
except ValueError as e:
    print(e)
    # "Chain 'Avalanche C-Chain' (ID: 43114) does not have a BlockScout instance."

    # Discover which chains are supported
    supported = ChainProvider.list_chains(provider='blockscout')
    print(f"Supported: {[c.name for c in supported]}")
```

### Missing API Key

```python
try:
    client = ChainProvider.etherscan(chain_id=1)  # No api_key param
except ValueError as e:
    print(e)
    # "Etherscan API key required. Set ETHERSCAN_KEY environment variable..."
```

### Unknown Chain

```python
try:
    client = ChainProvider.etherscan(chain='unknown_chain')
except ValueError as e:
    print(e)
    # "Unknown chain: 'unknown_chain'. Available chains: ..."
```

## Best Practices

### 1. Use Chain IDs in Production

Chain IDs are standardized (EIP-155) and unambiguous:

```python
# ✅ Good - explicit and unambiguous
client = ChainProvider.etherscan(chain_id=1)
client = ChainProvider.etherscan(chain_id=56)

# ❌ Avoid - names can be ambiguous
client = ChainProvider.etherscan(chain='main')  # Which main?
```

### 2. Use Chain Enum for Type Safety

```python
from aiochainscan import Chain

def get_balance(chain: Chain, address: str):
    client = ChainProvider.etherscan(chain=chain)
    # IDE autocomplete works here!
    return await client.call(Method.ACCOUNT_BALANCE, address=address)

# IDE will suggest: Chain.ETHEREUM, Chain.BSC, etc.
balance = await get_balance(Chain.ETHEREUM, '0x...')
```

### 3. Discover Chains Dynamically

```python
# List all chains with Etherscan support
etherscan_chains = ChainProvider.list_chains(provider='etherscan', testnet=False)

for chain in etherscan_chains:
    print(f"Checking {chain.display_name}...")
    client = ChainProvider.etherscan(chain_id=chain.chain_id)
    # ...
```

### 4. Graceful Fallback Between Providers

```python
async def get_balance_with_fallback(chain_id: int, address: str):
    providers = [
        ('blockscout', lambda: ChainProvider.blockscout(chain_id=chain_id)),
        ('etherscan', lambda: ChainProvider.etherscan(chain_id=chain_id)),
        ('moralis', lambda: ChainProvider.moralis(chain_id=chain_id)),
    ]

    for name, factory in providers:
        try:
            client = factory()
            balance = await client.call(Method.ACCOUNT_BALANCE, address=address)
            return balance
        except ValueError:
            continue  # Chain not supported by this provider

    raise ValueError(f"No provider supports chain ID {chain_id}")
```

## Corner Cases

### 1. Testnets vs Mainnets with Same Name

Use chain IDs to disambiguate:

```python
# BSC Mainnet
client = ChainProvider.etherscan(chain_id=56)

# BSC Testnet
client = ChainProvider.etherscan(chain_id=97)

# Filter by testnet status
mainnets = ChainProvider.list_chains(testnet=False)
testnets = ChainProvider.list_chains(testnet=True)
```

### 2. Etherscan V2 Multi-Chain Support

After Etherscan V2 API migration, one API key works for all chains:

```python
# Same API key for all chains!
eth_client = ChainProvider.etherscan(chain_id=1, api_key='YOUR_KEY')
bsc_client = ChainProvider.etherscan(chain_id=56, api_key='YOUR_KEY')
polygon_client = ChainProvider.etherscan(chain_id=137, api_key='YOUR_KEY')
```

### 3. BlockScout Multiple Instances

BlockScout has different instances for different chains:

```python
# Each chain maps to a different BlockScout instance
eth_client = ChainProvider.blockscout(chain_id=1)  # eth.blockscout.com
sepolia_client = ChainProvider.blockscout(chain_id=11155111)  # eth-sepolia.blockscout.com
gnosis_client = ChainProvider.blockscout(chain_id=100)  # gnosis.blockscout.com
```

## FAQ

**Q: Do I need to migrate immediately?**
A: No, the old API (`Client.from_config()`) still works. Migrate when convenient.

**Q: Can I use both APIs in the same project?**
A: Yes, they work side-by-side.

**Q: How do I add a new chain?**
A: Edit `aiochainscan/chains.py` and add a new `ChainInfo` entry to the `CHAINS` dict.

**Q: What about custom scanners?**
A: The new API focuses on the main providers. For custom scanners, use the `ChainscanClient` class directly.

**Q: Will the old API be deprecated?**
A: Not in the near term. It will be maintained for backward compatibility.

## Examples

See `examples/chain_provider_demo.py` for a comprehensive demonstration of the new API.

## Feedback

This is a major architectural improvement. If you encounter any issues or have suggestions, please open an issue on GitHub.
