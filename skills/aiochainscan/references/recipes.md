# Recipes

Code-first patterns. Every snippet assumes `python >= 3.12` and an async
context. The prose walkthrough lives in the repository's
[getting-started guide](https://github.com/VaitaR/aiochainscan/blob/main/docs/GETTING_STARTED.md).

## Export a wallet's full history

```python
from aiochainscan import ChainscanClient

async with ChainscanClient.from_config('blockscout', 'ethereum') as client:
    txs = await client.get_all_transactions(address)              # every tx
    erc20 = await client.get_all_token_transfers(address)         # every ERC-20 transfer
    internal = await client.get_all_internal_transactions(address)
```

Large wallets — constant memory instead of one big list:

```python
async for batch in client.iter_transactions_streaming(address, batch_size=1000):
    await sink.write(batch)          # ~10 MB RAM regardless of history size
```

Bounded range and progress reporting:

```python
from aiochainscan.utils.progress_helpers import console_progress

txs = await client.get_all_transactions(
    address, from_block=18_000_000, to_block=18_500_000, on_progress=console_progress()
)
```

Polars DataFrame of the **full** history (needs the `data` extra):

```python
df = await client.get_transactions_df(address)   # Wei columns are Utf8, never Int64
```

## Exact amounts

```python
from aiochainscan import format_ether, hex_to_int, to_decimal_amount, to_iso, wei_to_ether

wei_to_ether('1500000000000000000')        # Decimal('1.5')
to_decimal_amount('1500000', decimals=6)   # Decimal('1.5')  — USDC and friends
format_ether('1500000000000000000')        # '1.500000'      — half-up rendering
hex_to_int('0x1a')                         # 26 — accepts hex str, decimal str or int
to_iso('1609459200')                       # '2021-01-01T00:00:00+00:00'
```

Rules: never `int(wei) / 10**18`; never `float()` on a balance; token amounts
need the token's own `decimals` (from `get_token_info`), not 18. Inputs must
be integer strings — `'1e18'`, `'1_000'` and fractional base units are
rejected as corrupted data.

## Switch or combine providers

Same call, different provider:

```python
async with ChainscanClient.from_config('etherscan', 'ethereum') as client:   # needs ETHERSCAN_KEY
    ...
async with ChainscanClient.from_config('blockscout_v2', 'base') as client:   # keyless
    ...
async with ChainscanClient.from_config('nodereal', 'bsc') as client:         # needs NODEREAL_KEY
    ...
```

Automatic failover in priority order — the pool has the full client surface:

```python
from aiochainscan import ChainscanPool

async with ChainscanPool.from_config(
    [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]
) as pool:
    balance = await pool.get_balance(address)
    pool.last_provider        # 'etherscan/ethereum'  (sticky until it fails)
    pool.provider_states()    # {label: available | cooldown | ...}
```

Fallback happens on rate limits, network/5xx, missing keys, plan
restrictions and undeclared methods. Bad arguments, not-found and data-contract
errors propagate unchanged. If everything fails:
`ProviderPoolExhaustedError.attempts` lists `(provider, exception)` pairs.

## Provider-independent field names

Raw item shapes really do differ, so code written against one provider breaks
on another:

```python
# etherscan: flat strings
tx['from'], tx['to'], tx['value'], tx['timeStamp']       # Wei str, unix-seconds str

# blockscout_v2: nested dicts, ISO timestamp
tx['from']['hash'], tx['to']['hash'], tx['value'], tx['timestamp']
```

The normalized surface removes that difference:

```python
from aiochainscan.domain.normalized import Transaction

txs: list[Transaction] = await client.get_all_transactions_normalized(address)
tx = txs[0]
tx.hash, tx.block_number, tx.value_wei, tx.timestamp   # str, int, int, datetime
tx.provider_data                                        # untouched provider dict
```

Also `get_*_normalized` / `iter_*_normalized` for internal transactions,
token transfers and logs, plus `get_block_normalized`. A field the provider
does not expose is `None` — never guessed.

## Event logs

```python
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

logs = await client.get_all_logs(
    token_address, from_block=18_000_000, to_block=18_100_000, topic0=TRANSFER
)
async for batch in client.iter_logs_streaming(token_address, from_block=18_000_000):
    ...
```

`get_logs()` alone returns one capped page (~1000). A bounded block range on
a provider whose spec has no block-range parameters raises
`BlockRangeNotSupportedError` rather than silently ignoring the bounds.

## Token holders

```python
holders = await client.get_all_token_holders(token_address)
# [{'address': '0x…', 'value': '1234500000'}, …]   raw units, EIP-55 addresses

top = await client.get_top_token_holders(token_address, limit=100)  # etherscan PRO / nodereal
count = await client.get_token_holder_count(token_address)
```

On Etherscan the list is capped at 10 000 and there is no block range to
split, so a bigger token raises `CompletenessUnavailableError`; its
`.alternatives` names providers that serve the list to exhaustion
(`blockscout`, `blockscout_v2`, `nodereal`). Handle it by switching provider:

```python
from aiochainscan import CompletenessUnavailableError

try:
    holders = await client.get_all_token_holders(token_address)
except CompletenessUnavailableError as exc:
    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as fallback:
        holders = await fallback.get_all_token_holders(token_address)
```

## Contracts and decoded calls

```python
abi = await client.get_contract_abi(address)          # JSON string
source = await client.get_contract_source(address)

contract = await client.get_contract(address)         # ABI fetched + cached
async for event in contract.iter_events('Transfer', from_block=18_000_000, limit=100):
    print(event.block_number, event.args['from'], event.args['to'], event.args['value'])

result = await client.eth_call(to_address, '0x70a08231…')   # raw eth_call
```

ABI decoding works on a bare install (pure-Python codec covers the full ABI
spec). `pip install "aiochainscan[fastabi]"` swaps in the Rust backend for
bulk decoding; decoded values are identical by contract. An unsupported
Solidity type raises `AbiTypeNotSupportedError` — it never returns an empty
decode.

## Waiting for chain state

```python
receipt = await client.wait_for_transaction(tx_hash)     # 120 s deadline, 10 s poll
reached = await client.wait_for_block(20_000_000)        # 600 s deadline
verdict = await client.wait_for_verification(guid)       # 300 s deadline
```

They raise `ChainscanWaitTimeoutError(what, waited, last_state)` on expiry and
*return* final-but-negative states (a revert, a `Fail` verdict) instead of
raising.

## Errors

```python
from aiochainscan import (
    ChainscanRateLimitError,       # survived the built-in retry
    ChainscanNetworkError,         # connection / 5xx after retries
    ChainscanDataError,            # provider broke its data contract
    ChainscanWaitTimeoutError,     # wait_for_* deadline
    CompletenessUnavailableError,  # cannot be served completely here (.alternatives)
    PaginationDataLossError,       # one block alone exceeds the provider cap
    MethodNotDeclaredError,        # scanner does not declare this method
    BlockRangeNotSupportedError,   # bounded range the provider cannot express
    ProviderPoolExhaustedError,    # pool: every provider failed (.attempts)
)
```

Retry and rate limiting are built in (tenacity + token bucket, burst 1). Do
not add your own retry wrapper — the library already separates retryable
faults from deterministic refusals, and a second layer doubles the request
budget.

## ENS

```python
name = await client.lookup_address(address)        # None when unregistered — guard it
addr = await client.resolve_name('vitalik.eth')
names = await client.lookup_addresses([a1, a2])    # dict[str, str], batched
addrs = await client.resolve_names(['a.eth', 'b.eth'])
```

Ethereum mainnet only. Reverse lookup works on BlockScout V2; forward
resolution needs a scanner exposing `eth_call`.

## Self-hosted instances

```python
async with ChainscanClient.from_config(
    'blockscout_v2', 'https://blockscout.internal', expected_chain_id=100
) as client:
    info = await client.get_chain_info()      # probed once, cached 1 h
```

Any `network` string containing `://` is treated as a base URL. HTTPS only
unless `allow_http=True`; `expected_chain_id` is verified before the first
request.

## MCP server

```bash
pip install "aiochainscan[mcp]"
python -m aiochainscan.mcp_server
```

Twelve read-only stdio tools (balances, transactions, tokens, holders, ABIs,
`read_contract`, ENS, chain list). Every tool answers
`{data, notes, instructions, pagination}`; paginated tools ship a
ready-to-run `pagination.next_call`, so cursors never have to be parsed.
Default scanner is keyless `blockscout` (`AIOCHAINSCAN_MCP_SCANNER` to
override).
