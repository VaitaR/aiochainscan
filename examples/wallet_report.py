import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiochainscan import ChainscanClient
from aiochainscan.exceptions import ChainscanNetworkError, ChainscanRateLimitError

T = TypeVar('T')


async def with_retry(fn: Callable[[], Awaitable[T]]) -> T:
    rate_limit_delays = [1, 2, 4]
    for attempt, delay in enumerate(rate_limit_delays, start=1):
        try:
            return await fn()
        except ChainscanRateLimitError:
            if attempt == len(rate_limit_delays):
                raise
            print(
                f'Rate limit hit, retrying in {delay}s (attempt {attempt}/{len(rate_limit_delays)})...'
            )
            await asyncio.sleep(delay)
        except ChainscanNetworkError:
            print('Network error, retrying in 2s (1 retry)...')
            await asyncio.sleep(2)
            return await fn()
    raise RuntimeError('Unreachable')


async def main() -> None:
    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        balance = await with_retry(
            lambda: client.get_balance('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
        )
    print(f'Balance: {balance}')


if __name__ == '__main__':
    asyncio.run(main())
