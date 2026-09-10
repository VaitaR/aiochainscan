#!/usr/bin/env python3
"""ENS resolution: what each provider can and cannot answer.

    python ens_demo.py

Reverse lookup (address → name) works keylessly: BlockScout v2 carries the
reverse record in its address-info payload. Forward resolution (name → address)
is an `eth_call` against the ENS registry, so it needs a provider that declares
`PROXY_ETH_CALL` — Etherscan does, BlockScout v2 does not and says so with
`MethodNotDeclaredError` instead of answering `None`.

`None` means one thing only: the name (or the reverse record) does not exist.
"""

from __future__ import annotations

import asyncio
import time

from aiochainscan import ChainscanClient
from aiochainscan.exceptions import MethodNotDeclaredError

NAMES = ('vitalik.eth', 'nick.eth', 'uniswap.eth', 'ens.eth')

ADDRESSES = (
    '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',  # vitalik.eth
    '0xb8c2C29ee19D8307cb7255e1Cd9CbDE883A267d5',  # nick.eth
    '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',  # UNI token, no reverse record
    '0x0000000000000000000000000000000000000000',  # zero address
)


def header(title: str) -> None:
    print(f'\n{"=" * 70}\n{title}\n{"=" * 70}')


def forward_client() -> ChainscanClient | None:
    """A client that declares eth_call, or None with the reason printed."""
    try:
        return ChainscanClient.from_config('etherscan', 'ethereum')
    except ValueError as exc:
        print(f'  forward resolution needs an eth_call provider: {exc}')
        print("  set ETHERSCAN_KEY for the forward demos; reverse lookup doesn't need it")
        return None


async def demo_reverse_lookup() -> None:
    header('Reverse lookup (address → name), keyless')

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        for address in ADDRESSES:
            name = await client.lookup_address(address)
            print(f'  {address} → {name or "no reverse record"}')


async def demo_forward_resolution() -> None:
    header('Forward resolution (name → address)')

    client = forward_client()
    if client is None:
        return
    async with client:
        for name in NAMES:
            address = await client.resolve_name(name)
            print(f'  {name:14} → {address or "no such name"}')


async def demo_declared_methods_are_honest() -> None:
    header('A provider that cannot answer says so')

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        try:
            await client.resolve_name('vitalik.eth')
        except MethodNotDeclaredError as exc:
            print(f'  blockscout_v2 forward resolution → {type(exc).__name__}')
            print(f'  {str(exc)[:88]}...')
        else:
            print('  blockscout_v2 answered a forward resolution')


async def demo_batch_operations() -> None:
    header('Batch operations')

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        found = await client.lookup_addresses(list(ADDRESSES))
        print(f'  reverse: {len(found)}/{len(ADDRESSES)} addresses have a name')
        for address, name in found.items():
            print(f'    {address} → {name}')

    client = forward_client()
    if client is None:
        return
    async with client:
        names = [*NAMES, 'almost-certainly-not-taken-x9.eth']
        resolved = await client.resolve_names(names)
        print(f'  forward: {len(resolved)}/{len(names)} names resolved')
        for name, address in resolved.items():
            print(f'    {name:14} → {address}')


async def demo_caching() -> None:
    header('Caching')

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        await client.ens.clear_cache()

        start = time.perf_counter()
        first = await client.lookup_address(ADDRESSES[0])
        cold = time.perf_counter() - start

        start = time.perf_counter()
        await client.lookup_address(ADDRESSES[0])
        warm = time.perf_counter() - start

        print(f'  {ADDRESSES[0]} → {first}')
        print(f'  cold {cold * 1000:.0f} ms, cached {warm * 1000:.2f} ms')


async def demo_wrong_network() -> None:
    header('ENS is Ethereum mainnet only')

    async with ChainscanClient.from_config('blockscout_v2', 'polygon') as client:
        try:
            await client.resolve_name('vitalik.eth')
        except ValueError as exc:
            print(f'  {exc}')


async def demo_invalid_input() -> None:
    header('Input that cannot be an ENS name is answered without a request')

    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        for value, description in (
            ('', 'empty string'),
            ('not-ens', 'no .eth suffix'),
            ('invalid.com', 'wrong TLD'),
        ):
            print(f'  {description:16} → {await client.resolve_name(value)}')


async def main() -> None:
    await demo_reverse_lookup()
    await demo_forward_resolution()
    await demo_declared_methods_are_honest()
    await demo_batch_operations()
    await demo_caching()
    await demo_wrong_network()
    await demo_invalid_input()


if __name__ == '__main__':
    asyncio.run(main())
