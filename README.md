# aiochainscan

[![PyPI](https://img.shields.io/pypi/v/aiochainscan.svg)](https://pypi.org/project/aiochainscan/)
[![Python](https://img.shields.io/pypi/pyversions/aiochainscan.svg)](https://pypi.org/project/aiochainscan/)
[![License](https://img.shields.io/pypi/l/aiochainscan.svg)](https://github.com/VaitaR/aiochainscan/blob/main/LICENSE)

`aiochainscan` is an asynchronous Python client for Etherscan-compatible,
Blockscout and NodeReal blockchain explorer APIs, covering 36 chains. It
exposes one public client, `ChainscanClient`, across account, transaction,
block, contract, token, log, gas, and JSON-RPC endpoints.

The library is intended for applications that need a consistent explorer API
without coupling request code to one provider. History reads are
[guaranteed-complete](#pagination-and-streaming) by default: every matching
record, or an exception — never a silently truncated page. It also includes
streaming iteration, rate limiting, retries, optional Polars exports, ENS
resolution, and ABI decoding.

> Status: stable public API (1.x). The public surface is `ChainscanClient`;
> provider coverage differs by scanner and endpoint. Released changes are
> listed in the [changelog](https://github.com/VaitaR/aiochainscan/blob/main/CHANGELOG.md).

## Installation

Python 3.12 or newer is required:

```bash
pip install aiochainscan
```

The optional Rust accelerator installs as a separate distribution:

```bash
pip install "aiochainscan[fastabi]"
```

Optional extras are installed only when needed:

| Extra | Adds |
|---|---|
| `data` | Polars DataFrame exports |
| `mcp` | MCP server integration |
| `http2` | HTTP/2 support; disabled by default |
| `fallback` | Pure-Python Keccak fallback |

For example:

```bash
pip install "aiochainscan[data]"
```

The base install is dependency-light (httpx, orjson, tenacity, aiolimiter) and
needs no extras to decode ABI calldata, checksum addresses, or run the MCP
server's default keyless scanner — see the extras table for the accelerators.

## Quick start

Blockscout is used without an API key. Its public instances are shared
infrastructure: they apply their own rate limiting and may answer a burst of
requests with `403` or a bot-protection page. For unattended or high-volume
work, configure Etherscan (or a self-hosted Blockscout instance) instead — or
put both behind [`ChainscanPool`](https://github.com/VaitaR/aiochainscan#multi-provider-failover-pool).

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

## API model

`ChainscanClient.from_config(scanner, network)` accepts chain names such as
`ethereum`, `base`, `polygon`, `arbitrum`, and `optimism`, or a numeric chain
ID. The built-in scanner names are:

| Scanner | Default version | Authentication | Coverage |
|---|---:|---|---|
| `etherscan` | v2 | API key | Etherscan-compatible endpoint set |
| `blockscout` | v1 | None for public instances | Etherscan-compatible endpoint set |
| `blockscout_v2` | v2 | None for public instances | Native Blockscout v2 subset |
| `nodereal` | v1 | API key (`NODEREAL_KEY`), free tier | BSC-only subset — the only route to BSC here, Blockscout runs no BSC instance |

Scanner support is checked at call time. A convenience method that is not
declared by the selected scanner raises `ValueError`.

### Self-hosted instances and proxies

Instead of a chain name, `from_config` accepts a base URL — any string with a
`scheme://` prefix is treated as an instance root, anything else resolves
through the chain registry as before:

```python
# Self-hosted BlockScout — keyless, any chain (even private ones)
async with ChainscanClient.from_config(
    'blockscout_v2', 'https://my-blockscout.internal', expected_chain_id=100
) as client:
    info = await client.get_chain_info()   # ChainInfo(chain_id=..., explorer_url=...)
    await client.validate_chain(100)       # ChainscanDataError on mismatch

    await client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')

# Etherscan v2 behind a proxy — API key still required, chain id mandatory
client = ChainscanClient.from_config(
    'etherscan', 'https://eth-proxy.internal',
    api_key='...', expected_chain_id=137,
)
```

Base URLs are validated (`https` by default — cleartext `http` requires
`allow_http=True`; credentials, query strings and `..` segments are refused).
`expected_chain_id` is checked once before the first request and a mismatch
fails fast with `ChainscanDataError`. Chain identity is resolved through the
provider itself — BlockScout via its JSON-RPC `eth_chainId` endpoint, Etherscan
via the keyless `v2/chainlist` registry — and cached for an hour in a
process-shared cache, so the ~60-network chainlist is downloaded at most once.
NodeReal does not support custom base URLs (its API key rides in the URL path).

Common operations:

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

## One shape across providers

Provider payloads differ field by field (`blockNumber` vs `block_number`,
nested `from` objects vs flat strings). The normalized surface returns the same
frozen dataclasses whichever provider answered:

```python
from aiochainscan import ChainscanClient

async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
    txs = await client.get_transactions_normalized(address)
    txs[0].hash, txs[0].block_number, txs[0].value_wei   # str, int, int (wei)
```

`get_*_normalized` (one page), `get_all_*_normalized` (everything) and
`iter_*_normalized` (batches) exist for transactions, token transfers,
internal transactions and logs; a single block converts with
`get_block_normalized`. The dataclasses live in
[`aiochainscan.domain.normalized`](https://github.com/VaitaR/aiochainscan/blob/main/aiochainscan/domain/normalized.py)
and keep `raw` for the provider-specific fields. Everything else stays
provider-native, so switching providers on a raw method means expecting that
provider's field names.

## Pagination and streaming

Page-returning methods do not fetch an entire history:

- `get_transactions()` returns one page.
- `get_logs()` returns one page, subject to provider limits.
- `get_token_holders()` returns one page.
- `get_all_*()` collects all pages into a list.
- `iter_*_streaming()` yields batches and avoids materializing the full result.

`get_all_*()` and `iter_*_streaming()` take `guarantee_complete`, which
defaults to `True`: the call returns every matching record or raises. Explorers
cap a result window (Etherscan and Blockscout v1 both at `page * offset`
10 000) and answer a capped query with a short page that is indistinguishable
from the end of the data, so the library detects the cap and splits the block
range until every part fits.

```python
# Complete, or an exception — the default.
transfers = await client.get_all_token_transfers(address)

# Opt out: fewer requests on wide ranges, truncation possible and silent.
transfers = await client.get_all_token_transfers(address, guarantee_complete=False)
```

Two failures can surface: `PaginationDataLossError` when a *single block*
still exceeds the cap (splitting worked and ran out) and
`CompletenessUnavailableError` when the endpoint has no block range to split
at all — the holder list on Etherscan — in which case the exception names the
providers that can serve it completely.

Use streaming for large histories:

```python
async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
    async for batch in client.iter_transactions_streaming(address, batch_size=1_000):
        await store(batch)
```

The `data` extra adds DataFrame exports. These methods paginate and materialize
their result:

```python
async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    frame = await client.get_transactions_df(address)
```

Balances, token values, and supplies are returned as strings in base units.
Convert them using the asset's decimals; do not assume 18 decimals for every
token.

## Multi-provider failover pool

`ChainscanPool` composes several providers for the same chain into one client.
Providers are listed in priority order; the pool routes every call to the best
available one:

```python
from aiochainscan import ChainscanPool

async with ChainscanPool.from_config(
    [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]
) as pool:
    balance = await pool.get_balance(address)  # served by etherscan
    pool.last_provider                        # 'etherscan/ethereum'
```

Routing semantics:

- **Sticky provider.** The provider that last answered keeps serving while it
  is healthy — no ping-ponging between providers.
- **Classified failover.** Rate limits, network/5xx errors (after the
  transport retries are exhausted), missing API keys and plan restrictions
  ("chain not on the free plan") switch to the next provider with a
  `ChainscanProviderSwitchWarning`. Bad arguments, not-found answers and data
  errors are fatal and propagate immediately.
- **Cooldown.** A failed provider is skipped without a single HTTP attempt for
  a class-specific window; rate-limit cooldowns honour the advertised
  `retry_after`. After the cooldown the provider is tried again (half-open).
- **Capability routing.** A provider that does not declare a method in its
  SPECS is routed around silently; the pool's coverage is the union of its
  members.
- **Pagination binding.** `get_all_*` / `iter_*_streaming` calls are pinned to
  one provider for their whole run — switching mid-pagination would corrupt
  opaque cursors. Failover happens only if the very first page fails.

When every provider fails (or is cooling down), `ProviderPoolExhaustedError`
carries the ordered `(provider, exception)` attempts. Pool state lives in the
pool object only. The pool exposes the full `ChainscanClient` surface, plus
`last_provider`, `provider_states()` and `reset_cooldowns()` for
observability.

## Contracts and ENS

`get_contract()` fetches a verified ABI and returns a `SmartContract` object for
decoded event and transaction iteration:

```python
async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    contract = await client.get_contract(contract_address)

    async for event in contract.iter_events('Transfer', limit=100):
        print(event.block_number, event.args)
```

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

See the [SmartContract guide](https://github.com/VaitaR/aiochainscan/blob/main/docs/SMART_CONTRACT_API.md) and
[ENS guide](https://github.com/VaitaR/aiochainscan/blob/main/docs/ENS_INTEGRATION.md).

## MCP server

<!-- mcp-name: io.github.VaitaR/aiochainscan -->

The `mcp` extra exposes the client to AI agents (Claude Desktop, Cursor, …)
over stdio with 12 read-only tools and an agent-friendly response contract:

```bash
pip install "aiochainscan[mcp]" && aiochainscan mcp   # installed
uvx --from "aiochainscan[mcp]" aiochainscan mcp       # without installing
```

In a client's config file that means `"command": "uvx"`, `"args":
["--from", "aiochainscan[mcp]", "aiochainscan", "mcp"]`.
`python -m aiochainscan.mcp_server` still works and starts the same server.

For clients that install extensions instead of editing config, `mcpb/` builds
an [MCPB bundle](https://github.com/modelcontextprotocol/mcpb) (`make mcpb`)
— the format [Smithery](https://smithery.ai/docs/build/publish) distributes
local stdio servers in. The bundle installs the pinned release with uv and
asks for the optional API keys in the client's UI.

| Tool | What it does |
|---|---|
| `get_wallet_balance` | Native-coin balance (Wei string + human-readable) |
| `get_address_overview` | Composite snapshot: balance + newest txs + ERC-20 + NFTs (partial failures land in `notes`) |
| `get_transactions` | Curated transaction pages with opaque cursors |
| `get_transaction_info` | Tx details with the call input decoded via the verified ABI (fastabi) |
| `get_token_portfolio` | ERC-20 holdings (curated, paginated) |
| `get_token_info` | Token metadata, supply (raw + formatted), holder count |
| `get_token_holders` / `get_top_token_holders` | Holder pages with totals and human-readable balances |
| `get_contract_abi` | Verified-ABI summary (function/event signatures) |
| `read_contract` | `eth_call` with the ABI fetched automatically — no manual ABI input |
| `resolve_ens` | ENS in both directions |
| `list_chains` | Served chains with substring filter |

Every tool returns an envelope `{data, notes, instructions, pagination}` plus
a compact text summary. `notes` explain limits and caveats honestly (e.g. a
scanner that lacks an endpoint), `instructions` bridge to the next call, and
paginated tools ship a ready-to-execute `pagination.next_call` — the agent
never has to understand cursor internals.

Tools take a `chain` parameter (name, numeric ID, or a self-hosted instance
URL) and an optional `scanner` override. The default scanner is keyless
`blockscout` (`AIOCHAINSCAN_MCP_SCANNER` env override); `etherscan` covers
every chain but needs `ETHERSCAN_KEY`.

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

## Writing code with an AI agent

Three ways to give an agent the library, from thinnest to fullest:

```bash
npx skills add VaitaR/aiochainscan      # installs the packaged Agent Skill
```

The skill ([`skills/aiochainscan/`](https://github.com/VaitaR/aiochainscan/tree/main/skills/aiochainscan))
carries the rules that decide whether generated code is correct — single-page
versus complete history, exact Wei math, provider coverage — plus a provider
matrix and recipes as reference files. Agents that read
[Context7](https://context7.com) get the same guidance from
[`context7.json`](https://github.com/VaitaR/aiochainscan/blob/main/context7.json)
without installing anything.

For an agent that should *query chains* rather than write code, run the
[MCP server](#mcp-server) — 12 read-only tools over stdio.

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

Pool users get two more failure modes: `ProviderPoolExhaustedError` (every
provider failed or is cooling — see `exc.attempts` for the per-provider
causes) and `ChainscanProviderSwitchWarning` (a provider was routed around;
filter it if the diagnostics are noisy).

## Documentation

- [Getting started](https://github.com/VaitaR/aiochainscan/blob/main/docs/GETTING_STARTED.md) — install, provider choice, recipes, limits
- [Documentation index](https://github.com/VaitaR/aiochainscan/blob/main/docs/README.md)
- [SmartContract API](https://github.com/VaitaR/aiochainscan/blob/main/docs/SMART_CONTRACT_API.md)
- [ENS integration](https://github.com/VaitaR/aiochainscan/blob/main/docs/ENS_INTEGRATION.md)
- [Progress callbacks](https://github.com/VaitaR/aiochainscan/blob/main/docs/PROGRESS_CALLBACKS.md)
- [Migration guide](https://github.com/VaitaR/aiochainscan/blob/main/docs/MIGRATION_GUIDE.md)
- [Examples](https://github.com/VaitaR/aiochainscan/blob/main/examples/README.md)
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
