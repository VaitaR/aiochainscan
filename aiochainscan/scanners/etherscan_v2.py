"""
Etherscan API v2 scanner implementation for multichain support.

SPECS are derived programmatically from the parent EtherscanLikeScanner:
each inherited spec gets ``'chainid': '{chain_id}'`` injected into its
query dict so the v2 multichain routing works transparently.
"""

from dataclasses import replace

from ..core.endpoint import EndpointSpec
from ..core.method import Method
from . import register_scanner
from ._etherscan_like import EtherscanLikeScanner


def _inject_chain_id(
    specs: dict[Method, EndpointSpec],
    methods: set[Method],
) -> dict[Method, EndpointSpec]:
    """Return *copies* of the selected parent specs with ``chainid`` added to each query."""
    return {
        m: replace(specs[m], query={**specs[m].query, 'chainid': '{chain_id}'}) for m in methods
    }


# Parent methods that V2 supports without any param_map changes.
_V2_INHERITED_METHODS: set[Method] = {
    Method.ACCOUNT_BALANCE,
    Method.ACCOUNT_TRANSACTIONS,
    Method.ACCOUNT_INTERNAL_TXS,
    Method.TX_BY_HASH,
    Method.BLOCK_BY_NUMBER,
    Method.CONTRACT_ABI,
    Method.GAS_ORACLE,
    Method.ACCOUNT_TOKEN_PORTFOLIO,
    Method.ACCOUNT_NFT_PORTFOLIO,
    Method.CONTRACT_VERIFY,
    Method.CONTRACT_VERIFY_STATUS,
}


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
    }
