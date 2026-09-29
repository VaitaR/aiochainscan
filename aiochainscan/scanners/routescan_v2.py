"""Routescan's Etherscan-compatible API scanner.

Routescan uses one host with the network segment and EVM chain id embedded in
the path. The API is keyless by default; an optional key is sent in the
``apikey`` header as documented by Routescan.
"""

from dataclasses import replace
from typing import Any

from ..chain_registry import ROUTESCAN_SCANNER_NETWORKS
from ..core.endpoint import EndpointSpec
from ..core.url_builder import UrlBuilder
from ..domain.method import Method
from . import register_scanner
from ._etherscan_like import EtherscanLikeScanner


@register_scanner
class RoutescanV2(EtherscanLikeScanner):
    """Routescan Etherscan-compatible API v2 scanner."""

    name = 'routescan'
    version = 'v2'
    auth_mode = 'header'
    auth_field = 'apikey'

    # Routescan's Free (Keyless) plan allows 2 requests/second and 10,000
    # calls/day: https://routescan.io/docs/plans-and-limits/rate-limits
    # Keep the library default below that ceiling while still allowing callers
    # to inject a higher-rate limiter for a registered or paid key.
    default_rate_limit_rps = 1.0

    # Live probes on 2026-09-30 verified the Etherscan-compatible envelope for
    # Ethereum (1), Avalanche C-Chain (43114), Plasma (9745) and Corn
    # (21000000). Mode (34443) answered status=0 "chain not supported" and is
    # intentionally excluded.
    supported_networks = set(ROUTESCAN_SCANNER_NETWORKS)

    # Verified live 2026-09-30 on Avalanche WAVAX: ``getLogs``, ``txlist`` and
    # ``tokentx`` answer ``page * offset > 10000`` with "Result window is too
    # large", so ``result_window`` is inherited unchanged. Unlike Etherscan the
    # page is not clamped at 1000: ``getLogs`` serves ``offset=10000``, but
    # ``txlist`` with ``offset=10000`` returns HTTP 502 while 5000 is served.
    max_page_size = 5_000

    SPECS: dict[Method, EndpointSpec] = {
        **EtherscanLikeScanner.SPECS,
        # The shared base declares the log filters but not page/offset because
        # BlockScout V1 ignores those fields. Routescan does paginate this
        # endpoint, so expose the cursor fields at the same seam as Etherscan.
        Method.EVENT_LOGS: replace(
            EtherscanLikeScanner.SPECS[Method.EVENT_LOGS],
            param_map={
                **EtherscanLikeScanner.SPECS[Method.EVENT_LOGS].param_map,
                'page': 'page',
                'offset': 'offset',
            },
        ),
    }

    def __init__(
        self,
        api_key: str,
        network: str,
        url_builder: UrlBuilder,
        chain_id: int | None = None,
        network_client: Any = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(api_key, network, url_builder, chain_id, network_client, base_url)
        self._instance_root = 'https://api.routescan.io'

    def _request_url(self, spec: EndpointSpec, params: dict[str, Any]) -> str:
        """Build the per-chain Routescan Etherscan-compatible API URL."""
        if self.chain_id is None:
            raise ValueError('Routescan requires a resolved chain id')
        network_segment = (
            'testnet' if self.network.endswith(('testnet', '-testnet')) else 'mainnet'
        )
        return (
            f'https://api.routescan.io/v2/network/{network_segment}/evm/'
            f'{self.chain_id}/etherscan/api'
        )
