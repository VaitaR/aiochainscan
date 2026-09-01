# aiochainscan

`aiochainscan` is an asynchronous Python client for Etherscan-compatible and
Blockscout blockchain explorer APIs. It exposes one public client,
`ChainscanClient`, across account, transaction, block, contract, token, log,
gas, and JSON-RPC endpoints.

The library is intended for applications that need a consistent explorer API
without coupling request code to one provider. It includes pagination helpers,
streaming iteration, rate limiting, retries, optional Polars exports, ENS
resolution, and ABI decoding.

> Status: beta. The public API is `ChainscanClient`; provider coverage differs
> by scanner and endpoint.

## Installation

Python 3.12 or newer is required. Until the 0.6 release is published, install
the current API from GitHub:

```bash
pip install "aiochainscan @ git+https://github.com/VaitaR/aiochainscan.git"
```

The package currently published on PyPI is from the older 0.2 series and does
not match this documentation.

Optional extras are installed only when needed:

| Extra | Adds |
|---|---|
| `data` | Polars DataFrame exports |
| `mcp` | MCP server integration |
| `http2` | HTTP/2 support; disabled by default |
| `fallback` | Pure-Python ABI and Keccak fallback |

For example:

```bash
pip install "aiochainscan[data] @ git+https://github.com/VaitaR/aiochainscan.git"
```

## Quick start

Blockscout can be used without an API key:

```python
import asyncio

from aiochainscan import ChainscanClient


async def main() -> None:
    address = '0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3'

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

Scanner support is checked at call time. A convenience method that is not
declared by the selected scanner raises `ValueError`.

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

    # Contracts and logs
    abi = await client.get_contract_abi(contract_address)
    source = await client.get_contract_source(contract_address)
    logs = await client.get_logs(contract_address, from_block=20_000_000)

    # Tokens and network data
    token_balance = await client.get_token_balance(address, token_address)
    gas = await client.get_gas_oracle()
    price = await client.get_eth_price()
```

The `Method` enum contains the low-level operation set. Use `client.call()` when
you need an operation without a dedicated convenience method:

```python
from aiochainscan import Method

result = await client.call(Method.ACCOUNT_BALANCE, address=address)
```

## Pagination and streaming

Page-returning methods do not fetch an entire history:

- `get_transactions()` returns one page.
- `get_logs()` returns one page, subject to provider limits.
- `get_all_*()` collects all pages into a list.
- `iter_*_streaming()` yields batches and avoids materializing the full result.

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
Blockscout v2 supports reverse lookup, while forward resolution requires a
scanner that exposes `eth_call`.

```python
name = await client.lookup_address(address)
address = await client.resolve_name('vitalik.eth')
```

See the [SmartContract guide](docs/SMART_CONTRACT_API.md) and
[ENS guide](docs/ENS_INTEGRATION.md).

## Error handling

```python
from aiochainscan import (
    ChainscanClientApiError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
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
```

## Documentation

- [Documentation index](docs/README.md)
- [SmartContract API](docs/SMART_CONTRACT_API.md)
- [ENS integration](docs/ENS_INTEGRATION.md)
- [Progress callbacks](docs/PROGRESS_CALLBACKS.md)
- [Migration guide](docs/MIGRATION_GUIDE.md)
- [Examples](examples/README.md)

## Development

```bash
git clone https://github.com/VaitaR/aiochainscan.git
cd aiochainscan
uv sync --extra dev
uv run pytest tests/ -q
uv run mypy aiochainscan --strict
uv run pre-commit run --all-files
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow.

## License

MIT
