#!/usr/bin/env python3
"""Compare several addresses concurrently.

Self-contained — needs nothing but the published package:

    pip install aiochainscan
    python 03_multi_wallet_analysis.py [address ...]

One client serves every address: it holds the connection pool and the rate
limiter, so concurrent calls through it are throttled as one stream instead of
racing each other into a 429.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from decimal import Decimal

from aiochainscan import ChainscanClient, to_decimal_amount, wei_to_ether

WALLETS = (
    '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',  # vitalik.eth
    '0x28C6c06298d514Db089934071355E5743bf21d60',  # Binance 14
    '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',  # Uniswap V2 router
)


@dataclass(frozen=True)
class Holding:
    symbol: str
    amount: Decimal


@dataclass(frozen=True)
class WalletSummary:
    address: str
    ether: Decimal
    token_count: int
    top_holdings: tuple[Holding, ...]


async def summarize(client: ChainscanClient, address: str) -> WalletSummary:
    balance, portfolio = await asyncio.gather(
        client.get_balance(address),
        client.get_token_portfolio(address),
    )

    holdings: list[Holding] = []
    for item in portfolio:
        token = item.get('token', {})
        decimals = int(token.get('decimals') or 18)
        holdings.append(
            Holding(
                symbol=token.get('symbol') or '???',
                amount=to_decimal_amount(item.get('value', '0'), decimals=decimals),
            )
        )
    holdings.sort(key=lambda holding: holding.amount, reverse=True)

    return WalletSummary(
        address=address,
        ether=wei_to_ether(balance),
        token_count=len(holdings),
        top_holdings=tuple(holdings[:3]),
    )


async def main(addresses: tuple[str, ...]) -> None:
    async with ChainscanClient.from_config('blockscout_v2', 'ethereum') as client:
        summaries = await asyncio.gather(
            *(summarize(client, address) for address in addresses),
            return_exceptions=True,
        )

    for address, summary in zip(addresses, summaries, strict=True):
        if isinstance(summary, BaseException):
            print(f'{address}: failed — {type(summary).__name__}: {summary}')
            continue
        print(f'\n{summary.address}')
        print(f'  balance : {summary.ether:,.6f} ETH')
        print(f'  tokens  : {summary.token_count}')
        for holding in summary.top_holdings:
            print(f'    {holding.symbol:<12} {holding.amount:>24,.4f}')

    ranked = [s for s in summaries if isinstance(s, WalletSummary)]
    if ranked:
        richest = max(ranked, key=lambda summary: summary.ether)
        total = sum((summary.ether for summary in ranked), start=Decimal(0))
        print(f'\nTotal across {len(ranked)} addresses: {total:,.6f} ETH')
        print(f'Largest balance: {richest.address} ({richest.ether:,.6f} ETH)')


if __name__ == '__main__':
    asyncio.run(main(tuple(sys.argv[1:]) or WALLETS))
