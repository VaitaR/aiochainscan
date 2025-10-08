# Scripts

This directory contains automation scripts for maintaining the aiochainscan library.

## generate_chains.py

Automatically fetches and generates the chain configuration file (`aiochainscan/chains.py`) from chainid.network.

### Features

- **Automatic Discovery**: Fetches 100+ EVM chain configurations from chainid.network
- **Multi-Provider Support**: Detects Etherscan, Blockscout, and Moralis compatible chains
- **Smart Mapping**: Extracts API-specific information (domains, network names, etc.)
- **Clean Code Generation**: Produces well-formatted Python code with proper grouping

### Usage

```bash
# Generate chains.py (overwrites existing file)
python scripts/generate_chains.py

# Preview without writing
python scripts/generate_chains.py --dry-run

# Custom output path
python scripts/generate_chains.py --output /path/to/chains.py
```

### What It Does

1. Fetches latest chain data from https://chainid.network/chains.json
2. Filters chains with provider support (Etherscan/Blockscout/Moralis)
3. Generates:
   - `Chain` IntEnum with readable names (ETHEREUM, BSC, POLYGON, etc.)
   - `CHAINS` dict with full chain metadata
   - Helper functions (resolve_chain, list_chains, etc.)

### Output Statistics

Current generation yields:
- **128 total chains** with provider support
- **39 chains** with Etherscan API support
- **97 chains** with Blockscout instances
- **10 chains** with Moralis support

### Integration with Build/Release

#### Option 1: Manual Update Before Release
```bash
# Before each release, update chains:
python scripts/generate_chains.py
git add aiochainscan/chains.py
git commit -m "Update chain configurations"
```

#### Option 2: GitHub Actions (Automated)
Add to `.github/workflows/update-chains.yml`:

```yaml
name: Update Chain Configs

on:
  schedule:
    # Run weekly on Monday at 00:00 UTC
    - cron: '0 0 * * 1'
  workflow_dispatch:  # Allow manual trigger

jobs:
  update-chains:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Generate chains configuration
        run: python scripts/generate_chains.py

      - name: Create Pull Request
        uses: peter-evans/create-pull-request@v5
        with:
          commit-message: 'chore: update chain configurations'
          title: 'Update chain configurations from chainid.network'
          body: 'Automated update of supported chains'
          branch: update-chains
```

#### Option 3: Pre-commit Hook
Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: update-chains
        name: Update chain configurations
        entry: python scripts/generate_chains.py
        language: system
        pass_filenames: false
        stages: [manual]  # Only run when explicitly called
```

Then before release:
```bash
pre-commit run update-chains --all-files
```

### Provider Detection Logic

#### Etherscan API
Detects chains with explorer URLs matching:
- `etherscan.io` (Ethereum)
- `bscscan.com` (BSC)
- `polygonscan.com` (Polygon)
- `ftmscan.com` (Fantom)
- `arbiscan.io` (Arbitrum)
- `snowscan.xyz` (Avalanche)
- `optimistic.etherscan.io` (Optimism)
- `basescan.org` (Base)
- And more...

Extracts:
- `etherscan_api_kind`: API family (eth, bsc, polygon, etc.)
- `etherscan_network_name`: Network identifier (main, goerli, sepolia, etc.)

#### Blockscout
Detects chains with `blockscout` in explorer URL.

Extracts:
- `blockscout_instance`: Full domain (e.g., 'eth.blockscout.com')

#### Moralis
Hardcoded list of major chains supported by Moralis Web3 Data API.

Generates:
- `moralis_chain_id`: Hex-encoded chain ID (e.g., '0x1')

### Customization

To add custom chain name mappings, edit `_generate_enum_name()` in the script:

```python
custom_names = {
    1: 'ETHEREUM',
    56: 'BSC',
    137: 'POLYGON',
    # Add your custom mappings here
}
```

### Safety

- The script has `--dry-run` mode for testing
- Original chains.py can be backed up before running
- Generated code includes validation in `ChainInfo.__post_init__()`
- Import tests will catch any syntax errors

### Maintenance

Update the script when:
- New Etherscan-compatible domains emerge (add to `ETHERSCAN_DOMAINS`)
- Moralis adds new chain support (update `moralis_supported` in `_set_moralis_chain_id()`)
- Chain categorization needs adjustment (modify `generate_chain_enum()`)

### Troubleshooting

**Problem**: Generated enum names collide or are unclear

**Solution**: Add specific mapping in `_generate_enum_name()` custom_names dict

---

**Problem**: Chain missing from output

**Solution**: Check if chain has explorer URLs in chainid.network data. May need to add provider domain to detection logic.

---

**Problem**: Network API calls timing out

**Solution**: Increase timeout in `fetch_chains()` or use local chains.json cache

---

## Future Scripts

Planned automation scripts:
- `validate_chains.py` - Test API connectivity for all chains
- `benchmark_providers.py` - Compare provider response times
- `generate_docs.py` - Auto-generate chain support matrix for docs
