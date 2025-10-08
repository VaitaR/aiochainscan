"""
Moralis Web3 Data API v1 scanner implementation.
"""

from typing import TYPE_CHECKING, Any

import aiohttp

from ..core.endpoint import PARSERS, EndpointSpec
from ..core.method import Method
from ..url_builder import UrlBuilder
from . import register_scanner
from .base import Scanner

if TYPE_CHECKING:
    from ..chains import ChainInfo


@register_scanner
class MoralisV1(Scanner):
    """
    Moralis Web3 Data API v1 implementation.

    Uses Moralis deep-index API with RESTful endpoints and header authentication.
    Supports multiple EVM chains with unified interface.
    """

    name = 'moralis'
    version = 'v1'
    supported_networks = {'eth', 'bsc', 'polygon', 'arbitrum', 'base', 'optimism', 'avalanche'}
    auth_mode = 'header'
    auth_field = 'X-API-Key'

    def _validate_chain_support(self, chain_info: 'ChainInfo') -> None:
        """Validate that Moralis supports this chain."""
        if not chain_info.moralis_chain_id:
            from ..chains import list_chains

            available = [c.name for c in list_chains(provider='moralis')]
            raise ValueError(
                f"Chain '{chain_info.display_name}' (ID: {chain_info.chain_id}) "
                f'is not supported by Moralis. '
                f'Available chains: {", ".join(available)}'
            )

    def __init__(self, api_key: str, chain_info: 'ChainInfo', url_builder: UrlBuilder) -> None:
        """
        Initialize Moralis scanner with chain-specific configuration.

        Args:
            api_key: Moralis API key (required)
            chain_info: ChainInfo object with chain metadata
            url_builder: UrlBuilder instance (not used for Moralis)
        """
        super().__init__(api_key, chain_info, url_builder)

        # Get Moralis chain ID from chain_info
        self.moralis_chain_id = chain_info.moralis_chain_id
        if not self.moralis_chain_id:
            raise ValueError(
                f"Chain '{chain_info.display_name}' does not have Moralis support configured"
            )

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

        # Substitute chain ID in query
        if 'chain' in query_params and query_params['chain'] == '{chain_id}':
            query_params['chain'] = self.moralis_chain_id

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
            raise Exception(f'Moralis API error for chain {self.moralis_chain_id}: {e}') from e

    def __str__(self) -> str:
        """String representation including chain info."""
        return f'Moralis v{self.version} ({self.chain_info.display_name}, chain_id={self.moralis_chain_id})'

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"MoralisV1(chain_name='{self.chain_info.name}', "
            f'chain_id={self.chain_info.chain_id}, '
            f"moralis_chain_id='{self.moralis_chain_id}', "
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
