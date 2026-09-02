"""
Etherscan API v2 scanner implementation for multichain support.

SPECS are derived programmatically from the parent EtherscanLikeScanner:
each inherited spec gets ``'chainid': '{chain_id}'`` injected into its
query dict so the v2 multichain routing works transparently.

Token-holder specs (``tokenholderlist`` / ``topholders`` /
``tokenholdercount``) live here instead of the shared Etherscan-like base:
they are Etherscan PRO actions that BlockScout's Etherscan-compatible layer
does not implement (live-checked: it answers ``"Unknown action"``), so
inheriting them would falsely widen BlockScout v1's declared surface.
"""

from dataclasses import replace
from typing import Any

from ..core.endpoint import EndpointSpec, etherscan_parser
from ..domain.method import Method
from . import register_scanner
from ._etherscan_like import EtherscanLikeScanner
from .base import checksummed_holder_address


def _parse_token_holders(response: Any) -> list[dict[str, Any]]:
    """Normalize Etherscan ``tokenholderlist``/``topholders`` items.

    The parser runs at the post-unwrap seam: ``Network._handle_response``
    has already extracted the Etherscan envelope's ``result`` before
    ``spec.parse_response`` is invoked, so the expected input is the bare
    holder-item list. A full ``{'result': [...]}`` envelope is tolerated
    defensively, but it is not the production shape.

    Unified item shape (Wei-like quantities stay strings):

    - ``address``: holder address, EIP-55 checksummed
    - ``value``: held quantity in the token's smallest unit (str)
    - ``TokenHolderAddressType``: preserved when present (``topholders`` only;
      ``'C'`` for contracts, ``'A'`` for EOAs)
    """
    payload: Any = response
    if isinstance(response, dict) and isinstance(response.get('result'), list):
        payload = response['result']
    if not isinstance(payload, list):
        return []
    items: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        item: dict[str, Any] = {
            'address': checksummed_holder_address(raw.get('TokenHolderAddress')),
            'value': str(raw.get('TokenHolderQuantity') or '0'),
        }
        address_type = raw.get('TokenHolderAddressType')
        if address_type is not None:
            item['TokenHolderAddressType'] = address_type
        items.append(item)
    return items


def _inject_chain_id(
    specs: dict[Method, EndpointSpec],
    methods: set[Method],
) -> dict[Method, EndpointSpec]:
    """Return *copies* of the selected parent specs with ``chainid`` added to each query."""
    return {
        m: replace(specs[m], query={**specs[m].query, 'chainid': '{chain_id}'}) for m in methods
    }


# Parent methods that V2 supports without any param_map changes.
# The Etherscan v2 multichain API exposes the same module/action surface as
# the classic layout (routing via ``chainid``), so every parent spec is
# inherited. EVENT_LOGS is excluded here because V2 extends it below.
_V2_INHERITED_METHODS: set[Method] = set(EtherscanLikeScanner.SPECS) - {Method.EVENT_LOGS}


@register_scanner
class EtherscanV2(EtherscanLikeScanner):
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
        'sonic',
    }

    # Build SPECS from parent with chainid injection, plus V2-specific overrides.
    SPECS: dict[Method, EndpointSpec] = {
        **_inject_chain_id(EtherscanLikeScanner.SPECS, _V2_INHERITED_METHODS),
        # EVENT_LOGS gains page/offset params in V2 on top of the chainid injection.
        Method.EVENT_LOGS: replace(
            EtherscanLikeScanner.SPECS[Method.EVENT_LOGS],
            query={**EtherscanLikeScanner.SPECS[Method.EVENT_LOGS].query, 'chainid': '{chain_id}'},
            param_map={
                **EtherscanLikeScanner.SPECS[Method.EVENT_LOGS].param_map,
                'page': 'page',
                'offset': 'offset',
            },
        ),
        # Token holders (Etherscan PRO token module; not on the shared
        # Etherscan-like base — see module docstring). ``topholders`` has no
        # ``page`` param: ``offset`` is the result limit (max 1000).
        Method.TOKEN_HOLDERS: EndpointSpec(
            http_method='GET',
            path='/api',
            query={
                'module': 'token',
                'action': 'tokenholderlist',
                'chainid': '{chain_id}',
            },
            param_map={
                'contract_address': 'contractaddress',
                'page': 'page',
                'offset': 'offset',
            },
            parser=_parse_token_holders,
        ),
        Method.TOKEN_TOP_HOLDERS: EndpointSpec(
            http_method='GET',
            path='/api',
            query={
                'module': 'token',
                'action': 'topholders',
                'chainid': '{chain_id}',
            },
            param_map={
                'contract_address': 'contractaddress',
                'offset': 'offset',
            },
            parser=_parse_token_holders,
        ),
        Method.TOKEN_HOLDER_COUNT: EndpointSpec(
            http_method='GET',
            path='/api',
            query={
                'module': 'token',
                'action': 'tokenholdercount',
                'chainid': '{chain_id}',
            },
            param_map={'contract_address': 'contractaddress'},
            parser=etherscan_parser,
        ),
    }
