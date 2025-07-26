# aiochainscan

[![CI/CD](https://github.com/VaitaR/aiochainscan/workflows/CI/CD/badge.svg)](https://github.com/VaitaR/aiochainscan/actions)
[![PyPi](https://img.shields.io/pypi/v/aiochainscan.svg)](https://pypi.org/project/aiochainscan/)
[![License](https://img.shields.io/pypi/l/aiochainscan.svg)](https://pypi.org/project/aiochainscan/)
[![Coveralls](https://img.shields.io/coveralls/VaitaR/aiochainscan.svg)](https://coveralls.io/github/VaitaR/aiochainscan)
[![Versions](https://img.shields.io/pypi/pyversions/aiochainscan.svg)](https://pypi.org/project/aiochainscan/)

[Chainscan.io](https://chainscan.io) [API](https://chainscan.io/apis) async Python non-official wrapper.

> **Note**: This is a fork of the original [aioetherscan](https://github.com/ape364/aioetherscan) project by ape364, renamed and adapted for multi-chain support.

## Features

### API modules

Supports all API modules:

* [Accounts](https://docs.chainscan.io/api-endpoints/accounts)
* [Contracts](https://docs.chainscan.io/api-endpoints/contracts)
* [Transactions](https://docs.chainscan.io/api-endpoints/stats)
* [Blocks](https://docs.chainscan.io/api-endpoints/blocks)
* [Event logs](https://docs.chainscan.io/api-endpoints/logs)
* [GETH/Parity proxy](https://docs.chainscan.io/api-endpoints/geth-parity-proxy)
* [Tokens](https://docs.chainscan.io/api-endpoints/tokens)
* [Gas Tracker](https://docs.chainscan.io/api-endpoints/gas-tracker)
* [Stats](https://docs.chainscan.io/api-endpoints/stats-1)

Also provides extra modules:
* `utils` allows to fetch a lot of transactions without timeouts and not getting banned
* `links` helps to compose links to address/tx/etc

### Blockchains

Supports blockchain explorers:

* [Chainscan](https://docs.chainscan.io/getting-started/endpoint-urls)
* [BscScan](https://docs.bscscan.com/getting-started/endpoint-urls)
* [PolygonScan](https://docs.polygonscan.com/getting-started/endpoint-urls)
* [Optimism](https://docs.optimism.chainscan.io/getting-started/endpoint-urls)
* [Arbiscan](https://docs.arbiscan.io/getting-started/endpoint-urls)
* [FtmScan](https://docs.ftmscan.com/getting-started/endpoint-urls)

## Installation

### For users
```sh
pip install -U aiochainscan
```

### For development
```sh
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/VaitaR/aiochainscan.git
cd aiochainscan

# Install dependencies and create virtual environment
uv sync --dev

# Activate the virtual environment
source .venv/bin/activate  # On Unix/macOS
# .venv\Scripts\activate    # On Windows
```

## Development

### Running tests
```sh
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=aiochainscan

# Run linting
uv run ruff check
uv run ruff format --check

# Auto-fix linting issues
uv run ruff check --fix
uv run ruff format
```

### Adding dependencies
```sh
# Add a production dependency
uv add package_name

# Add a development dependency
uv add --dev package_name
```

## Usage
Register Chainscan account and [create free API key](https://etherscan.io).

```python
import asyncio

from aiohttp_retry import ExponentialRetry
from asyncio_throttle import Throttler

from aiochainscan import Client


async def main():
    throttler = Throttler(rate_limit=1, period=6.0)
    retry_options = ExponentialRetry(attempts=2)

    c = Client('YourApiKeyToken', throttler=throttler, retry_options=retry_options)

    try:
        print(await c.stats.eth_price())
        print(await c.block.block_reward(123456))

        async for t in c.utils.token_transfers_generator(
                address='0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2',
                start_block=16734850,
                end_block=16734850
        ):
            print(t)
    finally:
        await c.close()


if __name__ == '__main__':
    asyncio.run(main())
```
