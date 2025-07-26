# aiochainscan Examples

This directory contains example scripts demonstrating the usage of the aiochainscan library.

## Scripts

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

2. **Set up Etherscan API key:**

Create a `.env` file in the project root with your Etherscan API key:
```bash
# .env
ETHERSCAN_KEY=your_etherscan_api_key_here
```

Get a free API key at: https://etherscan.io/apis

## Usage

### Quick Scanner Check (Fast)
```bash
# Quick connectivity test for all scanners
python examples/quick_scanner_check.py

# Or with uv:
uv run python examples/quick_scanner_check.py
```

### Full Scanner Methods Test (Comprehensive)
```bash
# Test all available methods for all scanners
python examples/test_scanner_methods.py

# Or with uv:
uv run python examples/test_scanner_methods.py
```

### Test Decode Functionality
```bash
# Test decode functionality with real Ethereum data
python examples/test_decode_functionality.py

# Or with uv:
uv run python examples/test_decode_functionality.py
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