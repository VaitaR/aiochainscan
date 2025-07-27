# aiochainscan Examples

This directory contains example scripts demonstrating the usage of the aiochainscan library.

## 🆕 **NEW: Unified Architecture Examples**

### `simple_balance_comparison.py` ⭐

**QUICK START** - Compare legacy vs unified client architecture:

```bash
python examples/simple_balance_comparison.py
```

- **Purpose**: Demonstrates the new unified `ChainscanClient` vs legacy `Client`
- **Shows**: How same balance can be retrieved using different approaches
- **Output**: Side-by-side comparison proving backward compatibility
- **Key benefit**: Type-safe `Method` enum vs string-based calls

### `balance_comparison.py`

**ADVANCED** - Multi-scanner balance comparison:

```bash
python examples/balance_comparison.py
```

- **Purpose**: Compare balance retrieval across different scanner implementations
- **Features**: Etherscan, OKLink support with automatic parameter mapping
- **Shows**: How unified interface works across different APIs

### `unified_client_demo.py`

**COMPREHENSIVE** - Complete unified architecture demonstration:

```bash
python examples/unified_client_demo.py
```

- **Purpose**: Full showcase of the new scanner architecture
- **Features**:
  - Available scanner implementations and capabilities
  - Method support comparison matrix
  - Error handling demonstration
  - Scanner registry system
- **Output**: Interactive demo of all unified architecture features

## Traditional Examples

### `quick_scanner_check.py` 

**QUICK START** - Fast connectivity test for all scanners with minimal API calls:

- **Purpose**: Quick overview of scanner status and API key configuration
- **Speed**: Fast single method test per scanner (block_number only)
- **Output**: Console summary showing working/broken scanners
- **Use case**: Initial setup validation and troubleshooting

### `test_scanner_methods.py`

**COMPREHENSIVE** - Full test script that validates all API methods across all supported blockchain scanners:

- **Purpose**: Tests all available API methods for each scanner to determine compatibility
- **Coverage**: Tests all modules (proxy, account, stats, block, transaction, logs, gas_tracker, token, contract)
- **Networks**: Tests main networks (and testnet for Ethereum)
- **Features tested**:
  - Scanner configuration and API key validation
  - Method-by-method testing with detailed error reporting
  - Performance measurement (execution time per method)
  - Success rate analysis per scanner and module
  - Comprehensive reporting with multiple output formats

### `test_decode_functionality.py`

Comprehensive test script that validates the decode functionality using **real Ethereum mainnet data**:

- **Purpose**: Tests the library's ability to fetch and decode real blockchain data
- **Network**: Ethereum Mainnet via Etherscan API
- **Contract**: UNI Token (0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984)
- **Features tested**:
  - Fetching real logs from UNI token contract (5 pages)
  - Fetching real transactions with input data (5 pages)
  - Fetching verified contract ABI from Etherscan
  - Decoding logs using real contract ABI
  - Decoding transactions using two methods:
    - Real contract ABI-based decoding
    - Online signature lookup decoding

## Setup

1. **Install dependencies:**
```bash
uv sync --extra dev
```

2. **Set up API keys:**

Create a `.env` file in the project root:
```bash
# .env
ETHERSCAN_KEY=your_etherscan_api_key_here
OKLINK_KEY=your_oklink_api_key_here  # Optional for OKLink examples
BSCSCAN_KEY=your_bscscan_api_key_here  # Optional for BSC
POLYGONSCAN_KEY=your_polygonscan_api_key_here  # Optional for Polygon
```

Get API keys at:
- **Etherscan**: https://etherscan.io/apis
- **OKLink**: https://www.oklink.com/account/my-api
- **BSCScan**: https://bscscan.com/apis
- **PolygonScan**: https://polygonscan.com/apis

## Quick Start Guide

### 1. **Try the New Architecture** (Recommended)
```bash
# Set your Etherscan API key
export ETHERSCAN_KEY="your_key_here"

# Compare legacy vs unified approach
python examples/simple_balance_comparison.py
```

**Output:**
```
🔍 Getting balance for: 0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97

1️⃣ Legacy Client (traditional way):
   15010879002106550271 wei
   15.010879 ETH

2️⃣ ChainscanClient (new unified way):
   15010879002106550271 wei
   15.010879 ETH

✅ Both methods return identical results!
```

### 2. **Explore Scanner Capabilities**
```bash
# See all available scanners and methods
python examples/unified_client_demo.py
```

### 3. **Test Traditional Features**
```bash
# Quick connectivity test
python examples/quick_scanner_check.py

# Full method testing
python examples/test_scanner_methods.py
```

## Architecture Comparison

### 🔄 **Legacy Approach** (Per-Module)
```python
from aiochainscan import Client

client = Client.from_config('eth', 'main')
balance = await client.account.balance(address)
txs = await client.account.normal_txs(address)
await client.close()
```

### 🆕 **Unified Approach** (Cross-Scanner)
```python
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

# Works with any scanner implementation
client = ChainscanClient.from_config('etherscan', 'v1', 'eth', 'main')
balance = await client.call(Method.ACCOUNT_BALANCE, address=address)
txs = await client.call(Method.ACCOUNT_TRANSACTIONS, address=address)

# Same code works with different scanners!
oklink_client = ChainscanClient.from_config('oklink_eth', 'v1', 'oklink_eth', 'main')
balance = await oklink_client.call(Method.ACCOUNT_BALANCE, address=address)
```

### 🎯 **Key Benefits of Unified Architecture**

1. **Type Safety**: `Method.ACCOUNT_BALANCE` vs `"balance"`
2. **Cross-Scanner**: Same code works with different APIs
3. **Auto-Mapping**: Parameter names automatically converted
4. **Unified Parsing**: Response formats automatically normalized
5. **Easy Extension**: Add new scanners with ~30 lines of code

## Usage Examples

### 🆕 **Unified Client Examples**
```bash
# Quick comparison of legacy vs unified
python examples/simple_balance_comparison.py

# Advanced multi-scanner comparison  
python examples/balance_comparison.py

# Complete architecture demonstration
python examples/unified_client_demo.py
```

### Traditional Examples
```bash
# Quick connectivity test for all scanners
python examples/quick_scanner_check.py

# Test all available methods for all scanners
python examples/test_scanner_methods.py

# Test decode functionality with real Ethereum data
python examples/test_decode_functionality.py
```

## Outputs

### Scanner Methods Test Outputs
- `scanner_methods_test.log` - Detailed execution logs
- `scanner_methods_summary.md` - High-level overview of all scanners and success rates
- `scanner_methods_detailed.md` - Method-by-method results for each scanner
- `scanner_methods_results.json` - Raw test data for further analysis

### Decode Test Outputs  
- `test_decode.log` - Detailed execution logs
- `decode_test_report.txt` - Human-readable test report with real data results
- `decode_test_results.json` - Raw test results for debugging

**Note**: All outputs are automatically added to `.gitignore` to prevent accidentally committing test data.

## What the Test Does

1. **Connects to Ethereum mainnet** using your Etherscan API key
2. **Fetches real contract ABI** for the UNI token from verified source code
3. **Retrieves recent logs** from the last 1000 blocks for UNI token
4. **Fetches real transactions** with input data to/from UNI token contract
5. **Decodes everything** using both the real ABI and online signature lookup
6. **Generates comprehensive report** showing success rates and detailed results

This provides a complete end-to-end test of the library's capabilities with production data!

## Testing with Your API Keys

If you have API keys for multiple scanners, see `test_with_your_keys.md` for detailed instructions on:
- Setting up all API keys properly
- Running comprehensive tests across all scanners  
- Analyzing results and troubleshooting issues
- Understanding scanner-specific limitations

The comprehensive test will show you exactly which methods work on which scanners with your specific API key configuration. 