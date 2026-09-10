#!/usr/bin/env python3
"""One address across several chains.

    python 06_multichain_comparison.py [address]

Each chain needs its own client — a client is bound to one provider instance —
but the code is identical per chain, and the native currency symbol comes from
the client rather than a table in this file.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from decimal import Decimal

from aiochainscan import ChainscanClient, wei_to_ether

VITALIK = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

CHAINS = ('ethereum', 'polygon', 'arbitrum', 'optimism', 'base', 'gnosis')


@dataclass(frozen=True)
class ChainBalance:
    chain: str
    currency: str
    balance: Decimal
    token_count: int

    @property
    def active(self) -> bool:
        return self.balance > 0 or self.token_count > 0


async def check_chain(chain: str, address: str) -> ChainBalance:
    async with ChainscanClient.from_config('blockscout_v2', chain) as client:
        balance, portfolio = await asyncio.gather(
            client.get_balance(address),
            client.get_token_portfolio(address),
        )
        return ChainBalance(
            chain=chain,
            currency=client.currency,
            balance=wei_to_ether(balance),
            token_count=len(portfolio),
        )


async def main(address: str) -> None:
    print(f'Address: {address}\n')
    results = await asyncio.gather(
        *(check_chain(chain, address) for chain in CHAINS),
        return_exceptions=True,
    )

    print(f'{"chain":<12} {"balance":>22}  {"tokens":>6}  status')
    print('-' * 56)
    active = 0
    tokens = 0
    for chain, result in zip(CHAINS, results, strict=True):
        if isinstance(result, BaseException):
            print(f'{chain:<12} {type(result).__name__}: {str(result)[:28]}')
            continue
        amount = f'{result.balance:,.6f} {result.currency}'
        print(
            f'{result.chain:<12} {amount:>22}  {result.token_count:>6}  '
            f'{"active" if result.active else "empty"}'
        )
        active += result.active
        tokens += result.token_count

    print(f'\nActive on {active}/{len(CHAINS)} chains; {tokens} token positions in total.')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else VITALIK))
