from asyncio import AbstractEventLoop
from contextlib import AbstractAsyncContextManager
from typing import Any

from aiohttp import ClientTimeout
from aiohttp_retry import RetryOptionsBase

from aiochainscan.config import config as global_config
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
from aiochainscan.network import Network
from aiochainscan.url_builder import UrlBuilder


class Client:
    def __init__(
        self,
        api_key: str = '',
        api_kind: str = 'eth',
        network: str = 'main',
        loop: AbstractEventLoop | None = None,
        timeout: ClientTimeout | None = None,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager[Any] | None = None,
        retry_options: RetryOptionsBase | None = None,
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

    async def close(self) -> None:
        await self._http.close()

    @classmethod
    def from_config(
        cls,
        scanner: str,
        network: str = 'main',
        loop: AbstractEventLoop | None = None,
        timeout: ClientTimeout | None = None,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager[Any] | None = None,
        retry_options: RetryOptionsBase | None = None,
    ) -> 'Client':
        """
        Create a Client instance using the configuration system.

        Args:
            scanner: Scanner name (e.g., 'eth', 'bsc', 'polygon')
            network: Network name (e.g., 'main', 'test', 'goerli')
            loop: Event loop instance
            timeout: Request timeout configuration
            proxy: Proxy URL
            throttler: Rate limiting throttler
            retry_options: Retry configuration

        Returns:
            Configured Client instance

        Raises:
            ValueError: If scanner or network is not supported, or API key is missing

        Example:
            ```python
            # Create Ethereum mainnet client (requires ETHERSCAN_KEY env var)
            client = Client.from_config('eth', 'main')

            # Create BSC testnet client (requires BSCSCAN_KEY env var)
            client = Client.from_config('bsc', 'test')
            ```
        """
        client_config = global_config.create_client_config(scanner, network)

        return cls(
            api_key=client_config['api_key'],
            api_kind=client_config['api_kind'],
            network=client_config['network'],
            loop=loop,
            timeout=timeout,
            proxy=proxy,
            throttler=throttler,
            retry_options=retry_options,
        )

    @classmethod
    def get_supported_scanners(cls) -> list[str]:
        """Get list of all supported scanner names."""
        return global_config.get_supported_scanners()

    @classmethod
    def get_scanner_networks(cls, scanner: str) -> set[str]:
        """Get supported networks for a specific scanner."""
        return global_config.get_scanner_networks(scanner)

    @classmethod
    def list_configurations(cls) -> dict[str, dict[str, Any]]:
        """Get overview of all scanner configurations and their status."""
        return global_config.list_all_configurations()
