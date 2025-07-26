from __future__ import annotations

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
        'base': ('basescan.org', 'BASE'),
        'xlayer': ('oklink.com/api/v5/explorer/xlayer', 'XL'),
    }

    BASE_URL: str = None
    API_URL: str = None

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
        default_prefix = 'api' if self._is_main else f'api-{self._network}'
        prefix = prefix_exceptions.get((self._api_kind, self._is_main), default_prefix)

        # scanners with other then api url start
        if self._api_kind == 'flare':
            prefix = 'flare-explorer'
        elif self._api_kind == 'chiliz':
            prefix = 'scan'
        elif self._api_kind == 'xlayer':
            prefix = None

        return self._build_url(prefix, 'api')

    def _get_base_url(self) -> str:
        network_exceptions = {('polygon', 'testnet'): 'mumbai'}
        network = network_exceptions.get((self._api_kind, self._network), self._network)

        prefix_exceptions = {
            ('optimism', True): 'optimistic',
            ('optimism', False): f'{network}-optimism',
        }
        default_prefix = None if self._is_main else network
        prefix = prefix_exceptions.get((self._api_kind, self._is_main), default_prefix)
        return self._build_url(prefix)

    def filter_and_sign(self, params: dict, headers: dict):
        params, headers = self._sign(self._filter_params(params or {}), headers or {})
        return params, headers

    def _sign(self, params: dict, headers: dict) -> dict:
        if not params:
            params = {}
        if not headers:
            headers = {}
        # for scanners that don't require API key or have free tier without
        if self._API_KEY != '' and self._api_kind != 'xlayer':  # not for oklink
            params['apikey'] = self._API_KEY

        if self._api_kind == 'xlayer':
            headers['OK-ACCESS-KEY'] = self._API_KEY
            headers['Content-Type'] = 'application/json'

        return params, headers

    @staticmethod
    def _filter_params(params: dict) -> dict:
        return {k: v for k, v in params.items() if v is not None}
