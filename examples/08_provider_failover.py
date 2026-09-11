#!/usr/bin/env python3
"""One address, two explorers, automatic failover between them.

Self-contained — needs nothing but the published package:

    pip install aiochainscan
    python 08_provider_failover.py [address]

A single explorer is a single point of failure: public Blockscout instances
rate-limit and answer bursts with `403`, Etherscan needs a key and refuses
some chains on the free tier. `ChainscanPool` composes several providers for
the SAME chain behind the full `ChainscanClient` surface and routes around
the ones that are failing.

What the pool decides for you:

* Which failures are worth switching over (rate limit, 5xx, missing key,
  plan restriction, a method the provider does not declare) and which are
  the caller's own fault (bad arguments, not found) and must propagate.
* How long to skip a provider that just failed — a cooldown per failure
  class, so a rate-limited explorer is not hammered again on the next call.
* Which provider to keep using once one works (sticky routing, no yo-yo).

Without `ETHERSCAN_KEY` the Etherscan member cannot be constructed. That is
not an error: `from_config` drops it with a warning and the pool runs on the
remaining providers. Set the key to see two members and real failover.
"""

from __future__ import annotations

import asyncio
import sys
import warnings

from aiochainscan import ChainscanPool, wei_to_ether
from aiochainscan.exceptions import (
    ChainscanProviderSwitchWarning,
    ProviderPoolExhaustedError,
)

VITALIK = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

# Priority order: Etherscan first when a key is configured, Blockscout as the
# keyless rescue. Both serve Ethereum mainnet — a pool is one chain.
PROVIDERS = [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]


async def main(address: str) -> None:
    # A switch is reported, never silent: the warning names both providers
    # and the failure that caused it.
    warnings.simplefilter('always', ChainscanProviderSwitchWarning)

    async with ChainscanPool.from_config(PROVIDERS) as pool:
        print(f'Pool members, in priority order: {", ".join(pool.providers)}')

        try:
            balance = await pool.get_balance(address)
            transactions = await pool.get_transactions(address)
        except ProviderPoolExhaustedError as exc:
            # Every member failed. `attempts` is the full audit trail:
            # which provider was tried, and what it answered.
            print('No provider could serve the request:')
            for provider, error in exc.attempts:
                print(f'  {provider}: {type(error).__name__}: {error}')
            raise SystemExit(1) from None

        print(f'Balance: {wei_to_ether(balance)} ETH')
        print(f'Transactions on this page: {len(transactions)}')
        print(f'Answered by: {pool.last_provider}')

        for label, state in pool.provider_states().items():
            status = (
                'available'
                if state['available']
                else (f'cooling for {state["cooldown_remaining"]:.0f}s')
            )
            sticky = ' (sticky)' if state['sticky'] else ''
            print(f'  {label}: {status}{sticky}')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else VITALIK))
