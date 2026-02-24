# aiochainscan Examples

Practical examples for Data Analysts and Data Engineers working with blockchain data.

## 🚀 Quick Start

### No API Key Required (BlockScout V2)

```bash
# Run the quickstart example
python examples/01_quickstart.py
```

### With Etherscan API Key

```bash
# Get your free key at https://etherscan.io/apis
export ETHERSCAN_KEY="your_key_here"
python examples/04_etherscan_with_api_key.py
```

---

## 📚 Examples Overview

| # | File | Description | Difficulty |
|---|------|-------------|------------|
| 01 | [01_quickstart.py](01_quickstart.py) | Get wallet balance and transactions | ⭐ Beginner |
| 02 | [02_export_to_csv.py](02_export_to_csv.py) | Export transactions to CSV | ⭐ Beginner |
| 03 | [03_multi_wallet_analysis.py](03_multi_wallet_analysis.py) | Analyze multiple wallets | ⭐⭐ Intermediate |
| 04 | [04_etherscan_with_api_key.py](04_etherscan_with_api_key.py) | Using Etherscan with API key | ⭐⭐ Intermediate |
| 05 | [05_pydantic_typed_responses.py](05_pydantic_typed_responses.py) | Type-safe data with Pydantic | ⭐⭐⭐ Advanced |
| 06 | [06_multichain_comparison.py](06_multichain_comparison.py) | Cross-chain portfolio analysis | ⭐⭐⭐ Advanced |
| 07 | [07_handling_whale_blocks.py](07_handling_whale_blocks.py) | Handle large transaction sets | ⭐⭐⭐ Advanced |
| 🆕 | [streaming_decode_demo.py](streaming_decode_demo.py) | **Memory-efficient streaming for millions of txs** | ⭐⭐⭐ Advanced |
| 🆕 | [smart_contract_demo.py](smart_contract_demo.py) | Smart contract interaction and decoding | ⭐⭐⭐ Advanced |
| 🆕 | [ens_simple_demo.py](ens_simple_demo.py) | **ENS reverse lookup (address → name)** | ⭐ Beginner |
| 🆕 | [ens_demo.py](ens_demo.py) | **Complete ENS integration guide** | ⭐⭐ Intermediate |
| ✨ | [progress_callback_demo.py](progress_callback_demo.py) | **Progress bars and tracking for long operations** | ⭐⭐ Intermediate |

---

## 🎯 Use Cases for Data Teams

### Data Analysts
- **01_quickstart.py** - Quick wallet inspection
- **02_export_to_csv.py** - Export for Excel/pandas analysis
- **03_multi_wallet_analysis.py** - Whale tracking, portfolio comparison

### Data Engineers
- **04_etherscan_with_api_key.py** - Production pipelines with rate limits
- **05_pydantic_typed_responses.py** - Type-safe ETL with validation
- **06_multichain_comparison.py** - Multi-chain data aggregation

---

## 📋 Supported APIs

### BlockScout V2 (Recommended - No API Key!)

```python
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method

client = ChainscanClient.from_config("blockscout_v2", "ethereum")
balance = await client.call(Method.ACCOUNT_BALANCE, address="0x...")
await client.close()
```

**Supported Networks:**
- `ethereum` - Ethereum Mainnet
- `polygon` - Polygon PoS
- `arbitrum` - Arbitrum One
- `optimism` - Optimism
- `base` - Base (Coinbase L2)
- `gnosis` - Gnosis Chain
- `zksync` - zkSync Era
- `scroll` - Scroll
- `linea` - Linea
- `celo` - Celo
- `rootstock` - Rootstock (RSK)

### Etherscan (API Key Required)

```python
client = ChainscanClient.from_config("etherscan", "ethereum", api_key="YOUR_KEY")
```

**Get your key:** https://etherscan.io/apis (Free tier: 5 req/sec)

---

## 🔧 Available Methods

```python
from aiochainscan.core.method import Method

# Account
Method.ACCOUNT_BALANCE            # Native coin balance
Method.ACCOUNT_BALANCE_MULTI      # Multiple addresses
Method.ACCOUNT_TRANSACTIONS       # Normal transactions
Method.ACCOUNT_INTERNAL_TRANSACTIONS  # Internal/trace txs
Method.ACCOUNT_TOKEN_PORTFOLIO    # All ERC20 tokens
Method.ACCOUNT_NFT_PORTFOLIO      # All NFTs

# Tokens
Method.TOKEN_BALANCE              # Specific token balance
Method.TOKEN_TRANSFERS            # Token transfer history

# Contract
Method.CONTRACT_ABI               # Contract ABI
Method.CONTRACT_SOURCE            # Verified source code
Method.CONTRACT_VERIFY            # Submit verification
Method.CONTRACT_VERIFY_STATUS     # Check verification

# Block
Method.BLOCK_BY_NUMBER            # Block details
Method.BLOCK_COUNTDOWN            # Blocks until target

# Other
Method.EVENT_LOGS                 # Event logs with filters
Method.GAS_ORACLE                 # Current gas prices
Method.ETH_SUPPLY                 # Total ETH supply
Method.ETH_PRICE                  # ETH/USD price
```

---

## 💡 Tips for Production

### 1. Always Close Clients

```python
client = ChainscanClient.from_config("blockscout_v2", "ethereum")
try:
    data = await client.call(Method.ACCOUNT_BALANCE, address=addr)
finally:
    await client.close()
```

### 2. Handle Rate Limits

```python
from aiochainscan.exceptions import ChainscanRateLimitError

try:
    data = await client.call(Method.ACCOUNT_TRANSACTIONS, address=addr)
except ChainscanRateLimitError:
    await asyncio.sleep(1)
    # Retry...
```

### 3. Type-Safe Responses with Pydantic

```python
from aiochainscan.domain.dto_v2 import TransactionDTO

# Parse raw response into typed model
tx = TransactionDTO.model_validate(raw_tx_dict)
print(tx.value)  # IDE knows this is int!
```

---

## 📦 Legacy Examples

The following older examples are kept for reference but may use deprecated patterns:

- `blockscout_demo.py` - BlockScout V1 examples
- `unified_client_demo.py` - Legacy client patterns
- `dump_data.py` - Bulk data extraction

---

## 🆘 Getting Help

- **Documentation:** See [AGENTS.md](../AGENTS.md) for architecture overview
- **Issues:** https://github.com/VaitaR/aiochainscan/issues
