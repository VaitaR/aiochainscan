"""
Etherscan API v2 scanner implementation for multichain support.
"""

from ..core.endpoint import PARSERS, EndpointSpec
from ..core.method import Method
from . import register_scanner
from .base import Scanner


@register_scanner
class EtherscanV2(Scanner):
    """
    Etherscan API v2 implementation with multichain support.

    Supports multiple networks through different subdomains and improved
    endpoint structure compared to v1.
    """

    name = 'etherscan'
    version = 'v2'
    supported_networks = {
        'main',  # Ethereum mainnet (legacy alias)
        'ethereum',
        'goerli',
        'sepolia',
        'holesky',
        'bsc',
        'polygon',
        'arbitrum',
        'optimism',
        'base',
    }
    auth_mode = 'query'
    auth_field = 'apikey'

    SPECS = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={
                'module': 'account',
                'action': 'balance',
                'tag': 'latest',
                'chainid': '{chain_id}',
            },
            param_map={'address': 'address'},
            parser=PARSERS['etherscan'],
        ),
        Method.ACCOUNT_TRANSACTIONS: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account', 'action': 'txlist', 'chainid': '{chain_id}'},
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
            query={'module': 'account', 'action': 'txlistinternal', 'chainid': '{chain_id}'},
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
            query={
                'module': 'proxy',
                'action': 'eth_getTransactionByHash',
                'chainid': '{chain_id}',
            },
            param_map={'txhash': 'txhash'},
            parser=PARSERS['etherscan'],
        ),
        Method.BLOCK_BY_NUMBER: EndpointSpec(
            http_method='GET',
            path='/api',
            query={
                'module': 'proxy',
                'action': 'eth_getBlockByNumber',
                'boolean': 'true',
                'chainid': '{chain_id}',
            },
            param_map={'block_number': 'tag'},
            parser=PARSERS['etherscan'],
        ),
        Method.CONTRACT_ABI: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'contract', 'action': 'getabi', 'chainid': '{chain_id}'},
            param_map={'address': 'address'},
            parser=PARSERS['etherscan'],
        ),
        Method.GAS_ORACLE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'gastracker', 'action': 'gasoracle', 'chainid': '{chain_id}'},
            parser=PARSERS['etherscan'],
        ),
    }
