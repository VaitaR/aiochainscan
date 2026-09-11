# aiochainscan

[![PyPI](https://img.shields.io/pypi/v/aiochainscan.svg)](https://pypi.org/project/aiochainscan/)
[![Python](https://img.shields.io/pypi/pyversions/aiochainscan.svg)](https://pypi.org/project/aiochainscan/)
[![License](https://img.shields.io/pypi/l/aiochainscan.svg)](https://github.com/VaitaR/aiochainscan/blob/main/LICENSE)

`aiochainscan` reads on-chain history from public block explorers across 85
chains through one async client — and hands it back usable, not raw. Ask for an
address's transactions and you get the complete history, not the first page of
provider JSON that you then have to stitch, decode and wrap in retries
yourself.

```python
async with ChainscanClient.from_config('blockscout', 'ethereum') as client:
    transactions = await client.get_all_transactions(address)   # every page, or an exception
```

Three things it does for you instead of leaving them as homework:

- **Pagination.** `get_all_*` walks to the end. By default the result is
  [guaranteed complete](https://github.com/VaitaR/aiochainscan/blob/main/docs/PAGINATION_AND_FAILOVER.md):
  every matching record, or an exception — never a silently truncated page.
- **Decoding.** ABI decoding of calldata and event logs is built in and needs
  no extra dependency — no `eth-abi`, no `web3`.
- **Failures.** Rate limiting, retries, one shape across providers, and
  optional [failover](https://github.com/VaitaR/aiochainscan/blob/main/docs/PAGINATION_AND_FAILOVER.md#multi-provider-failover)
  between them.

It runs on free access: 8 chains need no API key at all, BSC works on
NodeReal's free tier, and the base install pulls four dependencies.

> Status: stable public API (1.x). The public surface is `ChainscanClient`;
> provider coverage differs by scanner and endpoint. Released changes are
> listed in the [changelog](https://github.com/VaitaR/aiochainscan/blob/main/CHANGELOG.md).

## Is this the right tool?

- **Reading history** — every transaction, transfer, internal call or log an
  address ever touched, decoded, without running an indexer or paying for one:
  this library.
- **Reading live state or sending transactions** — contract calls in a hot
  path, signing, nonces, mempool: use an RPC client such as `web3.py`.
  `eth_call` exists here, but as a convenience on top of an explorer, not as a
  node client.
- **Arbitrary queries over a whole chain** — "every address that did X in
  2024": that is an indexer or a warehouse, not an explorer API.

## Installation

Python 3.12 or newer is required:

```bash
pip install aiochainscan
```

The base install is dependency-light (httpx, orjson, tenacity, aiolimiter) and
needs no extras to decode ABI calldata, checksum addresses, or run the MCP
server's default keyless scanner. Extras are installed only when needed:

| Extra | Adds |
|---|---|
| `fastabi` | Rust accelerator for bulk ABI decoding (separate distribution) |
| `data` | Polars DataFrame exports |
| `mcp` | MCP server integration |
| `http2` | HTTP/2 support; disabled by default |
| `fallback` | Pure-Python Keccak fallback |

```bash
pip install "aiochainscan[data]"
```

## Try it in one command

The shortest end-to-end run — an address's transaction history to CSV, keyless,
no checkout:

```bash
curl -O https://raw.githubusercontent.com/VaitaR/aiochainscan/main/examples/02_export_to_csv.py
python 02_export_to_csv.py 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --all
```

The [recipe](https://github.com/VaitaR/aiochainscan/blob/main/examples/README.md)
says what it exports, what it does not, and how it behaves when a provider
refuses.

## Quick start

Blockscout is used without an API key. Its public instances are shared
infrastructure: they apply their own rate limiting and may answer a burst of
requests with `403` or a bot-protection page. For unattended or high-volume
work, configure Etherscan (or a self-hosted Blockscout instance) instead — or
put both behind a
[failover pool](https://github.com/VaitaR/aiochainscan/blob/main/docs/PAGINATION_AND_FAILOVER.md#multi-provider-failover).

```python
import asyncio

from aiochainscan import ChainscanClient


async def main() -> None:
    address = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'  # vitalik.eth

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        balance = await client.get_balance(address)
        transactions = await client.get_transactions(address)

    print(balance)       # native balance as a base-unit string
    print(transactions)  # one provider page


asyncio.run(main())
```

Etherscan requires an API key. Pass it explicitly or set `ETHERSCAN_KEY`:

```bash
export ETHERSCAN_KEY='your-api-key'
```

```python
async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    block = await client.get_block(20_000_000)
```

`from_config` also accepts a base URL instead of a chain name, which points the
client at a self-hosted Blockscout or an Etherscan proxy — see the
[API reference](https://github.com/VaitaR/aiochainscan/blob/main/docs/API_REFERENCE.md#self-hosted-instances-and-proxies).

## Providers

| Scanner | Default version | Authentication | Chains | Methods |
|---|---:|---|---:|---:|
| `etherscan` | v2 | API key | 61 | 33/33 |
| `blockscout` | v1 | None for public instances | 32 | 31/33 |
| `blockscout_v2` | v2 | None for public instances | 32 | 11/33 |
| `nodereal` | v1 | API key (`NODEREAL_KEY`), free tier | BSC only | 25/33 |

Thirty-three chains need no API key at all — every Blockscout instance
(Ethereum, Optimism, Gnosis, Polygon, Base, Arbitrum, Scroll, Sepolia, Mode,
Astar, Rootstock, ZKsync Era and twenty more), plus BSC through NodeReal's free
tier. Etherscan's 61 are the chains its keyless `GET /v2/chainlist` registry
listed on 2026-09-11; `aiochainscan.registry_sync.sync_etherscan_chains()` is
an opt-in call that re-reads that registry at runtime, so a chain Etherscan
adds after a release is constructible without waiting for one.

On Etherscan a free key's reach depends on the endpoint rather than the chain,
and BSC has no Blockscout instance at all — the measured details, and the full method list, are in the
[API reference](https://github.com/VaitaR/aiochainscan/blob/main/docs/API_REFERENCE.md).
`aiochainscan scanners` prints the same table for your own environment,
including which keys are configured.

## Complete data, or an exception

Page-returning methods (`get_transactions`, `get_logs`, `get_token_holders`)
return one page. `get_all_*` collects every page and `iter_*_streaming` yields
batches without materializing the result.

Both take `guarantee_complete`, defaulting to `True`: every matching record, or
an exception. Explorers cap a result window and answer a capped query with a
short page indistinguishable from the end of the data — so the library detects
the cap and splits the block range until every part fits, instead of handing
you a partial history that looks complete.

```python
# Complete, or an exception — the default.
transfers = await client.get_all_token_transfers(address)

# Opt out: fewer requests on wide ranges, truncation possible and silent.
transfers = await client.get_all_token_transfers(address, guarantee_complete=False)

# Constant memory for large histories.
async for batch in client.iter_transactions_streaming(address, batch_size=1_000):
    await store(batch)
```

When completeness cannot be reached the call raises `PaginationDataLossError`
or `CompletenessUnavailableError` rather than returning part of the data; the
second names the providers that can serve the request whole. Full contract,
failover-pool semantics and costs:
[Pagination, completeness and failover](https://github.com/VaitaR/aiochainscan/blob/main/docs/PAGINATION_AND_FAILOVER.md).

## One shape across providers

Provider payloads differ field by field (`blockNumber` vs `block_number`,
nested `from` objects vs flat strings). The normalized surface returns the same
frozen dataclasses whichever provider answered:

```python
txs = await client.get_transactions_normalized(address)
txs[0].hash, txs[0].block_number, txs[0].value_wei   # str, int, int (wei)
```

`get_*_normalized`, `get_all_*_normalized` and `iter_*_normalized` exist for
transactions, token transfers, internal transactions and logs. Everything else
stays provider-native.

Every scalar an explorer returns is a string — wei amounts, hex numbers, unix
timestamps. Module-level helpers convert them exactly, with no float step:

```python
from aiochainscan import hex_to_int, to_decimal_amount, wei_to_ether

wei_to_ether('1500000000000000000')        # Decimal('1.5') — exact, never float
to_decimal_amount('1500000', decimals=6)   # Decimal('1.5') — USDC-style tokens
hex_to_int('0x1a')                         # 26 — hex string, decimal string or int
```

## Decoding calls and events

Explorers return calldata as an opaque hex blob. Decoding it into a function
name and named arguments is part of the base install — `abi_pure.py` implements
the whole ABI spec in pure Python, so nothing beyond the four runtime
dependencies is needed. `pip install "aiochainscan[fastabi]"` swaps in a Rust
backend for the same results, faster; it is worth it for bulk work and
irrelevant for single decodes.

With a contract address, the ABI is fetched for you:

```python
contract = await client.get_contract(token_address)

async for event in contract.iter_events('Transfer', limit=100):
    print(event.args['from'], event.args['to'], event.args['value'])
```

With an ABI you already hold, decode directly — no client, no network:

```python
from aiochainscan.decode import decode_transaction_input

decoded = decode_transaction_input(transaction, abi)
decoded['decoded_func']   # 'transfer'
decoded['decoded_data']   # {'to': '0x…', 'amount': 1000000000000}
```

Two things worth knowing. `get_transaction()` returns the provider's raw
payload — it does not decode on its own. And a type this library cannot decode
raises `AbiTypeNotSupportedError` rather than returning an empty result, so a
gap never looks like undecodable calldata. See the
[SmartContract guide](https://github.com/VaitaR/aiochainscan/blob/main/docs/SMART_CONTRACT_API.md).

## ENS

ENS methods are available for Ethereum mainnet. Provider capabilities differ:
Blockscout v2 serves reverse lookup from its own address metadata, while
forward resolution reads the ENS registry over `eth_call` and therefore needs
a scanner that declares it (`etherscan`, `blockscout` v1). A scanner that does
not raises `MethodNotDeclaredError` rather than returning `None` — `None`
means the name (or the reverse record) does not exist.

```python
name = await client.lookup_address(address)
address = await client.resolve_name('vitalik.eth')
```

See the [ENS guide](https://github.com/VaitaR/aiochainscan/blob/main/docs/ENS_INTEGRATION.md).

## For AI agents

<!-- mcp-name: io.github.VaitaR/aiochainscan -->

An agent that should **query chains** runs the MCP server — 12 read-only tools
over stdio, with an envelope that carries pagination and caveats the agent can
act on:

```bash
uvx --from "aiochainscan[mcp]" aiochainscan mcp
```

Setup, the tool table and the response contract:
[MCP server](https://github.com/VaitaR/aiochainscan/blob/main/docs/MCP_SERVER.md).

An agent that should **write code** against the library wants the packaged
Agent Skill instead:

```bash
npx skills add VaitaR/aiochainscan
```

The skill ([`skills/aiochainscan/`](https://github.com/VaitaR/aiochainscan/tree/main/skills/aiochainscan))
carries the rules that decide whether generated code is correct — single-page
versus complete history, exact Wei math, provider coverage — plus a provider
matrix and recipes. Agents that read [Context7](https://context7.com) get the
same guidance from
[`context7.json`](https://github.com/VaitaR/aiochainscan/blob/main/context7.json)
without installing anything.

## Errors

```python
from aiochainscan import ChainscanRateLimitError, PaginationDataLossError

try:
    transactions = await client.get_all_transactions(address)
except ChainscanRateLimitError:
    raise  # The configured retry policy was exhausted.
except PaginationDataLossError:
    raise  # The provider could not return a complete range safely.
```

Most exceptions derive from `ChainscanClientError`, so one clause can bound a
call site; `MethodNotDeclaredError` and `AbiTypeNotSupportedError` subclass
`ValueError` instead, because both mean the caller asked for something this
configuration cannot serve. The full taxonomy is in the
[API reference](https://github.com/VaitaR/aiochainscan/blob/main/docs/API_REFERENCE.md#error-handling).

## Documentation

- [Getting started](https://github.com/VaitaR/aiochainscan/blob/main/docs/GETTING_STARTED.md) — install, provider choice, recipes, limits
- [Examples](https://github.com/VaitaR/aiochainscan/blob/main/examples/README.md) — starting with a keyless recipe: an address's transaction history to CSV
- [API reference](https://github.com/VaitaR/aiochainscan/blob/main/docs/API_REFERENCE.md) — providers, every call, conversions, error taxonomy
- [Pagination, completeness and failover](https://github.com/VaitaR/aiochainscan/blob/main/docs/PAGINATION_AND_FAILOVER.md)
- [MCP server](https://github.com/VaitaR/aiochainscan/blob/main/docs/MCP_SERVER.md)
- [SmartContract API](https://github.com/VaitaR/aiochainscan/blob/main/docs/SMART_CONTRACT_API.md)
- [ENS integration](https://github.com/VaitaR/aiochainscan/blob/main/docs/ENS_INTEGRATION.md)
- [Streaming pattern](https://github.com/VaitaR/aiochainscan/blob/main/docs/STREAMING_PATTERN.md)
- [Progress callbacks](https://github.com/VaitaR/aiochainscan/blob/main/docs/PROGRESS_CALLBACKS.md)
- [Migration guide](https://github.com/VaitaR/aiochainscan/blob/main/docs/MIGRATION_GUIDE.md)
- [Documentation index](https://github.com/VaitaR/aiochainscan/blob/main/docs/README.md)
- [Changelog](https://github.com/VaitaR/aiochainscan/blob/main/CHANGELOG.md)
- [Security policy](https://github.com/VaitaR/aiochainscan/blob/main/SECURITY.md)

## Development

```bash
git clone https://github.com/VaitaR/aiochainscan.git
cd aiochainscan
uv sync --extra dev
uv run pytest tests/ -q
uv run mypy aiochainscan --strict
uv run pre-commit run --all-files
```

See [CONTRIBUTING.md](https://github.com/VaitaR/aiochainscan/blob/main/CONTRIBUTING.md) for the contribution workflow.

## License

MIT — see [LICENSE](https://github.com/VaitaR/aiochainscan/blob/main/LICENSE).
