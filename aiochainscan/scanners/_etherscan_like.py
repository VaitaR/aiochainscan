"""Utility base classes for scanners that follow the legacy Etherscan schema."""

from __future__ import annotations

from ..core.endpoint import PARSERS, EndpointSpec
from ..core.method import Method
from .base import Scanner


class EtherscanLikeScanner(Scanner):
    """Common implementation for scanners that expose the classic Etherscan layout."""

    auth_mode = 'query'
    auth_field = 'apikey'

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
        Method.ACCOUNT_ERC20_TRANSFERS: EndpointSpec(
            http_method='GET',
            path='/api',
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
            path='/api',
            query={'module': 'proxy', 'action': 'eth_getTransactionByHash'},
            param_map={'txhash': 'txhash'},
            parser=PARSERS['etherscan'],
        ),
        Method.TX_RECEIPT_STATUS: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'transaction', 'action': 'gettxreceiptstatus'},
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
        Method.BLOCK_REWARD: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'block', 'action': 'getblockreward'},
            param_map={'block_number': 'blockno'},
            parser=PARSERS['etherscan'],
        ),
        Method.CONTRACT_ABI: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'contract', 'action': 'getabi'},
            param_map={'address': 'address'},
            parser=PARSERS['etherscan'],
        ),
        Method.CONTRACT_SOURCE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'contract', 'action': 'getsourcecode'},
            param_map={'address': 'address'},
            parser=PARSERS['etherscan'],
        ),
        Method.TOKEN_BALANCE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account', 'action': 'tokenbalance'},
            param_map={'contract_address': 'contractaddress', 'address': 'address', 'tag': 'tag'},
            parser=PARSERS['etherscan'],
        ),
        Method.TOKEN_SUPPLY: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'stats', 'action': 'tokensupply'},
            param_map={'contract_address': 'contractaddress'},
            parser=PARSERS['etherscan'],
        ),
        Method.GAS_ORACLE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'gastracker', 'action': 'gasoracle'},
            parser=PARSERS['etherscan'],
        ),
        Method.EVENT_LOGS: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'logs', 'action': 'getLogs'},
            param_map={
                'address': 'address',
                'from_block': 'fromBlock',
                'to_block': 'toBlock',
                'topic0': 'topic0',
                'topic1': 'topic1',
                'topic2': 'topic2',
                'topic3': 'topic3',
            },
            parser=PARSERS['etherscan'],
        ),
        Method.ETH_SUPPLY: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'stats', 'action': 'ethsupply'},
            parser=PARSERS['etherscan'],
        ),
        Method.ETH_PRICE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'stats', 'action': 'ethprice'},
            parser=PARSERS['etherscan'],
        ),
        Method.PROXY_ETH_CALL: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'proxy', 'action': 'eth_call'},
            param_map={'to': 'to', 'data': 'data', 'tag': 'tag'},
            parser=PARSERS['etherscan'],
        ),
    }

