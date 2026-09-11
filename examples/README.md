# Examples

## Recipe: an address's transaction history as CSV

The shortest useful thing this library does, start to finish. No checkout, no
API key, no pagination code of your own.

```bash
pip install 'aiochainscan==1.0.5'
curl -O https://raw.githubusercontent.com/VaitaR/aiochainscan/main/examples/02_export_to_csv.py

python 02_export_to_csv.py 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045          # one page
python 02_export_to_csv.py 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --all    # full history
```

```text
Exporting 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 -> 0xd8dA6BF2_transactions.csv
  blockscout_v2/ethereum, one provider page
Done: 50 rows in 0xd8dA6BF2_transactions.csv
This is ONE page. Re-run with --all for the complete history.
```

```csv
hash,block_number,timestamp,from_address,to_address,value_wei,gas_used,gas_price_wei,is_error
0x18fbf479…,25882055,2026-09-01T11:12:59+00:00,0xFD8d9047…,0xd8dA6BF2…,0,30880,143361614,0
```

**Chain and provider.** Ethereum mainnet through Blockscout v2, keyless. Change
the pair in the one `ChainscanClient.from_config('blockscout_v2', 'ethereum')`
call; nothing else in the script is provider-specific, because the rows come
from the normalized transaction model rather than from raw provider JSON.

**What `--all` covers.** External transactions only — the `ACCOUNT_TRANSACTIONS`
endpoint. Internal transactions and ERC-20/721/1155 transfers are separate
endpoints (`get_all_internal_transactions`, `get_all_token_transfers`), so this
CSV is not a wallet's full economic history: an address that only ever received
tokens exports almost nothing here.

**What is handled for you.** Paging runs to exhaustion, and a provider's
`page * offset` window is worked around, not merely reported: where the endpoint
has a block range, the range is split at the last served record and the halves
re-fetched. Completeness is a guarantee, not an effort — there is no silently
truncated result. Where completeness cannot be reached the call raises instead
of returning part of the data: `PaginationDataLossError` when a single block
exceeds the provider's cap, `CompletenessUnavailableError` when the endpoint has
no range to split on this provider (the message names providers that serve it
whole). Pass `guarantee_complete=False` to accept truncation deliberately.

**Memory.** `--all` streams batches straight to the file, so a large account
costs no more memory than a small one.

**Rate limits.** Public Blockscout instances are shared infrastructure: they
apply their own rate limiting and may answer a burst of requests with `403` or a
bot-protection page. For unattended or high-volume work configure Etherscan (or
a self-hosted Blockscout instance) instead, or put both behind
[`ChainscanPool`](https://github.com/VaitaR/aiochainscan#multi-provider-failover-pool). The script catches those
refusals and exits with a message instead of a traceback;
[08_provider_failover.py](08_provider_failover.py) shows the pool routing
around them.

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
| [08_provider_failover.py](08_provider_failover.py) | `ChainscanPool`: two explorers, automatic failover, visible routing | none (`ETHERSCAN_KEY` for two members) |

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

Public Blockscout instances are keyless but shared — see the rate-limit note
in the recipe above. Examples that need reliability use `ETHERSCAN_KEY`.
