# Examples

## Run the first three with nothing but the package

`01`–`03` are self-contained: no repository checkout, no development
environment, no API key.

```bash
pip install aiochainscan
curl -O https://raw.githubusercontent.com/VaitaR/aiochainscan/main/examples/01_quickstart.py
python 01_quickstart.py                 # or: python 01_quickstart.py 0xYourAddress
```

| File | What it shows | Extra setup |
|---|---|---|
| [01_quickstart.py](01_quickstart.py) | Balance, recent transactions, token holdings — with exact `Decimal` conversion | none |
| [02_export_to_csv.py](02_export_to_csv.py) | CSV export; `--all` streams the complete history with flat memory | none |
| [03_multi_wallet_analysis.py](03_multi_wallet_analysis.py) | Several addresses concurrently through one client | none |

Each takes addresses on the command line, so they work as small tools, not just
as reading material.

## The rest, from a checkout

```bash
git clone https://github.com/VaitaR/aiochainscan.git
cd aiochainscan
uv sync --extra dev
uv run python examples/05_typed_responses.py
```

| File | What it shows | Extra setup |
|---|---|---|
| [04_etherscan_with_api_key.py](04_etherscan_with_api_key.py) | The full Etherscan v2 surface | `ETHERSCAN_KEY` |
| [05_typed_responses.py](05_typed_responses.py) | Exact typing through the `convert` helpers | none |
| [06_multichain_comparison.py](06_multichain_comparison.py) | The same address across chains | none |
| [07_handling_whale_blocks.py](07_handling_whale_blocks.py) | Provider pagination limits and the completeness guarantee | none |

### Streaming and exports

| File | What it shows |
|---|---|
| [stream_to_csv_example.py](stream_to_csv_example.py) | Streamed batches written to CSV |
| [streaming_vs_bulk_demo.py](streaming_vs_bulk_demo.py) | Materialized versus streamed retrieval |
| [streaming_decode_demo.py](streaming_decode_demo.py) | Batch ABI decoding while streaming |
| [wallet_report.py](wallet_report.py) | A small wallet report |

### Contracts and ENS

| File | What it shows |
|---|---|
| [smart_contract_demo.py](smart_contract_demo.py) | ABI loading and decoded contract activity |
| [ens_simple_demo.py](ens_simple_demo.py) | Reverse ENS lookup |
| [ens_demo.py](ens_demo.py) | ENS resolution and caching |
| [ens_and_gas_dashboard.py](ens_and_gas_dashboard.py) | ENS plus gas data |

### Progress reporting

[progress_callback_demo.py](progress_callback_demo.py) — progress callbacks on
paginated operations.

## Conventions these examples follow

- The public surface only: `from aiochainscan import ChainscanClient` and its
  convenience methods. `client.call(Method.…)` appears where an example is
  specifically about the low-level path.
- Base-unit values convert through `wei_to_ether` / `to_decimal_amount`
  (exact `Decimal`), never `int(wei) / 1e18`.
- One `async with` client per script; a method the configured scanner does not
  declare raises `MethodNotDeclaredError` rather than returning empty data.

Public Blockscout instances are keyless but shared: they rate-limit, and a
burst can come back as `403`. Examples that need reliability use
`ETHERSCAN_KEY`.
