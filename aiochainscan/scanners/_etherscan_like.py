"""Utility base classes for scanners that follow the legacy Etherscan schema."""

from __future__ import annotations

from typing import Any

from ..constants import API_MAX_OFFSET_ETHERSCAN
from ..core.endpoint import EndpointSpec, etherscan_parser
from ..core.method import Method
from .base import Scanner


class EtherscanLikeScanner(Scanner):
    """Common implementation for scanners that expose the classic Etherscan layout."""

    auth_mode = 'query'
    auth_field = 'apikey'

    # page/offset REST: ``page * offset`` is bounded, so a block range holding
    # more than this many matching records is truncated without any error.
    # Verified in-repo for Etherscan only (``constants.py`` documents the
    # ``page * offset <= 10_000`` rule); BlockScout V1 inherits it because
    # assuming a cap that may not exist only costs extra requests, while
    # missing a real one loses data.
    result_window = API_MAX_OFFSET_ETHERSCAN

    async def fetch_page(
        self,
        method: Method,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        Fetch one page using Etherscan page/offset pagination.

        The cursor encodes the next ``page``/``offset`` pair and is merged
        back into ``params`` by the caller (base cursor contract). It is
        ``None`` once no full page can remain: an empty page, a partial page
        (``len(items) < offset``), or when ``offset`` is missing from
        ``params``. This mirrors the classic stop condition exactly.

        Args:
            method: Logical method to execute
            params: Parameters for the method; must include ``offset`` (page
                size) and, for pages after the first, the merged cursor

        Returns:
            Tuple of (items, next_cursor)
        """
        result = await self.call(method, **params)
        items = self._coerce_items(result)

        offset = params.get('offset')
        if not items or not isinstance(offset, int) or len(items) < offset:
            return items, None

        page = params.get('page', 1)
        return items, {'page': page + 1, 'offset': offset}

    SPECS = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account', 'action': 'balance', 'tag': 'latest'},
            param_map={'address': 'address', 'tag': 'tag'},
            parser=etherscan_parser,
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
            parser=etherscan_parser,
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
            parser=etherscan_parser,
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
            parser=etherscan_parser,
        ),
        Method.ACCOUNT_ERC721_TRANSFERS: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account', 'action': 'tokennfttx'},
            param_map={
                'address': 'address',
                'contract_address': 'contractaddress',
                'start_block': 'startblock',
                'end_block': 'endblock',
                'page': 'page',
                'offset': 'offset',
                'sort': 'sort',
            },
            parser=etherscan_parser,
        ),
        Method.ACCOUNT_ERC1155_TRANSFERS: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account', 'action': 'token1155tx'},
            param_map={
                'address': 'address',
                'contract_address': 'contractaddress',
                'start_block': 'startblock',
                'end_block': 'endblock',
                'page': 'page',
                'offset': 'offset',
                'sort': 'sort',
            },
            parser=etherscan_parser,
        ),
        Method.TX_BY_HASH: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'proxy', 'action': 'eth_getTransactionByHash'},
            param_map={'txhash': 'txhash'},
            parser=etherscan_parser,
        ),
        Method.TX_RECEIPT_STATUS: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'transaction', 'action': 'gettxreceiptstatus'},
            param_map={'txhash': 'txhash'},
            parser=etherscan_parser,
        ),
        Method.TX_STATUS_CHECK: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'transaction', 'action': 'getstatus'},
            param_map={'txhash': 'txhash'},
            parser=etherscan_parser,
        ),
        Method.BLOCK_BY_NUMBER: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'proxy', 'action': 'eth_getBlockByNumber', 'boolean': 'true'},
            param_map={'block_number': 'tag'},
            parser=etherscan_parser,
        ),
        Method.BLOCK_REWARD: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'block', 'action': 'getblockreward'},
            param_map={'block_number': 'blockno'},
            parser=etherscan_parser,
        ),
        Method.BLOCK_COUNTDOWN: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'block', 'action': 'getblockcountdown'},
            param_map={'block_number': 'blockno'},
            parser=etherscan_parser,
        ),
        Method.BLOCK_NUMBER_BY_TIMESTAMP: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'block', 'action': 'getblocknobytime'},
            param_map={'timestamp': 'timestamp', 'closest': 'closest'},
            parser=etherscan_parser,
        ),
        Method.CONTRACT_ABI: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'contract', 'action': 'getabi'},
            param_map={'address': 'address'},
            parser=etherscan_parser,
        ),
        Method.CONTRACT_SOURCE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'contract', 'action': 'getsourcecode'},
            param_map={'address': 'address'},
            parser=etherscan_parser,
        ),
        Method.CONTRACT_CREATION: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'contract', 'action': 'getcontractcreation'},
            param_map={'contract_addresses': 'contractaddresses'},
            parser=etherscan_parser,
        ),
        Method.TOKEN_BALANCE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account', 'action': 'tokenbalance'},
            param_map={'contract_address': 'contractaddress', 'address': 'address', 'tag': 'tag'},
            parser=etherscan_parser,
        ),
        Method.TOKEN_SUPPLY: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'stats', 'action': 'tokensupply'},
            param_map={'contract_address': 'contractaddress'},
            parser=etherscan_parser,
        ),
        Method.TOKEN_INFO: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'token', 'action': 'tokeninfo'},
            param_map={'contract_address': 'contractaddress'},
            parser=etherscan_parser,
        ),
        Method.GAS_ESTIMATE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'gastracker', 'action': 'gasestimate'},
            param_map={'gas_price': 'gasprice'},
            parser=etherscan_parser,
        ),
        Method.GAS_ORACLE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'gastracker', 'action': 'gasoracle'},
            parser=etherscan_parser,
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
            parser=etherscan_parser,
        ),
        Method.ETH_SUPPLY: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'stats', 'action': 'ethsupply'},
            parser=etherscan_parser,
        ),
        Method.ETH_PRICE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'stats', 'action': 'ethprice'},
            parser=etherscan_parser,
        ),
        Method.PROXY_ETH_CALL: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'proxy', 'action': 'eth_call'},
            param_map={'to': 'to', 'data': 'data', 'tag': 'tag'},
            parser=etherscan_parser,
        ),
        Method.PROXY_GET_BALANCE: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'proxy', 'action': 'eth_getBalance'},
            param_map={'address': 'address', 'tag': 'tag'},
            parser=etherscan_parser,
        ),
        Method.ACCOUNT_TOKEN_PORTFOLIO: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account', 'action': 'addresstokenbalance'},
            param_map={
                'address': 'address',
                'page': 'page',
                'offset': 'offset',
            },
            parser=etherscan_parser,
        ),
        Method.ACCOUNT_NFT_PORTFOLIO: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'account', 'action': 'addresstokennftinventory'},
            param_map={
                'address': 'address',
                'page': 'page',
                'offset': 'offset',
            },
            parser=etherscan_parser,
        ),
        Method.CONTRACT_VERIFY: EndpointSpec(
            http_method='POST',
            path='/api',
            query={'module': 'contract', 'action': 'verifysourcecode'},
            param_map={
                'contract_address': 'contractaddress',
                'source_code': 'sourceCode',
                'code_format': 'codeformat',
                'contract_name': 'contractname',
                'compiler_version': 'compilerversion',
                'optimization_used': 'optimizationUsed',
                'runs': 'runs',
                'constructor_arguments': 'constructorArguements',
                'evm_version': 'evmversion',
                'library_name': 'libraryname',
                'library_address': 'libraryaddress',
            },
            parser=etherscan_parser,
        ),
        Method.CONTRACT_VERIFY_STATUS: EndpointSpec(
            http_method='GET',
            path='/api',
            query={'module': 'contract', 'action': 'checkverifystatus'},
            param_map={'guid': 'guid'},
            parser=etherscan_parser,
        ),
    }
