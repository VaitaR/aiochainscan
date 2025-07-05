# aiochainscan

Async Python wrapper for Chainscan API.

> **Note**: This is a fork of the original [aioetherscan](https://github.com/ape364/aioetherscan) project by ape364, renamed and adapted for multi-chain support.

## Features

- Async/await support with aiohttp
- Support for Ethereum blockchain explorer
- Basic API modules for accounts, blocks, transactions

## Installation

```sh
pip install aiochainscan
```

## Usage

```python
import asyncio
from aiochainscan import Client

async def main():
    c = Client('YourApiKeyToken')
    try:
        print(await c.stats.eth_price())
    finally:
        await c.close()

if __name__ == '__main__':
    asyncio.run(main())
```
