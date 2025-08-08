#!/usr/bin/env python3
import asyncio

from aiochainscan import get_balance, get_token_balance, open_default_session


async def main() -> None:
    session = await open_default_session()
    try:
        balance_wei = await get_balance(
            address='0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3',
            api_kind='eth',
            network='main',
            api_key='YOUR_API_KEY',
            http=session.http,
            endpoint_builder=session.endpoint,
            telemetry=session.telemetry,
        )
        usdt_balance_wei = await get_token_balance(
            holder='0x742d35Cc6634C0532925a3b8D9fa7a3D91D1e9b3',
            token_contract='0xdAC17F958D2ee523a2206206994597C13D831ec7',
            api_kind='eth',
            network='main',
            api_key='YOUR_API_KEY',
            http=session.http,
            endpoint_builder=session.endpoint,
            telemetry=session.telemetry,
        )
        print(balance_wei, usdt_balance_wei)
    finally:
        await session.aclose()


if __name__ == '__main__':
    asyncio.run(main())
