# aiochainscan Examples

This directory contains example scripts demonstrating the usage of the aiochainscan library.

## Scripts

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

```bash
uv run python examples/test_decode_functionality.py
```

## Outputs

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