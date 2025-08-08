#!/usr/bin/env python3
import asyncio
from datetime import date, timedelta

from aiochainscan import (
    get_daily_transaction_count,
    get_logs,
    open_default_session,
)


async def main() -> None:
    session = await open_default_session()
    try:
        # Logs example
        logs = await get_logs(
            start_block=19000000,
            end_block=19000100,
            address='0x0000000000000000000000000000000000000000',
            api_kind='eth',
            network='main',
            api_key='YOUR_API_KEY',
            http=session.http,
            endpoint_builder=session.endpoint,
            telemetry=session.telemetry,
        )
        print(f'logs: {len(logs)}')

        # Stats daily series example
        end = date.today()
        start = end - timedelta(days=7)
        series = await get_daily_transaction_count(
            start_date=start,
            end_date=end,
            api_kind='eth',
            network='main',
            api_key='YOUR_API_KEY',
            http=session.http,
            endpoint_builder=session.endpoint,
            telemetry=session.telemetry,
        )
        print(f'series points: {len(series)}')
    finally:
        await session.aclose()


if __name__ == '__main__':
    asyncio.run(main())
