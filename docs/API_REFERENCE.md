# API reference

The landing [README](../README.md) shows what the library is for. This file is
the lookup surface: every provider, every common call, and the exact
conversion and error contracts.

## Providers

`ChainscanClient.from_config(scanner, network)` accepts chain names such as
`ethereum`, `base`, `polygon`, `arbitrum`, and `optimism`, or a numeric chain
ID. The built-in scanner names are:

| Scanner | Default version | Authentication | Chains | Methods |
|---|---:|---|---:|---:|
| `etherscan` | v2 | API key | 10 | 33/33 |
| `blockscout` | v1 | None for public instances | 8 | 31/33 |
| `blockscout_v2` | v2 | None for public instances | 8 | 11/33 |
| `nodereal` | v1 | API key (`NODEREAL_KEY`), free tier | BSC only | 25/33 |

Thirteen chains are served in total; a self-hosted Blockscout or an Etherscan
proxy adds any other (see below). Eight of the thirteen need no API key at all,
served by both Blockscout legs: Ethereum, Optimism, Gnosis, Polygon, Base,
Arbitrum, Scroll and Sepolia.

On Etherscan, what a free key may read depends on the endpoint rather than the
chain: ABI and source are free everywhere, while balances and history are free
on Ethereum, Arbitrum, Polygon, Sepolia and Sonic and need a paid plan on the
rest (measured 2026-09-11). BSC has no Blockscout instance, so NodeReal's free
tier is the free route to BSC balances and history.

`aiochainscan scanners` prints this table for your own environment, including
which keys are configured.

Scanner support is checked at call time. A convenience method that is not
declared by the selected scanner raises `MethodNotDeclaredError` (a `ValueError`
subclass).

## Common operations

```python
async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    # Accounts
    balance = await client.get_balance(address)
    page = await client.get_transactions(address)
    all_transactions = await client.get_all_transactions(address)
    token_transfers = await client.get_token_transfers(address)

    # Blocks and transactions
    block = await client.get_block(20_000_000)
    transaction = await client.get_transaction(tx_hash)
    receipt_status = await client.get_transaction_status(tx_hash)

    # Polling helpers (wait until final; timeout/poll_interval are tunable)
    final_status = await client.wait_for_transaction(tx_hash, timeout=120, poll_interval=10)
    verdict = await client.wait_for_verification(guid)
    reached = await client.wait_for_block(20_000_000)

    # Contracts and logs
    abi = await client.get_contract_abi(contract_address)
    source = await client.get_contract_source(contract_address)
    logs = await client.get_logs(contract_address, from_block=20_000_000)

    # Tokens and network data
    token_balance = await client.get_token_balance(address, token_address)
    holders = await client.get_token_holders(token_address)        # one page
    all_holders = await client.get_all_token_holders(token_address)
    top_holders = await client.get_top_token_holders(token_address, limit=100)
    holder_count = await client.get_token_holder_count(token_address)
    gas = await client.get_gas_oracle()
    price = await client.get_eth_price()
```

The `Method` enum contains the low-level operation set. Use `client.call()` when
you need an operation without a dedicated convenience method:

```python
from aiochainscan import Method

result = await client.call(Method.ACCOUNT_BALANCE, address=address)
```

## One shape across providers

Provider payloads differ field by field (`blockNumber` vs `block_number`,
nested `from` objects vs flat strings). The normalized surface returns the same
frozen dataclasses whichever provider answered:

```python
async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
    txs = await client.get_transactions_normalized(address)
    txs[0].hash, txs[0].block_number, txs[0].value_wei   # str, int, int (wei)
```

`get_*_normalized` (one page), `get_all_*_normalized` (everything) and
`iter_*_normalized` (batches) exist for transactions, token transfers,
internal transactions and logs; a single block converts with
`get_block_normalized`. The dataclasses live in
[`aiochainscan.domain.normalized`](../aiochainscan/domain/normalized.py) and
keep `raw` for the provider-specific fields. Everything else stays
provider-native, so switching providers on a raw method means expecting that
provider's field names.

## Self-hosted instances and proxies

Instead of a chain name, `from_config` accepts a base URL — any string with a
`scheme://` prefix is treated as an instance root, anything else resolves
through the chain registry as before:

```python
# Self-hosted BlockScout — keyless, any chain (even private ones)
async with ChainscanClient.from_config(
    'blockscout_v2', 'https://my-blockscout.internal', expected_chain_id=100
) as client:
    info = await client.get_chain_info()

# Etherscan v2 behind a proxy — API key still required, chain id mandatory
client = ChainscanClient.from_config(
    'etherscan', 'https://eth-proxy.internal', api_key='...', expected_chain_id=137
)
```

`expected_chain_id` is checked once before the first request and a mismatch
fails fast with `ChainscanDataError`. Chain identity is resolved through the
provider itself — BlockScout via its JSON-RPC `eth_chainId` endpoint, Etherscan
via the keyless `v2/chainlist` registry — and cached for an hour in a
process-shared cache, so the ~60-network chainlist is downloaded at most once.
NodeReal does not support custom base URLs (its API key rides in the URL path).

## Value conversions

Explorer APIs return every scalar as a string — wei amounts, hex numbers, unix
timestamps. Module-level helpers convert them exactly (no float step, no new
dependencies):

```python
from aiochainscan import format_ether, hex_to_int, to_iso, to_decimal_amount, wei_to_ether

wei_to_ether('1500000000000000000')        # Decimal('1.5') — exact, never float
format_ether('1500000000000000000')        # '1.500000'
to_decimal_amount('1500000', decimals=6)   # Decimal('1.5') — USDC-style tokens

hex_to_int('0x1a')                         # 26 — hex string, decimal string or int
to_iso('1609459200')                       # '2021-01-01T00:00:00+00:00' (UTC)
```

Wei math is `Decimal`-exact for any magnitude (including 10^30+ wei and
negative allowance-style amounts); `hex_to_int` absorbs the proxy-vs-REST
habit of returning the same field as `'0x1a'` or `'26'`. Invalid input (empty
strings, fractional wei, bare hex like `'1a'`) raises `ValueError` instead of
guessing.

Balances, token values and supplies are always base-unit strings. Convert them
with the asset's own decimals; do not assume 18 for every token.

## Command line

The package installs an `aiochainscan` command for inspecting what the current
environment can reach — which scanners are available, which need a key, and
whether a chosen provider actually answers:

```bash
aiochainscan scanners                  # providers, versions, auth, method coverage
aiochainscan check                     # credential status + which .env files were read
aiochainscan chains --filter base      # chains the registry resolves
aiochainscan generate-env > .env       # template with the keys that are actually used
aiochainscan test blockscout_v2 ethereum   # one real request through the configured client
```

`scanners` and `chains` need no network access and no credentials; `test`
performs a single balance request with the resolved configuration and exits
non-zero when the provider cannot serve it.

## Error handling

```python
from aiochainscan import (
    ChainscanClientApiError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
    ChainscanWaitTimeoutError,
    PaginationDataLossError,
)

try:
    transactions = await client.get_all_transactions(address)
except ChainscanRateLimitError:
    raise  # The configured retry policy was exhausted.
except ChainscanNetworkError:
    raise  # Transport failure after retries.
except PaginationDataLossError:
    raise  # The provider could not return a complete range safely.
except ChainscanClientApiError:
    raise  # The explorer rejected the request or returned an API error.

try:
    final_status = await client.wait_for_transaction(tx_hash, timeout=120)
except ChainscanWaitTimeoutError as exc:
    print(exc.what, exc.waited, exc.last_state)  # still pending after the budget
```

Most library exceptions derive from `ChainscanClientError`, so one `except`
clause bounds a call site. The two exceptions that do not are deliberate:
`MethodNotDeclaredError` and `AbiTypeNotSupportedError` subclass `ValueError`,
because both mean the *caller* asked for something this configuration cannot
serve. The full set:

| Exception | Means |
|---|---|
| `ChainscanRateLimitError` | Provider throttled the request; carries `retry_after` when advertised |
| `ChainscanNetworkError` | Transport failure that survived the retry policy |
| `ChainscanClientApiError` | The explorer answered with an API-level error |
| `ChainscanDataError` | The response violated the expected data contract |
| `MethodNotDeclaredError` | The scanner does not declare this method (`ValueError` subclass) |
| `BlockRangeNotSupportedError` | A bounded block range the provider's spec cannot carry |
| `InputLimitExceededError` | More input than the endpoint documents (refused locally, never sent) |
| `PaginationDataLossError` | A single block exceeds the provider's result window |
| `CompletenessUnavailableError` | The endpoint has no range to split; `.alternatives` names providers that can serve it |
| `AbiTypeNotSupportedError` | No decode tier handles this Solidity type (`ValueError` subclass) |
| `ChainscanWaitTimeoutError` | A `wait_for_*` helper exhausted its budget |
| `ProviderPoolExhaustedError` | Every pool member failed; `.attempts` carries the per-provider causes |

Pool users also see `ChainscanProviderSwitchWarning` — a provider was routed
around; filter it if the diagnostics are noisy.
