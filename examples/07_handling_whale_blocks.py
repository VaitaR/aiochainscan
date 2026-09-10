#!/usr/bin/env python3
"""Provider pagination limits and the completeness guarantee.

    python 07_handling_whale_blocks.py [address]

`get_all_*` and `iter_*_streaming` default to ``guarantee_complete=True``:
they return every matching record or raise. Two failures can end that walk,
and they mean different things:

* ``PaginationDataLossError`` — the range was narrowed until a *single block*
  still exceeded the provider's result window. Splitting worked and ran out.
* ``CompletenessUnavailableError`` — the endpoint has no range to split on
  this provider (a token-holder list has no block dimension), so narrowing
  cannot apply. ``exc.alternatives`` names the providers that can serve the
  method completely.

Both carry ``confirmed``: ``True`` means records were definitely cut off,
``False`` means the window came back exactly full and the API offers no way
to tell truncation from a clean end.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence

from aiochainscan import ChainscanClient, Method
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    CompletenessUnavailableError,
    PaginationDataLossError,
)
from aiochainscan.scanners import scanners_serving_completely

VITALIK = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
USDC = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'


async def guaranteed_history(address: str) -> None:
    """The default: complete data, or an exception that says why not."""
    # BlockScout v1, not v2: v1 declares block-range parameters and a 10,000
    # result window, which is what the guarantee machinery reacts to. v2
    # paginates by an opaque cursor and refuses bounded ranges outright.
    async with ChainscanClient.from_config('blockscout', 'ethereum') as client:
        try:
            transactions = await client.get_all_transactions(
                address, from_block=18_000_000, to_block=18_010_000
            )
            print(f'Complete: {len(transactions)} transactions in blocks 18.00M-18.01M')

        except PaginationDataLossError as exc:
            # One block alone is over the provider's cap: no narrower range exists.
            print(f'Block {exc.block_number} exceeds the provider cap')
            print(f'  fetched {exc.items_fetched} of at least {exc.api_limit}')
            print(f'  definitely truncated: {exc.confirmed}')
            print(f'  suggestion: {exc.suggested_action}')

        except CompletenessUnavailableError as exc:
            print(f'{exc.method} cannot be served completely by {exc.provider}')
            print(f'  try instead: {", ".join(exc.alternatives) or "no built-in provider"}')


async def holder_list_without_a_range() -> None:
    """The rangeless case, and the two ways out of it."""
    try:
        client = ChainscanClient.from_config('etherscan', 'ethereum')
    except ValueError as exc:
        print(f'Etherscan is not configured, skipping: {exc}')
        return

    async with client:
        try:
            holders = await client.get_all_token_holders(USDC)
            print(f'Complete holder list: {len(holders)}')

        except CompletenessUnavailableError as exc:
            print(f'Etherscan caps {exc.method} at {exc.api_limit} with no range to split.')
            print(f'  providers that serve it to exhaustion: {", ".join(exc.alternatives)}')
            await _switch_provider(exc.alternatives)

            # Way out 2: accept truncation, deliberately and visibly.
            truncated = await client.get_all_token_holders(USDC, guarantee_complete=False)
            print(f'  guarantee_complete=False returned {len(truncated)} (possibly partial)')

        except ChainscanClientApiError as exc:
            # Etherscan's holder endpoints are PRO-only, so a free key never
            # reaches the completeness question there — the remedy is the same
            # provider switch the error would have named.
            print(f'Etherscan refused the holder list: {exc}')
            await _switch_provider(scanners_serving_completely(Method.TOKEN_HOLDERS))


async def _switch_provider(alternatives: Sequence[str]) -> None:
    """Way out 1: a provider that paginates the holder list to exhaustion."""
    if not alternatives:
        print('  no built-in provider serves this method completely')
        return
    scanner = alternatives[0].split('/')[0]
    async with ChainscanClient.from_config(scanner, 'ethereum') as complete:
        page = await complete.get_token_holders(USDC)
        print(f'  {scanner} answers holder pages ({len(page)} in the first one)')


async def main(address: str) -> None:
    print('Bounded range, guaranteed complete')
    print('=' * 60)
    await guaranteed_history(address)

    print('\nRangeless endpoint (token holders)')
    print('=' * 60)
    await holder_list_without_a_range()


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else VITALIK))
