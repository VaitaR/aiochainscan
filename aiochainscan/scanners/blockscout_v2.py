"""
Blockscout REST API V2 scanner implementation.

Modern RESTful API with path parameters and rich JSON responses.
No API key required - public API.

Differences from V1 (Etherscan-compatible):
- Uses path parameters instead of query parameters
- Returns rich JSON objects directly (no status/message wrapper)
- Different response schemas with nested objects
- Pagination via next_page_params

Base URL example: https://eth.blockscout.com/api/v2/
"""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING, Any, ClassVar

from ..chain_registry import BLOCKSCOUT_INSTANCE_HOSTS, BLOCKSCOUT_SCANNER_NETWORKS
from ..core.endpoint import EndpointSpec
from ..core.url_builder import UrlBuilder
from ..domain.method import Method
from . import register_scanner
from .base import Scanner, holder_item, translate_unexpected_errors

if TYPE_CHECKING:
    from ..network import Network


# ============================================================================
# Response Parsers for Blockscout V2 API
# ============================================================================


def _parse_balance(response: dict[str, Any]) -> str:
    """
    Extract balance from V2 address response.

    Deliberately NOT shared with ``nodereal._parse_balance``: this one reads
    a dict envelope whose ``coin_balance`` is already a decimal Wei string,
    while NodeReal normalizes a bare ``eth_getBalance`` hex quantity.

    Response format:
    {
        "hash": "0x...",
        "coin_balance": "32122885900610537215",
        "ens_domain_name": "vitalik.eth",
        ...
    }
    """
    result = response.get('coin_balance', '0')
    return str(result) if result else '0'


def _parse_token_portfolio(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract token list from V2 tokens response.

    Response format:
    {
        "items": [
            {
                "token": {"address_hash": "0x...", "name": "USDC", ...},
                "value": "5878047570"
            },
            ...
        ],
        "next_page_params": {...}
    }
    """
    items = response.get('items')
    return list(items) if items else []


def _parse_transactions(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract transactions from V2 transactions response.

    Response format:
    {
        "items": [...],
        "next_page_params": {...}
    }
    """
    items = response.get('items')
    return list(items) if items else []


def _parse_contract_abi(response: dict[str, Any]) -> list[dict[str, Any]] | None:
    """
    Extract ABI from V2 smart contract response.

    Response format:
    {
        "abi": [...],
        "name": "ContractName",
        "is_verified": true,
        ...
    }
    """
    abi = response.get('abi')
    return list(abi) if abi else None


def _parse_raw(response: dict[str, Any]) -> dict[str, Any]:
    """Return raw response without transformation."""
    return response


def _normalize_token_holder_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Flatten one ``/tokens/{address}/holders`` entry to the unified shape.

    BlockScout nests the holder address inside an ``address`` object (with
    ``hash`` plus metadata); extraction unwraps it and ``base.holder_item``
    builds the unified item — checksummed ``address`` plus the raw-unit
    ``value`` string (Wei-like: never Int64).
    """
    holder = entry.get('address')
    address = holder.get('hash') if isinstance(holder, dict) else holder
    return holder_item(address, entry.get('value'))


def _parse_token_holders(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract token holders from the V2 holders response.

    Response format:
    {
        "items": [
            {"address": {"hash": "0x...", ...}, "token_id": null, "value": "123"},
            ...
        ],
        "next_page_params": {...}
    }
    """
    items = response.get('items')
    return [_normalize_token_holder_entry(entry) for entry in items] if items else []


def _parse_token_transfers(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract ERC-20 transfers from the V2 token-transfers response.

    Response format (``?type=ERC-20`` static filter applied — the endpoint is
    shared with ERC-721/ERC-1155 transfers, so without it the list is mixed):
    {
        "items": [
            {
                "token": {"address_hash": "0x...", "decimals": "6", ...},
                "total": {"decimals": "6", "value": "1500000"},
                "from": {"hash": "0x...", ...},
                "to": {"hash": "0x...", ...},
                "transaction_hash": "0x...",
                "block_number": 25888691,
                "log_index": 51,
                "timestamp": "2026-09-02T09:23:59.000000Z",
                ...
            },
            ...
        ],
        "next_page_params": {"index": 92, "block_number": 25818613}
    }

    Item shape is BlockScout-native (nested ``token``/``from``/``to``
    objects, decimal ``value`` under ``total``), not flattened to
    Etherscan's flat ``tokenName``/``value``/``timeStamp`` keys — no
    convenience method or test asserts a cross-scanner field contract for
    this Method beyond ``list[dict]``.
    """
    items = response.get('items')
    return list(items) if items else []


def _parse_internal_transactions(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract internal transactions from the V2 internal-transactions response.

    Response format:
    {
        "items": [
            {
                "block_number": 25891449,
                "created_contract": null,
                "error": null,
                "from": {"hash": "0x...", ...},
                "to": {"hash": "0x...", ...},
                "gas_limit": "2300",
                "index": 26,
                "success": true,
                "timestamp": "...",
                "transaction_hash": "0x...",
                "transaction_index": 126,
                "type": "call",
                "value": "0",
            },
            ...
        ],
        "next_page_params": {
            "index": 26, "block_number": 25891449,
            "transaction_index": 126, "items_count": 50
        }
    }

    Item shape is BlockScout-native, not Etherscan's flat
    ``blockNumber``/``traceId``/``isError`` keys — see
    ``_parse_token_transfers`` for the same reconciliation note.
    """
    items = response.get('items')
    return list(items) if items else []


def _parse_nft_portfolio(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract owned NFT instances from the V2 address NFT response.

    Response format:
    {
        "items": [
            {
                "id": "567",
                "token": {"address_hash": "0x...", "type": "ERC-721", ...},
                "token_type": "ERC-721",
                "value": "1",
                "owner": null,
                "metadata": {...},
                "image_url": "...",
                ...
            },
            ...
        ],
        "next_page_params": {
            "token_type": "ERC-721", "token_contract_address_hash": "0x...",
            "token_id": "567", "items_count": 50
        }
    }

    One item per owned NFT instance (``/nft``), matching Etherscan's
    ``addresstokennftinventory`` per-token-id granularity. The alternative
    endpoint ``/nft/collections`` groups by collection with a nested
    ``token_instances`` list instead — a different shape that does not match
    this Method's declared per-item contract, so it was not used here.
    """
    items = response.get('items')
    return list(items) if items else []


def _parse_token_holder_count(response: dict[str, Any]) -> int:
    """
    Extract the holder count from the V2 token info response.

    Response format (abridged):
    {
        "address_hash": "0x...",
        "holders_count": 30506,     # current field name
        "holders": 30506,           # legacy field name on older instances
        ...
    }
    """
    count = response.get('holders_count')
    if count is None:
        count = response.get('holders')
    try:
        return int(count) if count is not None else 0
    except (TypeError, ValueError):
        return 0


@register_scanner
class BlockScoutV2Scanner(Scanner):
    """
    Scanner for Blockscout REST API V2.

    Modern RESTful API with path parameters and rich JSON responses.
    No API key required - public API.

    Key features:
    - Path-based routing (e.g., /api/v2/addresses/{address})
    - Rich nested JSON responses
    - No API key required (public endpoints)
    - Automatic pagination support via next_page_params
    - ENS resolution included in address responses

    Example usage:
        scanner = BlockScoutV2Scanner(
            api_key="",  # Not required
            network="ethereum",
            url_builder=url_builder
        )
        balance = await scanner.call(Method.ACCOUNT_BALANCE, address="0x...")
        tokens = await scanner.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address="0x...")
    """

    name = 'blockscout'
    version = 'v2'

    # ``fetch_page`` follows the server's ``next_page_params`` to exhaustion,
    # so there is no page/offset result window to overflow (see base class).
    result_window = None

    # Cursor vocabulary per paginated endpoint: the keys BlockScout returns in
    # ``next_page_params`` for that endpoint (the same fields the SPECS'
    # ``param_map`` entries declare for cursor threading below). Declared once
    # here — where the cursor is produced — so the MCP cursor whitelist derives
    # these server-controlled key names instead of hand-copying them
    # (``Scanner.cursor_keys`` stays empty: the dialect differs per endpoint).
    CURSOR_KEYS: ClassVar[dict[Method, frozenset[str]]] = {
        Method.ACCOUNT_TRANSACTIONS: frozenset({'block_number', 'index', 'items_count'}),
        Method.ACCOUNT_INTERNAL_TXS: frozenset(
            {'block_number', 'index', 'items_count', 'transaction_index'}
        ),
        Method.ACCOUNT_ERC20_TRANSFERS: frozenset({'block_number', 'index'}),
        Method.ACCOUNT_TOKEN_PORTFOLIO: frozenset({'fiat_value', 'items_count', 'token', 'value'}),
        Method.ACCOUNT_NFT_PORTFOLIO: frozenset(
            {'items_count', 'token_contract_address_hash', 'token_id', 'token_type'}
        ),
        Method.TOKEN_HOLDERS: frozenset({'address_hash', 'items_count', 'value'}),
    }

    # Declared from the same host table ``BASE_URLS`` is built from: an alias
    # this scanner can resolve to an instance is one it declares. Hand-listing
    # them let 'bsc' resolve in the registry and then fail at construction.
    supported_networks = set(BLOCKSCOUT_SCANNER_NETWORKS)

    # Network -> Base URL mapping for Blockscout instances — derived from the
    # shared per-alias host table (one table for BlockScout v1 and v2).
    BASE_URLS: ClassVar[dict[str, str]] = {
        alias: f'https://{host}' for alias, host in BLOCKSCOUT_INSTANCE_HOSTS.items()
    }

    # Endpoint specifications
    # Note: path contains {address} placeholder for path parameter substitution
    # (consumed by URL substitution — ``EndpointSpec.map_params`` never sends
    # path params as query). ``unknown_params='drop'``: V2 endpoints reject
    # undeclared query keys, and a server cursor must never smuggle foreign
    # state onto the wire (pinned by tests).
    SPECS = {
        Method.ACCOUNT_BALANCE: EndpointSpec(
            http_method='GET',
            path='/api/v2/addresses/{address}',
            query={},
            param_map={'address': 'address'},
            parser=_parse_balance,
            requires_api_key=False,
            unknown_params='drop',
        ),
        Method.ACCOUNT_TOKEN_PORTFOLIO: EndpointSpec(
            http_method='GET',
            path='/api/v2/addresses/{address}/tokens',
            query={'type': 'ERC-20'},
            param_map={'address': 'address'},
            parser=_parse_token_portfolio,
            requires_api_key=False,
            unknown_params='drop',
        ),
        Method.ACCOUNT_TRANSACTIONS: EndpointSpec(
            http_method='GET',
            path='/api/v2/addresses/{address}/transactions',
            query={},
            param_map={
                'address': 'address',
                # BlockScout returns these fields in next_page_params.
                'block_number': 'block_number',
                'index': 'index',
                'items_count': 'items_count',
            },
            parser=_parse_transactions,
            requires_api_key=False,
            unknown_params='drop',
        ),
        Method.CONTRACT_ABI: EndpointSpec(
            http_method='GET',
            path='/api/v2/smart-contracts/{address}',
            query={},
            param_map={'address': 'address'},
            parser=_parse_contract_abi,
            requires_api_key=False,
            unknown_params='drop',
        ),
        Method.BLOCK_BY_NUMBER: EndpointSpec(
            http_method='GET',
            path='/api/v2/blocks/{block_number}',
            query={},
            param_map={'block_number': 'block_number'},
            parser=_parse_raw,
            requires_api_key=False,
            unknown_params='drop',
        ),
        Method.TOKEN_HOLDERS: EndpointSpec(
            http_method='GET',
            path='/api/v2/tokens/{contract_address}/holders',
            query={},
            param_map={
                'contract_address': 'contract_address',
                # BlockScout returns these fields in next_page_params.
                'value': 'value',
                'address_hash': 'address_hash',
                'items_count': 'items_count',
            },
            parser=_parse_token_holders,
            requires_api_key=False,
            unknown_params='drop',
        ),
        Method.TOKEN_HOLDER_COUNT: EndpointSpec(
            http_method='GET',
            path='/api/v2/tokens/{contract_address}',
            query={},
            param_map={'contract_address': 'contract_address'},
            parser=_parse_token_holder_count,
            requires_api_key=False,
            unknown_params='drop',
        ),
        Method.ACCOUNT_ERC20_TRANSFERS: EndpointSpec(
            http_method='GET',
            path='/api/v2/addresses/{address}/token-transfers',
            # The endpoint mixes ERC-20/721/1155 transfers by default (see
            # docstring on _parse_token_transfers); this static filter is
            # what makes it ACCOUNT_ERC20_TRANSFERS rather than "all transfers".
            query={'type': 'ERC-20'},
            param_map={
                'address': 'address',
                'contract_address': 'token',
                # BlockScout returns these fields in next_page_params.
                'index': 'index',
                'block_number': 'block_number',
            },
            parser=_parse_token_transfers,
            requires_api_key=False,
            unknown_params='drop',
        ),
        Method.ACCOUNT_INTERNAL_TXS: EndpointSpec(
            http_method='GET',
            path='/api/v2/addresses/{address}/internal-transactions',
            query={},
            param_map={
                'address': 'address',
                # BlockScout returns these fields in next_page_params.
                'index': 'index',
                'block_number': 'block_number',
                'transaction_index': 'transaction_index',
                'items_count': 'items_count',
            },
            parser=_parse_internal_transactions,
            requires_api_key=False,
            unknown_params='drop',
        ),
        # Method.TX_BY_HASH deliberately NOT declared: BlockScout V2's native
        # transaction envelope carries its own top-level ``result`` field
        # (the tx execution status string, e.g. "success"/"error"), which
        # collides with Network._handle_response's generic Etherscan-style
        # envelope unwrapping (`if 'result' in response_json: payload =
        # response_json['result']`, aiochainscan/network.py — shared by
        # every scanner and off-limits here). Live-verified: a GET to
        # /api/v2/transactions/{hash} returns the full tx dict, but the
        # scanner-agnostic Network layer silently reduces it to the bare
        # string "success" before this spec's parser ever runs. A wrong
        # spec that returns a string where callers expect a dict is worse
        # than no spec, so this Method is not declared for BlockScout V2.
        Method.CONTRACT_SOURCE: EndpointSpec(
            http_method='GET',
            # Same resource CONTRACT_ABI reads (only its 'abi' field); this
            # spec returns the full verified-source envelope unfiltered.
            path='/api/v2/smart-contracts/{address}',
            query={},
            param_map={'address': 'address'},
            parser=_parse_raw,
            requires_api_key=False,
            unknown_params='drop',
        ),
        Method.ACCOUNT_NFT_PORTFOLIO: EndpointSpec(
            http_method='GET',
            path='/api/v2/addresses/{address}/nft',
            query={},
            param_map={
                'address': 'address',
                # BlockScout returns these fields in next_page_params.
                'token_type': 'token_type',
                'token_contract_address_hash': 'token_contract_address_hash',
                'token_id': 'token_id',
                'items_count': 'items_count',
            },
            parser=_parse_nft_portfolio,
            requires_api_key=False,
            unknown_params='drop',
        ),
    }

    def __init__(
        self,
        api_key: str,
        network: str,
        url_builder: UrlBuilder,
        chain_id: int | None = None,
        network_client: Network | None = None,
        base_url: str | None = None,
    ) -> None:
        """
        Initialize BlockScout V2 scanner with network-specific instance.

        Args:
            api_key: API key (not required for Blockscout V2)
            network: Network name (must be in supported_networks)
            url_builder: UrlBuilder instance (used for compatibility)
            chain_id: Chain ID (optional, will be resolved from network)
            network_client: Optional Network instance for connection pooling
            base_url: Custom base URL for self-hosted BlockScout instances
                (overrides the per-network instance mapping; no API key needed)
        """
        super().__init__(api_key, network, url_builder, chain_id, network_client, base_url)

        # Resolve the instance root: explicit self-hosted URL or the
        # per-network public instance mapping (shared unknown-network
        # ValueError shape lives on the base).
        if base_url is None:
            self.base_url = self._require_mapped_network(self.BASE_URLS, 'Blockscout V2 instance')
        self._instance_root = self.base_url

    def _build_url(self, spec: EndpointSpec, **params: Any) -> str:
        """
        Build full URL with path parameter substitution.

        Replaces {address} placeholders in the path with actual values.

        Args:
            spec: Endpoint specification
            **params: Parameters including address

        Returns:
            Full URL with substituted path parameters
        """
        path = spec.path

        # Substitute path parameters (e.g., {address})
        for param_name, value in params.items():
            placeholder = f'{{{param_name}}}'
            if placeholder in path:
                path = path.replace(placeholder, urllib.parse.quote(str(value), safe=''))

        return f'{self.base_url}{path}'

    # ------------------------------------------------------------------
    # Provider dialect (the base owns the ladder, dispatch and params)
    # ------------------------------------------------------------------

    def _request_url(self, spec: EndpointSpec, params: dict[str, Any]) -> str:
        """Full per-instance URL with path placeholders substituted."""
        return self._build_url(spec, **params)

    def _transport_headers(self, spec: EndpointSpec) -> dict[str, str]:
        """Headers that disable brotli compression (not always supported)."""
        headers = {
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
        }
        if spec.http_method == 'POST':
            headers['Content-Type'] = 'application/json'
        return headers

    async def fetch_page(
        self,
        method: Method,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        Fetch one page, preserving BlockScout V2's ``next_page_params`` cursor.

        Follows the base cursor contract: merge a non-``None`` cursor into
        ``params`` for the next call; ``None`` terminates pagination. The
        request runs under the shared error ladder (the ``call()`` path gets
        it from :meth:`Scanner.call`).

        Args:
            method: Logical method to execute
            params: Parameters for the method (merged cursor included for
                subsequent pages)

        Returns:
            Tuple of (items, next_cursor)
        """
        spec = self._spec_for(method)
        # Missing-client guard before the ladder: a missing Network is a
        # programming error (RuntimeError), never a network failure.
        self._require_network_client()

        with translate_unexpected_errors(self._error_context(method)):
            raw_response = await self._perform_raw_request(spec, method, params)

        if isinstance(raw_response, dict):
            # TOKEN_HOLDERS is normalized by the same parser the SPECS entry
            # uses, so the pagination path (streaming/get_all) matches
            # ``call()`` output by construction.
            if method is Method.TOKEN_HOLDERS:
                items: Any = _parse_token_holders(raw_response)
            else:
                items = raw_response.get('items', [])
            next_cursor = raw_response.get('next_page_params')
        elif isinstance(raw_response, list):
            # Fallback for list responses
            items = raw_response
            next_cursor = None
        else:
            items, next_cursor = [], None

        cursor = dict(next_cursor) if next_cursor else {}
        # A remote cursor is opaque pagination state, but it must never be
        # allowed to replace resource identity embedded in this endpoint's
        # path (for example, switching the requested address on page two).
        for public_name, scanner_name in spec.param_map.items():
            if f'{{{public_name}}}' in spec.path:
                cursor.pop(public_name, None)
                cursor.pop(scanner_name, None)

        return list(items) if items else [], cursor or None

    # ========================================================================
    # Scanner-port methods (explicit dependencies, see docstrings)
    # ========================================================================

    async def get_address_info(self, address: str) -> dict[str, Any]:
        """
        Get full address information including ENS, balance, contract status.

        This is a scanner-port method serving ENS reverse resolution: it is
        injected into :class:`~aiochainscan.services.ens_resolver.ENSResolver`
        (via its ``AddressInfoProvider`` port) so reverse lookups can read
        ``ens_domain_name`` directly from the BlockScout V2 address endpoint.
        It is not part of the generic ``call()``/``fetch_page()`` contract.

        Args:
            address: Ethereum address

        Returns:
            Full address info dict
        """
        spec = self.SPECS[Method.ACCOUNT_BALANCE]
        request_data = self._build_request(spec, address=address)

        network = self._require_network_client()

        result = await self._dispatch_request(spec, request_data, network)
        if isinstance(result, dict):
            return dict(result)
        return {}
