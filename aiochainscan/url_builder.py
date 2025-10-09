from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlunsplit


class UrlBuilder:
    _API_KINDS = {
        'eth': ('etherscan.io', 'ETH'),
        'bsc': ('bscscan.com', 'BNB'),
        'polygon': ('polygonscan.com', 'MATIC'),
        'optimism': ('etherscan.io', 'ETH'),
        'arbitrum': ('arbiscan.io', 'ETH'),
        'fantom': ('ftmscan.com', 'FTM'),
        'gnosis': ('gnosisscan.io', 'GNO'),
        'flare': ('flare.network', 'FLR'),
        'wemix': ('wemixscan.com', 'WEMIX'),
        'chiliz': ('chiliz.com', 'CHZ'),
        'mode': ('routescan.io/v2/network/mainnet/evm/34443/etherscan', 'MODE'),
        'linea': ('lineascan.build', 'LINEA'),
        'blast': ('blastscan.io', 'BLAST'),
        'base': ('etherscan.io', 'BASE'),  # Base network via Etherscan V2
        'routscan_mode': ('api.routescan.io/v2/network/mainnet/evm/34443', 'ETH'),
        'blockscout_eth': ('eth.blockscout.com', 'ETH'),
        'blockscout_sepolia': ('eth-sepolia.blockscout.com', 'ETH'),
        'blockscout_gnosis': ('gnosis.blockscout.com', 'xDAI'),
        'blockscout_polygon': ('polygon.blockscout.com', 'MATIC'),
        'moralis': ('deep-index.moralis.io', 'Multi-chain'),
    }

    # API kinds that use Etherscan V2 header-based authentication.
    # IMPORTANT: Only Etherscan-compatible V2 endpoints should be listed here.
    _HEADER_AUTH_API_KINDS = {'eth', 'optimism', 'arbitrum', 'bsc', 'polygon', 'base'}

    _CHAIN_ID_MAP = {
        ('eth', 'main'): '1',
        ('eth', 'goerli'): '5',
        ('eth', 'sepolia'): '11155111',
        ('eth', 'holesky'): '17000',
        ('eth', 'test'): '5',
        ('eth', 'ropsten'): '3',
        ('eth', 'rinkeby'): '4',
        ('eth', 'kovan'): '42',
        ('optimism', 'main'): '10',
        ('optimism', 'goerli'): '420',
        ('optimism', 'test'): '420',
        ('bsc', 'main'): '56',
        ('bsc', 'test'): '97',
        ('bsc', 'testnet'): '97',
        ('polygon', 'main'): '137',
        ('polygon', 'mumbai'): '80001',
        ('polygon', 'test'): '80001',
        ('polygon', 'testnet'): '80001',
        ('arbitrum', 'main'): '42161',
        ('arbitrum', 'nova'): '42170',
        ('arbitrum', 'goerli'): '421613',
        ('arbitrum', 'test'): '421613',
        ('base', 'main'): '8453',
        ('base', 'goerli'): '84531',
        ('base', 'sepolia'): '84532',
        ('linea', 'main'): '59144',
        ('linea', 'test'): '59140',
        ('gnosis', 'main'): '100',
        ('gnosis', 'chiado'): '10200',
        ('fantom', 'main'): '250',
        ('fantom', 'test'): '4002',
        ('fantom', 'testnet'): '4002',
        ('mode', 'main'): '34443',
        ('blast', 'main'): '81457',
        ('blast', 'sepolia'): '168587773',
    }

    BASE_URL: str
    API_URL: str

    def __init__(self, api_key: str, api_kind: str, network: str) -> None:
        self._API_KEY = api_key

        self._set_api_kind(api_kind)
        self._network = network.lower().strip()

        self.API_URL = self._get_api_url()
        self.BASE_URL = self._get_base_url()

    def _set_api_kind(self, api_kind: str) -> None:
        api_kind = api_kind.lower().strip()
        if api_kind not in self._API_KINDS:
            raise ValueError(
                f'Incorrect api_kind {api_kind!r}, supported only: {", ".join(self._API_KINDS)}'
            )
        else:
            self._api_kind = api_kind

    @property
    def _is_main(self) -> bool:
        return self._network == 'main'

    @property
    def _base_netloc(self) -> str:
        # Etherscan V2 API Migration: All V2 APIs (header auth) use etherscan.io domain
        # Reference: https://docs.etherscan.io/v2-migration
        if self._api_kind in self._HEADER_AUTH_API_KINDS:
            return 'etherscan.io'
        netloc, _ = self._API_KINDS[self._api_kind]
        return netloc

    @property
    def currency(self) -> str:
        _, currency = self._API_KINDS[self._api_kind]
        return currency

    def get_link(self, path: str) -> str:
        return urljoin(self.BASE_URL, path)

    def _build_url(self, prefix: str | None, path: str = '') -> str:
        netloc = self._base_netloc if prefix is None else f'{prefix}.{self._base_netloc}'
        return urlunsplit(('https', netloc, path, '', ''))

    def _get_api_url(self) -> str:
        prefix_exceptions = {
            ('optimism', True): 'api-optimistic',
            ('optimism', False): f'api-{self._network}-optimistic',
        }
        default_prefix: str = 'api' if self._is_main else f'api-{self._network}'
        prefix: str | None = prefix_exceptions.get((self._api_kind, self._is_main), default_prefix)

        # scanners with other then api url start
        if self._api_kind == 'flare':
            prefix = 'flare-explorer'
        elif self._api_kind == 'chiliz':
            prefix = 'scan'

        elif self._api_kind == 'routscan_mode':
            prefix = 'etherscan'
        elif self._api_kind.startswith('blockscout_'):
            prefix = None  # BlockScout uses direct /api path

        # Default path
        path = 'api'

        # Etherscan V2 header-auth APIs use unified domain api.etherscan.io
        # and fixed 'api' prefix regardless of network, with path 'v2/api'.
        if self._api_kind in self._HEADER_AUTH_API_KINDS:
            prefix = 'api'  # force unified api prefix
            path = 'v2/api'

        return self._build_url(prefix, path)

    def _get_base_url(self) -> str:
        network_exceptions = {('polygon', 'testnet'): 'mumbai'}
        network = network_exceptions.get((self._api_kind, self._network), self._network)

        prefix_exceptions = {
            ('optimism', True): 'optimistic',
            ('optimism', False): f'{network}-optimism',
        }
        # Blockscout instances use direct hostnames per network; no subdomain prefix.
        if self._api_kind.startswith('blockscout_'):
            default_prefix = None
        else:
            default_prefix = None if self._is_main else network
        prefix = prefix_exceptions.get((self._api_kind, self._is_main), default_prefix)
        return self._build_url(prefix)

    def filter_and_sign(
        self, params: dict[str, Any] | None, headers: dict[str, Any] | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        filtered_params = self._filter_params(dict(params or {}))
        filtered_headers = self._filter_headers(dict(headers or {}))

        params_with_chain = self._apply_chain_id(filtered_params)
        signed_params, signed_headers = self._apply_auth(params_with_chain, filtered_headers)
        return signed_params, signed_headers

    @staticmethod
    def _filter_params(params: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in params.items() if v is not None}

    @staticmethod
    def _filter_headers(headers: dict[str, Any]) -> dict[str, str]:
        return {str(k): str(v) for k, v in headers.items() if v is not None}

    def _apply_chain_id(self, params: dict[str, Any]) -> dict[str, Any]:
        if (self._api_kind, self._network) in self._CHAIN_ID_MAP:
            params.setdefault('chainid', self._CHAIN_ID_MAP[(self._api_kind, self._network)])
        return params

    def _apply_auth(
        self, params: dict[str, Any], headers: dict[str, str]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        if not self._API_KEY:
            return params, headers

        if self._api_kind in self._HEADER_AUTH_API_KINDS or self._api_kind == 'moralis':
            headers.setdefault('X-API-Key', self._API_KEY)
        else:
            params.setdefault('apikey', self._API_KEY)

        return params, headers

    # Legacy compatibility shim for code that still calls the old private helper.
    def _sign(
        self, params: dict[str, Any] | None, headers: dict[str, Any] | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.filter_and_sign(params, headers)
