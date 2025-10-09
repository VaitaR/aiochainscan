"""
RoutScan API v1 scanner implementation.
"""

from typing import Any

from ..core.endpoint import PARSERS, EndpointSpec
from ..core.method import Method
from ..url_builder import UrlBuilder
from . import register_scanner
from .base import Scanner


@register_scanner
class RoutScanV1(Scanner):
    """
    RoutScan API v1 implementation.

    Uses the RoutScan explorer API with network-specific endpoints.
    Example: api.routescan.io/v2/network/mainnet/evm/34443/etherscan/api
    """

    name = 'routscan'
    version = 'v1'
    supported_networks = {'mode'}  # Mode network (chain ID 34443)
    auth_mode = 'query'
    auth_field = 'apikey'

    # Network to chain ID mapping for RoutScan
    NETWORK_CHAIN_IDS = {
        'mode': '34443',  # Mode network
    }

    def __init__(
        self, api_key: str, network: str, url_builder: UrlBuilder, chain_id: int | None = None
    ) -> None:
        """
        Initialize RoutScan scanner with network-specific chain ID.

        Args:
            api_key: API key (optional for RoutScan)
            network: Network name (must be in supported_networks)
            url_builder: UrlBuilder instance
            chain_id: Chain ID (optional, will be resolved from network)
        """
        super().__init__(api_key, network, url_builder, chain_id)

        # Get chain ID for this network
        chain_id_value = chain_id or self.NETWORK_CHAIN_IDS.get(network)
        if not chain_id_value:
            available = ', '.join(sorted(self.NETWORK_CHAIN_IDS.keys()))
            raise ValueError(
                f"Network '{network}' not mapped for RoutScan. Available: {available}"
            )
        if isinstance(chain_id_value, str):
            self.chain_id = int(chain_id_value)
        else:
            self.chain_id = chain_id_value

    async def call(self, method: Method, **params: Any) -> Any:
        """
        Override call to use proper RoutScan URL structure.

        RoutScan uses a specific URL pattern:
        https://api.routescan.io/v2/network/mainnet/evm/{chain_id}/etherscan/api
        """
        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise ValueError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )

        spec = self.SPECS[method]
        request_data = self._build_request(spec, **params)

        # Build the complete RoutScan URL manually
        base_url = f'https://api.routescan.io/v2/network/mainnet/evm/{self.chain_id}'
        full_url = base_url + spec.path

        # Use aiohttp directly for RoutScan requests
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                if spec.http_method == 'GET':
                    async with session.get(
                        full_url,
                        params=request_data.get('params'),
                        headers=request_data.get('headers', {}),
                    ) as response:
                        raw_response = await response.json()
                else:  # POST
                    async with session.post(
                        full_url,
                        json=request_data.get('data'),
                        headers=request_data.get('headers', {}),
                    ) as response:
                        raw_response = await response.json()

            return spec.parse_response(raw_response)

        except Exception as e:
            # Enhanced error reporting for RoutScan
            raise Exception(f'RoutScan API error for chain {self.chain_id}: {e}') from e

    def _build_request(self, spec: EndpointSpec, **params: Any) -> dict[str, Any]:
        """
        Override to handle RoutScan-specific request building.

        RoutScan API key is optional and goes in query parameters.
        """
        # Get base request data from parent
        request_data: dict[str, Any] = super()._build_request(spec, **params)

        # RoutScan works without API keys (remove empty apikey)
        if not self.api_key:
            if spec.http_method == 'GET' and 'params' in request_data:
                request_data['params'].pop('apikey', None)
            elif spec.http_method == 'POST' and 'data' in request_data:
                request_data['data'].pop('apikey', None)

        return request_data

    def __str__(self) -> str:
        """String representation including chain info."""
        return f'RoutScan v{self.version} (chain {self.chain_id})'

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"RoutScanV1(network='{self.network}', "
            f"chain_id='{self.chain_id}', "
            f'methods={len(self.SPECS)})'
        )

    SPECS = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method='GET',
            path='/etherscan/api',
            query={'module': 'account', 'action': 'balance', 'tag': 'latest'},
            param_map={'address': 'address'},
            parser=PARSERS['etherscan'],
        ),
        Method.ACCOUNT_TRANSACTIONS: EndpointSpec(
            http_method='GET',
            path='/etherscan/api',
            query={'module': 'account', 'action': 'txlist'},
            param_map={
                'address': 'address',
                'start_block': 'startblock',
                'end_block': 'endblock',
                'page': 'page',
                'offset': 'offset',
                'sort': 'sort',
            },
            parser=PARSERS['etherscan'],
        ),
        Method.ACCOUNT_INTERNAL_TXS: EndpointSpec(
            http_method='GET',
            path='/etherscan/api',
            query={'module': 'account', 'action': 'txlistinternal'},
            param_map={
                'address': 'address',
                'start_block': 'startblock',
                'end_block': 'endblock',
                'page': 'page',
                'offset': 'offset',
                'sort': 'sort',
            },
            parser=PARSERS['etherscan'],
        ),
        Method.ACCOUNT_ERC20_TRANSFERS: EndpointSpec(
            http_method='GET',
            path='/etherscan/api',
            query={'module': 'account', 'action': 'tokentx'},
            param_map={
                'address': 'address',
                'contract_address': 'contractaddress',
                'start_block': 'startblock',
                'end_block': 'endblock',
                'page': 'page',
                'offset': 'offset',
                'sort': 'sort',
            },
            parser=PARSERS['etherscan'],
        ),
        Method.TX_BY_HASH: EndpointSpec(
            http_method='GET',
            path='/etherscan/api',
            query={'module': 'proxy', 'action': 'eth_getTransactionByHash'},
            param_map={'txhash': 'txhash'},
            parser=PARSERS['etherscan'],
        ),
        Method.BLOCK_BY_NUMBER: EndpointSpec(
            http_method='GET',
            path='/etherscan/api',
            query={'module': 'proxy', 'action': 'eth_getBlockByNumber', 'boolean': 'true'},
            param_map={'block_number': 'tag'},
            parser=PARSERS['etherscan'],
        ),
        Method.CONTRACT_ABI: EndpointSpec(
            http_method='GET',
            path='/etherscan/api',
            query={'module': 'contract', 'action': 'getabi'},
            param_map={'address': 'address'},
            parser=PARSERS['etherscan'],
        ),
    }
