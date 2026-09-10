# Getting started

The user-facing path: install, first request, which provider to pick, the
recipes that cover most work, and the limits worth knowing before you build on
them. Everything here uses the published package — no repository checkout and
no development environment.

## 1. Install

```bash
pip install aiochainscan          # httpx, orjson, tenacity, aiolimiter
pip install "aiochainscan[data]"  # + Polars DataFrame exports
pip install "aiochainscan[mcp]"   # + MCP server for AI agents
```

Python 3.12 or newer. ABI decoding, address checksums and the MCP server work
on the base install; `aiochainscan[fastabi]` adds the Rust accelerator for bulk
decoding.

## 2. First request

```python
import asyncio

from aiochainscan import ChainscanClient, wei_to_ether


async def main() -> None:
    address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'  # vitalik.eth

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        balance = await client.get_balance(address)
        page = await client.get_transactions(address)

    print(f'{wei_to_ether(balance)} ETH')
    print(f'{len(page)} transactions in the first page')


asyncio.run(main())
```

Every scalar an explorer returns is a string in base units. Convert with
`wei_to_ether` / `to_decimal_amount` (exact `Decimal`); never with
`int(value) / 1e18`, which loses precision above ~9 ETH.

## 3. Choose a provider

| Provider | `from_config` name | Key | Use it when |
|---|---|---|---|
| Blockscout v2 | `blockscout_v2` | none | Exploration, notebooks, small jobs on a public instance |
| Blockscout v1 | `blockscout` | none | Same instances, Etherscan-shaped endpoint set, holder lists |
| Etherscan v2 | `etherscan` | `ETHERSCAN_KEY` | Production work, the full method surface, every supported chain |
| NodeReal | `nodereal` | `NODEREAL_KEY` | BSC analytics on a free tier |

The keyless Blockscout legs serve the eight chains with a public Blockscout
instance (ethereum, sepolia, gnosis, polygon, optimism, arbitrum, base,
scroll); BSC and Linea have none, so BSC analytics go through `nodereal` or
`etherscan`. `aiochainscan chains` prints the current mapping.

```python
async with ChainscanClient.from_config('etherscan', 'ethereum') as client: ...
async with ChainscanClient.from_config('etherscan', 8453) as client: ...      # chain id
async with ChainscanClient.from_config(                                      # self-hosted
    'blockscout_v2', 'https://my-blockscout.internal', expected_chain_id=100
) as client: ...
```

Keyless access is real but conditional: public Blockscout instances are shared
infrastructure with their own rate limiting, and a burst can be answered with
`403` or a bot-protection page instead of data. For unattended jobs, use a key
provider, a self-hosted instance, or list both in a pool:

```python
from aiochainscan import ChainscanPool

async with ChainscanPool.from_config(
    [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]
) as pool:
    balance = await pool.get_balance(address)   # falls over to Blockscout on failure
```

Coverage differs per provider. A convenience method the configured scanner does
not declare raises `MethodNotDeclaredError` at call time — it is never answered
with empty data. `aiochainscan scanners` prints the coverage of the installed
version.

## 4. Recipes

**Complete history, materialized.**

```python
transactions = await client.get_all_transactions(address)
transfers = await client.get_all_token_transfers(address)
logs = await client.get_all_logs(contract, from_block=20_000_000)
```

**Large histories without holding them in memory.**

```python
async for batch in client.iter_transactions_streaming(address, batch_size=1_000):
    await store(batch)
```

**Token amounts with the right decimals.**

```python
from aiochainscan import to_decimal_amount

raw = await client.get_token_balance(address, usdc)
amount = to_decimal_amount(raw, decimals=6)     # Decimal('1.5')
```

**Event logs for one topic over a block range.**

```python
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

logs = await client.get_all_logs(
    token, from_block=18_000_000, to_block=18_100_000, topic0=TRANSFER
)
```

**The same field names from every provider.** Raw items stay provider-native
(Etherscan answers flat `tx['from']` and `timeStamp`; Blockscout v2 answers
nested `tx['from']['hash']` and ISO `timestamp`). Code that must run on more
than one provider uses the `*_normalized` variants, which return frozen
dataclasses from `aiochainscan.domain.normalized`:

```python
for tx in await client.get_all_transactions_normalized(address):
    print(tx.hash, tx.block_number, tx.value_wei, tx.timestamp)  # str, int, int, datetime
    tx.provider_data                                             # raw item, untouched
```

Transactions, internal transactions, token transfers and logs have all three
shapes (`get_*_normalized`, `get_all_*_normalized`, `iter_*_normalized`);
blocks have `get_block_normalized`. A field the provider does not expose is
`None`, never guessed.

**A complete token-holder list, with a provider switch when needed.**

```python
from aiochainscan import ChainscanClient, CompletenessUnavailableError

try:
    holders = await client.get_all_token_holders(token)      # [{'address', 'value'}, …]
except CompletenessUnavailableError as exc:
    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as complete:
        holders = await complete.get_all_token_holders(token)  # exc.alternatives named it
```

**Decoded contract events.**

```python
contract = await client.get_contract(address)
async for event in contract.iter_events('Transfer', limit=100):
    print(event.block_number, event.args)
```

**DataFrames** (needs the `data` extra; paginates internally).

```python
frame = await client.get_transactions_df(address)
```

**Progress reporting** for anything paginated.

```python
from aiochainscan.utils.progress_helpers import console_progress

transactions = await client.get_all_transactions(address, on_progress=console_progress())
```

## 5. Limits worth knowing

- **One page is not the history.** `get_transactions()`, `get_logs()` and
  `get_token_holders()` return a single provider page. Use `get_all_*()` or
  `iter_*_streaming()` for complete data.
- **Completeness is guaranteed or refused.** `get_all_*` / `iter_*_streaming`
  default to `guarantee_complete=True`: they either return every matching
  record or raise. `PaginationDataLossError` means one block alone exceeds the
  provider's result window; `CompletenessUnavailableError` means the endpoint
  has no range to split on this provider and names the providers that can serve
  it completely (Etherscan holder lists are the common case). Pass
  `guarantee_complete=False` to accept truncation deliberately.
- **Provider page caps are measured, not assumed.** Etherscan v2 serves at most
  1000 items per page and refuses `page * offset` above 10 000; Blockscout v1
  serves up to 10 000 per page with the same window, and its `getLogs` ignores
  paging entirely above 1000 logs. Blockscout v2 and NodeReal paginate by
  opaque cursors.
- **Values are strings in base units.** Never `float`, never `Int64` in a
  DataFrame column — an 18-decimal wei value overflows `Int64` at ~9.2 ETH.
- **Bounded block ranges need provider support.** Asking a provider whose spec
  carries no block-range parameters for a bounded range raises
  `BlockRangeNotSupportedError` instead of silently ignoring the bounds.
- **ENS is Ethereum mainnet only**, and forward resolution needs a scanner that
  declares `eth_call`.
- **Rate limiting and retries are on by default.** Transient failures are
  retried by the transport; a rate limit that survives the policy surfaces as
  `ChainscanRateLimitError`.

## Where to go next

- [Examples](../examples/README.md) — runnable scripts, three of them
  self-contained.
- [SmartContract API](SMART_CONTRACT_API.md), [ENS](ENS_INTEGRATION.md),
  [Streaming](STREAMING_PATTERN.md), [Progress callbacks](PROGRESS_CALLBACKS.md).
- [Migration guide](MIGRATION_GUIDE.md) — moving off the pre-1.0 entrypoints.
- The full method table and provider matrix live in the
  [README](../README.md) and, in exhaustive form, in
  [`AGENTS.md`](../AGENTS.md).
