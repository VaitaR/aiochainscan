"""Utility base classes for scanners that follow the legacy Etherscan schema."""

from __future__ import annotations

from typing import Any

from ..constants import (
    API_MAX_CONTRACT_CREATION_ADDRESSES,
    API_MAX_OFFSET_ETHERSCAN,
    API_MAX_TOP_HOLDERS,
)
from ..core.endpoint import EndpointSpec, etherscan_parser
from ..domain.method import Method
from ..exceptions import InputLimitExceededError
from .base import Scanner


class EtherscanLikeScanner(Scanner):
    """Common implementation for scanners that expose the classic Etherscan layout."""

    auth_mode = 'query'
    auth_field = 'apikey'

    # page/offset REST: ``page * offset`` is bounded, so a block range holding
    # more than this many matching records is truncated without any error.
    # Confirmed live on BlockScout V1 (2026-09-02): ``page=11&offset=1000`` and
    # ``page=2&offset=10000`` both answer status 0 "Result window is too large,
    # PageNo x Offset size must be less than or equal to 10000", while an
    # over-cap ``offset=10001`` is silently clamped to 10000 items — the cap is
    # real and it truncates without an error at exactly this window.
    result_window = API_MAX_OFFSET_ETHERSCAN

    # The page/offset dialect is uniform: every cursor this family emits is
    # exactly ``{'page': next, 'offset': size}`` (see ``fetch_page``). Declared
    # once here so the MCP cursor whitelist derives it instead of hand-copying
    # the key names (base ``Scanner.cursor_keys`` default is empty).
    cursor_keys = frozenset({'page', 'offset'})

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
        (``len(items) < offset``), when ``offset`` is missing from ``params``,
        or when this method's spec cannot carry the cursor on the wire (see
        :meth:`_spec_pages_by_offset`). This mirrors the classic stop
        condition exactly.

        Args:
            method: Logical method to execute
            params: Parameters for the method; must include ``offset`` (page
                size) and, for pages after the first, the merged cursor

        Returns:
            Tuple of (items, next_cursor)
        """
        offset = params.get('offset')
        if (
            isinstance(offset, int)
            and self.max_page_size is not None
            and offset > self.max_page_size
        ):
            # The provider would serve max_page_size items and say status=1, and
            # that short page would read as "no more data" three lines below —
            # silently dropping the rest of the range. Ask for what it serves.
            offset = self.max_page_size
            params = {**params, 'offset': offset}

        result = await self.call(method, **params)
        items = self._coerce_items(result)

        if not items or not isinstance(offset, int) or len(items) < offset:
            return items, None
        if not self._spec_pages_by_offset(method):
            return items, None

        page = params.get('page', 1)
        return items, {'page': page + 1, 'offset': offset}

    def _spec_pages_by_offset(self, method: Method) -> bool:
        """Whether this method's spec maps ``page``/``offset`` onto the wire.

        A spec that maps neither has exactly ONE page: the params would be
        dropped before the request, so every "next page" is byte-for-byte the
        first one. Advancing the cursor there does not paginate, it repeats —
        BlockScout V1's ``getLogs`` ignores page/offset and answers at most
        1000 logs with ``status=1``, which made an unguaranteed ``get_all_logs``
        re-fetch the same page forever (verified live 2026-09-02).
        """
        spec = self.SPECS.get(method)
        if spec is None:
            return False
        return 'page' in spec.param_map or 'offset' in spec.param_map

    async def _perform_raw_request(
        self,
        spec: EndpointSpec,
        method: Method,
        params: dict[str, Any],
    ) -> Any:
        """Refuse doc-declared oversized inputs before the request is built.

        Keyed on the logical ``Method`` (this seam receives it, unlike
        ``_build_request``) rather than a ``spec.query['action']`` string
        match. The two calls with a documented ceiling of this shape:
        ``CONTRACT_CREATION`` (up to 5 addresses) and ``TOKEN_TOP_HOLDERS``
        (``offset`` up to 1000 — declared only by ``EtherscanV2``, but the
        check lives here regardless since it is keyed on the method, not on
        which subclass owns the spec). See
        ``constants.API_MAX_CONTRACT_CREATION_ADDRESSES`` /
        ``API_MAX_TOP_HOLDERS`` for the doc citations (dated 2026-09-02, NOT
        live-verified).

        Overriding this seam rather than ``call`` or ``_build_request`` means
        the check also covers ``BlockScoutV1``: its ``_perform_request``
        override still calls ``super()._perform_request(...)`` for every
        method it does not route through JSON-RPC, which reaches
        ``Scanner._perform_request`` -> ``self._perform_raw_request(...)`` ->
        this override, via MRO — no forbidden file touched.
        """
        if method is Method.CONTRACT_CREATION:
            addresses = params.get('contract_addresses')
            if addresses is not None:
                count = (
                    len([a for a in addresses.split(',') if a])
                    if isinstance(addresses, str)
                    else len(addresses)
                )
                if count > API_MAX_CONTRACT_CREATION_ADDRESSES:
                    raise InputLimitExceededError(
                        'contract addresses', API_MAX_CONTRACT_CREATION_ADDRESSES, count
                    )
        elif method is Method.TOKEN_TOP_HOLDERS:
            offset = params.get('offset')
            if isinstance(offset, int) and offset > API_MAX_TOP_HOLDERS:
                raise InputLimitExceededError('top holders', API_MAX_TOP_HOLDERS, offset)
        return await super()._perform_raw_request(spec, method, params)

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
                # Topic-pair operators (and/or between adjacent topics) —
                # emitted by ``iter_logs(topic_operators=...)``.
                'topic0_1_opr': 'topic0_1_opr',
                'topic1_2_opr': 'topic1_2_opr',
                'topic2_3_opr': 'topic2_3_opr',
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
        # Wire param spellings realigned to the documented body params at
        # https://docs.etherscan.io/api-reference/endpoint/verifysourcecode
        # (fetched 2026-09-02): ``constructorArguments`` (not the historical
        # ``constructorArguements`` typo) and ``evmVersion`` (not lowercase
        # ``evmversion``), plus the newly-added ``licenseType``. This was NOT
        # live-verified — that needs a real contract-verification POST, an
        # outward-facing side effect this change did not perform. No
        # in-repo or web evidence was found either way on whether Etherscan
        # still accepts the legacy ``constructorArguements`` spelling; the
        # docs page names only the current spelling, which is what is sent.
        # ``libraryname``/``libraryaddress`` are not listed on the current
        # docs page (checked 2026-09-02) but that is inconclusive on whether
        # the live API still accepts them, so they are KEPT per the
        # "unverified stays, drop only with evidence of removal" rule — an
        # extra ignored param is not a regression, but dropping a working one
        # would be.
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
                'constructor_arguments': 'constructorArguments',
                'evm_version': 'evmVersion',
                'license_type': 'licenseType',
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
