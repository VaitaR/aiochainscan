from asyncio import AbstractEventLoop
from contextlib import AbstractAsyncContextManager

from aiohttp import ClientTimeout
from aiohttp_retry import RetryOptionsBase

from aiochainscan.modules.account import Account
from aiochainscan.modules.block import Block
from aiochainscan.modules.contract import Contract
from aiochainscan.modules.extra.links import LinkHelper
from aiochainscan.modules.extra.utils import Utils
from aiochainscan.modules.gas_tracker import GasTracker
from aiochainscan.modules.logs import Logs
from aiochainscan.modules.proxy import Proxy
from aiochainscan.modules.stats import Stats
from aiochainscan.modules.token import Token
from aiochainscan.modules.transaction import Transaction
from aiochainscan.network import Network, UrlBuilder


class Client:
    def __init__(
        self,
        api_key: str = '',
        api_kind: str = 'eth',
        network: str = 'main',
        loop: AbstractEventLoop = None,
        timeout: ClientTimeout = None,
        proxy: str = None,
        throttler: AbstractAsyncContextManager = None,
        retry_options: RetryOptionsBase = None,
    ) -> None:
        self._url_builder = UrlBuilder(api_key, api_kind, network)
        self._http = Network(self._url_builder, loop, timeout, proxy, throttler, retry_options)

        self.account = Account(self)
        self.block = Block(self)
        self.contract = Contract(self)
        self.transaction = Transaction(self)
        self.stats = Stats(self)
        self.logs = Logs(self)
        self.proxy = Proxy(self)
        self.token = Token(self)
        self.gas_tracker = GasTracker(self)

        self.utils = Utils(self)
        self.links = LinkHelper(self._url_builder)

    @property
    def currency(self) -> str:
        return self._url_builder.currency

    async def close(self):
        await self._http.close()
