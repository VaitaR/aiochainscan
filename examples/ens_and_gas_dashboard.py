"""
ENS resolution + multi-chain balance lookup, and a gas/price dashboard.
Uses only the public aiochainscan ChainscanClient API.
"""

import asyncio
import logging
import os

from aiochainscan import ChainscanClient
from aiochainscan.exceptions import ChainscanNetworkError

logger = logging.getLogger(__name__)

_BALANCE_NETWORKS = ['ethereum', 'arbitrum', 'base']


async def resolve_ens_and_balances(ens_name: str) -> dict:
    """
    Resolve an ENS name to an address, fetch ETH balances on multiple chains,
    and confirm the reverse ENS lookup matches.

    Args:
        ens_name: e.g. "vitalik.eth"

    Returns:
        {
            "address": str,
            "ens_confirmed": str,   # reverse-lookup result from blockscout_v2
            "balances": {
                "ethereum": float,  # ETH (not Wei)
                "arbitrum": float,
                "base": float,
            },
        }
    """
    # 1. Forward resolve: ENS name → address (requires etherscan)
    async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
        address = await client.resolve_name(ens_name)

    logger.info('Resolved %s → %s', ens_name, address)

    # 2. Balances across chains (blockscout_v2, no API key needed)
    balances: dict[str, float] = {}
    for network in _BALANCE_NETWORKS:
        async with ChainscanClient.from_config('blockscout_v2', network) as client:
            try:
                raw = await client.get_balance(address)
                balances[network] = int(raw) / 10**18
            except ChainscanNetworkError as exc:
                logger.error('Network error on %s: %s — skipping', network, exc)

    # 3. Reverse lookup: address → ENS name (blockscout_v2 on ethereum)
    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        ens_confirmed = await client.lookup_address(address)

    logger.info('Reverse lookup %s → %s', address, ens_confirmed)

    return {
        'address': address,
        'ens_confirmed': ens_confirmed,
        'balances': balances,
    }


async def gas_dashboard() -> dict:
    """
    Fetch current ETH price and gas oracle recommendations from Etherscan.

    Returns:
        {
            "eth_usd": float,
            "gas_safe_gwei": str,
            "gas_fast_gwei": str,
        }

    Raises:
        RuntimeError: if ETHERSCAN_KEY is not set in the environment.
    """
    if not os.environ.get('ETHERSCAN_KEY'):
        raise RuntimeError('ETHERSCAN_KEY not set')

    async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
        price = await client.get_eth_price()
        gas = await client.get_gas_oracle()

    return {
        'eth_usd': float(price['ethusd']),
        'gas_safe_gwei': gas['SafeGasPrice'],
        'gas_fast_gwei': gas['FastGasPrice'],
    }


# ---------------------------------------------------------------------------
# Quick demo – run with:  python -m examples.ens_and_gas_dashboard
# ---------------------------------------------------------------------------
async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    print('=== ENS + Balances ===')
    result = await resolve_ens_and_balances('vitalik.eth')
    print(f"Address      : {result['address']}")
    print(f"ENS confirmed: {result['ens_confirmed']}")
    for net, bal in result['balances'].items():
        print(f'  {net:10s}: {bal:.6f} ETH')

    print('\n=== Gas Dashboard ===')
    try:
        dash = await gas_dashboard()
        print(f"ETH price : ${dash['eth_usd']:,.2f}")
        print(f"Safe gas  : {dash['gas_safe_gwei']} Gwei")
        print(f"Fast gas  : {dash['gas_fast_gwei']} Gwei")
    except RuntimeError as exc:
        print(f'Skipped: {exc}')


if __name__ == '__main__':
    asyncio.run(_main())
