"""
Moralis Web3 Data API v1 scanner implementation.
"""

from typing import Any

import aiohttp

from ..core.endpoint import PARSERS, EndpointSpec
from ..core.method import Method
from ..url_builder import UrlBuilder
from . import register_scanner
from .base import Scanner

# Network to Moralis chain ID mapping
NETWORK_TO_CHAIN_ID = {
    'eth': '0x1',  # Ethereum Mainnet
    'bsc': '0x38',  # BSC Mainnet
    'polygon': '0x89',  # Polygon Mainnet
    'arbitrum': '0xa4b1',  # Arbitrum One
    'base': '0x2105',  # Base Mainnet
    'optimism': '0xa',  # Optimism Mainnet
    'avalanche': '0xa86a',  # Avalanche C-Chain
}


@register_scanner
class MoralisV1(Scanner):
    """
    Moralis Web3 Data API v1 implementation.

    Uses Moralis deep-index API with RESTful endpoints and header authentication.
    Supports multiple EVM chains with unified interface.
    """

    name = 'moralis'
    version = 'v1'
    supported_networks = set(NETWORK_TO_CHAIN_ID.keys())
    auth_mode = 'header'
    auth_field = 'X-API-Key'

    def __init__(
        self, api_key: str, network: str, url_builder: UrlBuilder, chain_id: int | None = None
    ) -> None:
        """
        Initialize Moralis scanner with network-specific chain ID.

        Args:
            api_key: Moralis API key (required)
            network: Network name (must be in supported_networks)
            url_builder: UrlBuilder instance (not used for Moralis)
            chain_id: Chain ID (optional, will be resolved from network)
        """
        super().__init__(api_key, network, url_builder, chain_id)

        # Get chain ID for this network
        chain_id_value = chain_id or NETWORK_TO_CHAIN_ID.get(network)
        if not chain_id_value:
            available = ', '.join(sorted(NETWORK_TO_CHAIN_ID.keys()))
            raise ValueError(f"Network '{network}' not mapped for Moralis. Available: {available}")
        if isinstance(chain_id_value, str):
            self.chain_id = int(chain_id_value)
        else:
            self.chain_id = chain_id_value

        self.base_url = 'https://deep-index.moralis.io/api/v2.2'

    async def call(self, method: Method, **params: Any) -> Any:
        """
        Override call to use Moralis API structure.

        Moralis uses RESTful endpoints with path parameters and chain ID in query.
        """
        if method not in self.SPECS:
            available = [str(m) for m in self.SPECS]
            raise ValueError(
                f'Method {method} not supported by {self.name} v{self.version}. '
                f'Available: {", ".join(available)}'
            )

        spec = self.SPECS[method]

        # Build URL with path parameter substitution
        url_path = spec.path
        query_params: dict[str, Any] = spec.query.copy()

        # Substitute chain ID in query (Moralis expects hex string)
        if 'chain' in query_params and query_params['chain'] == '{chain_id}':
            query_params['chain'] = f'0x{self.chain_id:x}'

        # Handle path parameter substitution for address, txhash, etc.
        for param_name, param_value in params.items():
            if param_value is not None:
                placeholder = f'{{{param_name}}}'
                if placeholder in url_path:
                    url_path = url_path.replace(placeholder, str(param_value))
                else:
                    # Add to query if not in path
                    mapped_param = spec.param_map.get(param_name, param_name)
                    query_params[mapped_param] = param_value

        full_url = self.base_url + url_path

        # Set up headers with authentication
        headers = {'Accept': 'application/json', 'X-API-Key': self.api_key}

        # Use aiohttp directly for Moralis requests
        try:
            async with aiohttp.ClientSession() as session:
                if spec.http_method == 'GET':
                    async with session.get(
                        full_url, params=query_params, headers=headers
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise Exception(f'Moralis API error {response.status}: {error_text}')
                        raw_response = await response.json()
                else:  # POST
                    async with session.post(
                        full_url, json=query_params, headers=headers
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise Exception(f'Moralis API error {response.status}: {error_text}')
                        raw_response = await response.json()

            return spec.parse_response(raw_response)

        except Exception as e:
            # Enhanced error reporting for Moralis
            raise Exception(f'Moralis API error for chain {self.chain_id}: {e}') from e

    def __str__(self) -> str:
        """String representation including chain info."""
        return f'Moralis v{self.version} (chain {self.chain_id})'

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"MoralisV1(network='{self.network}', "
            f"chain_id='{self.chain_id}', "
            f'methods={len(self.SPECS)})'
        )

    SPECS = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method='GET',
            path='/{address}/balance',
            query={'chain': '{chain_id}'},
            param_map={'address': 'address'},
            parser=PARSERS['moralis_balance'],
        ),
        Method.ACCOUNT_TRANSACTIONS: EndpointSpec(
            http_method='GET',
            path='/{address}',
            query={'chain': '{chain_id}', 'limit': '100'},
            param_map={'address': 'address', 'cursor': 'cursor', 'limit': 'limit'},
            parser=PARSERS['moralis_transactions'],
        ),
        Method.TOKEN_BALANCE: EndpointSpec(
            http_method='GET',
            path='/{address}/erc20',
            query={'chain': '{chain_id}'},
            param_map={'address': 'address', 'token_addresses': 'token_addresses'},
            parser=PARSERS['moralis_token_balances'],
        ),
        Method.ACCOUNT_ERC20_TRANSFERS: EndpointSpec(
            http_method='GET',
            path='/{address}/erc20/transfers',
            query={'chain': '{chain_id}', 'limit': '100'},
            param_map={'address': 'address', 'cursor': 'cursor', 'limit': 'limit'},
            parser=PARSERS['moralis_transactions'],
        ),
        Method.TX_BY_HASH: EndpointSpec(
            http_method='GET',
            path='/transaction/{txhash}',
            query={'chain': '{chain_id}'},
            param_map={'txhash': 'txhash'},
            parser=PARSERS['moralis_transaction'],
        ),
        Method.BLOCK_BY_NUMBER: EndpointSpec(
            http_method='GET',
            path='/block/{block_number}',
            query={'chain': '{chain_id}'},
            param_map={'block_number': 'block_number'},
            parser=PARSERS['moralis_transaction'],
        ),
        Method.CONTRACT_ABI: EndpointSpec(
            http_method='GET',
            path='/{address}/abi',
            query={'chain': '{chain_id}'},
            param_map={'address': 'address'},
            parser=PARSERS['raw'],
        ),
    }
