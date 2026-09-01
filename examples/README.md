# Examples

The examples demonstrate `ChainscanClient` usage for account data, exports,
multiple chains, streaming, contracts, ENS, and progress reporting.

Run them from the repository root after installing development dependencies:

```bash
uv sync --extra dev
uv run python examples/01_quickstart.py
```

Examples that use Etherscan require `ETHERSCAN_KEY`. Public Blockscout examples
do not require a key.

## Starting points

| File | Purpose | Additional setup |
|---|---|---|
| [01_quickstart.py](01_quickstart.py) | Fetch a balance and recent transactions | None |
| [02_export_to_csv.py](02_export_to_csv.py) | Export transaction data | None |
| [03_multi_wallet_analysis.py](03_multi_wallet_analysis.py) | Query several wallets | None |
| [04_etherscan_with_api_key.py](04_etherscan_with_api_key.py) | Use Etherscan v2 | `ETHERSCAN_KEY` |
| [05_typed_responses.py](05_typed_responses.py) | Exact typing via `convert` helpers (dict responses, no Pydantic) | None |
| [06_multichain_comparison.py](06_multichain_comparison.py) | Query more than one chain | Provider access |
| [07_handling_whale_blocks.py](07_handling_whale_blocks.py) | Handle provider pagination limits | Provider access |

## Streaming and exports

| File | Purpose |
|---|---|
| [stream_to_csv_example.py](stream_to_csv_example.py) | Write streamed batches to CSV |
| [streaming_vs_bulk_demo.py](streaming_vs_bulk_demo.py) | Compare materialized and streamed retrieval |
| [streaming_decode_demo.py](streaming_decode_demo.py) | Decode transactions in batches |
| [wallet_report.py](wallet_report.py) | Build a wallet report |

## Contracts and ENS

| File | Purpose |
|---|---|
| [smart_contract_demo.py](smart_contract_demo.py) | Fetch ABIs and decode contract activity |
| [ens_simple_demo.py](ens_simple_demo.py) | Perform a reverse ENS lookup |
| [ens_demo.py](ens_demo.py) | Exercise ENS resolution and caching |
| [ens_and_gas_dashboard.py](ens_and_gas_dashboard.py) | Combine ENS and gas data |

## Progress callbacks

[progress_callback_demo.py](progress_callback_demo.py) shows how to receive
progress updates from paginated operations.

Use an async context manager in new code:

```python
from aiochainscan import ChainscanClient


async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
    balance = await client.get_balance(address)
```

The source code and scanner declarations determine which methods a provider
supports. A method that is not available for the configured scanner raises
`ValueError`.
