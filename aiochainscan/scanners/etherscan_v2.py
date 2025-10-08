"""
Etherscan API v2 scanner implementation for multichain support.
"""

from typing import TYPE_CHECKING, Any

from ..core.endpoint import PARSERS, EndpointSpec
from ..core.method import Method
from . import register_scanner
from .base import Scanner

if TYPE_CHECKING:
    pass


@register_scanner
class EtherscanV2(Scanner):
    """
    Etherscan API v2 implementation with multichain support.

    Supports multiple networks through a unified endpoint and improved
    endpoint structure compared to v1.

    Key features of V2 API:
    - Single API key works across all 50+ supported chains
    - Uses chainid parameter in URL to specify the blockchain
    - Query parameter authentication (apikey=YOUR_KEY)
    - Unified endpoint: https://api.etherscan.io/v2/api

    Example from official docs:
        https://api.etherscan.io/v2/api?chainid=1&module=account&action=balance&apikey=KEY

    References:
        - V2 API Docs: https://docs.etherscan.io/
        - Migration Guide: https://docs.etherscan.io/v2-migration
    """

    name = 'etherscan'
    version = 'v2'
    supported_networks = {
        'main',
        'goerli',
        'sepolia',
        'holesky',
        'bsc',
        'polygon',
        'arbitrum',
        'optimism',
        'base',
    }
    # V2 API still uses query parameter authentication (not header)
    auth_mode = 'query'
    auth_field = 'apikey'

    def _build_request(self, spec: EndpointSpec, **params: Any) -> dict[str, Any]:
        """
        Override to add chainid parameter for Etherscan V2 API.

        Etherscan V2 requires chainid in query string:
        https://api.etherscan.io/v2/api?chainid=1&module=account&action=balance...
        """
        # Get base request from parent
        request_data = super()._build_request(spec, **params)

        # Add chainid parameter to query
        if spec.http_method == 'GET' and 'params' in request_data:
            request_data['params']['chainid'] = str(self.chain_info.chain_id)
        elif spec.http_method == 'POST' and 'data' in request_data:
            request_data['data']['chainid'] = str(self.chain_info.chain_id)

        return request_data

    async def call(self, method: 'Method', **params: Any) -> Any:
        """
        Execute a method call using Etherscan V2 API.

        Uses direct HTTP calls with the V2 endpoint:
        https://api.etherscan.io/v2/api
        """

        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise ValueError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )

        spec = self.SPECS[method]
        request_data = self._build_request(spec, **params)

        # Build Etherscan V2 URL
        base_url = 'https://api.etherscan.io/v2'
        full_url = base_url + spec.path

        # Use aiohttp directly for V2 API
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
            raise Exception(
                f'Etherscan V2 API error for chain {self.chain_info.chain_id}: {e}'
            ) from e

    SPECS = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account', 'action': 'balance', 'tag': 'latest'},
            param_map={'address': 'address'},
            parser=PARSERS['etherscan'],
        ),
        Method.ACCOUNT_TRANSACTIONS: EndpointSpec(
            http_method='GET',
            path='/api',
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
            path='/api',
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
        Method.TX_BY_HASH: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'proxy', 'action': 'eth_getTransactionByHash'},
            param_map={'txhash': 'txhash'},
            parser=PARSERS['etherscan'],
        ),
        Method.BLOCK_BY_NUMBER: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'proxy', 'action': 'eth_getBlockByNumber', 'boolean': 'true'},
            param_map={'block_number': 'tag'},
            parser=PARSERS['etherscan'],
        ),
        Method.CONTRACT_ABI: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'contract', 'action': 'getabi'},
            param_map={'address': 'address'},
            parser=PARSERS['etherscan'],
        ),
        Method.GAS_ORACLE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'gastracker', 'action': 'gasoracle'},
            parser=PARSERS['etherscan'],
        ),
    }
