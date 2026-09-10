#!/usr/bin/env python3
"""The Etherscan v2 surface: everything a keyless provider cannot serve.

    export ETHERSCAN_KEY='your-key'      # https://etherscan.io/apis
    python 04_etherscan_with_api_key.py [address]

The key is resolved by the library (environment, ``./.env.local``, ``./.env``,
``~/.aiochainscan/.env``) — this script never reads it itself. One Etherscan v2
key serves every chain the scanner declares; `from_config('etherscan', 8453)`
is the same account.
"""

from __future__ import annotations

import asyncio
import json
import sys

from aiochainscan import ChainscanClient, to_decimal_amount, wei_to_ether

VITALIK = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
USDC = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'


async def main(address: str) -> None:
    try:
        client = ChainscanClient.from_config('etherscan', 'ethereum')
    except ValueError as exc:
        print(f'Etherscan is not configured: {exc}')
        print("Set ETHERSCAN_KEY, or use 'blockscout_v2' for keyless access.")
        raise SystemExit(1) from exc

    async with client:
        balance = await client.get_balance(address)
        print(f'Balance: {wei_to_ether(balance):.6f} ETH')

        # A bounded range and explicit sort: parameters the Etherscan dialect
        # carries and the Blockscout v2 dialect does not.
        transactions = await client.get_transactions_normalized(
            address, start_block=18_000_000, offset=5
        )
        print(f'\nTransactions from block 18,000,000 ({len(transactions)}):')
        for tx in transactions:
            print(f'  {tx.hash} {wei_to_ether(tx.value_wei):>12.6f} ETH')

        internal = await client.get_internal_transactions(address)
        print(f'\nInternal transactions in this page: {len(internal)}')

        gas = await client.get_gas_oracle()
        print(
            '\nGas (gwei): '
            f'safe {gas.get("SafeGasPrice")}, '
            f'propose {gas.get("ProposeGasPrice")}, '
            f'fast {gas.get("FastGasPrice")}'
        )

        price = await client.get_eth_price()
        print(f'ETH price: ${price.get("ethusd")} ({price.get("ethbtc")} BTC)')

        supply = await client.get_eth_supply()
        print(f'ETH supply: {wei_to_ether(supply):,.0f} ETH')

        abi = json.loads(await client.get_contract_abi(USDC))
        functions = [entry['name'] for entry in abi if entry.get('type') == 'function']
        print(f'\nUSDC ABI: {len(abi)} entries, {len(functions)} functions')
        print(f'  first five: {", ".join(functions[:5])}')

        # Token holder endpoints are Etherscan PRO; supply is not.
        supply_raw = await client.get_token_supply(USDC)
        print(f'USDC supply: {to_decimal_amount(supply_raw, decimals=6):,.2f} USDC')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else VITALIK))
