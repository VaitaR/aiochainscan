"""ProviderContext: bundles all infrastructure ports for a single API provider.

Instead of threading 8-12 individual kwargs through every service function,
callers build one ``ProviderContext`` and pass it as a single ``ctx`` argument.

Typical construction (inside *_facade.py* or *fetch_all.py*)::

    ctx = ProviderContext(
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        endpoint_builder=endpoint_builder,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        cache=cache,
    )
    result = await get_block_by_number(ctx=ctx, tag=tag, full=False)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry

if TYPE_CHECKING:
    from aiochainscan.ports.graphql_client import GraphQLClient
    from aiochainscan.ports.graphql_query_builder import GraphQLQueryBuilder
    from aiochainscan.ports.provider_federator import ProviderFederator


@dataclass
class ProviderContext:
    """All infrastructure ports for one API provider, bundled into a single object.

    Attributes:
        api_kind:         Scanner identifier used for URL building and telemetry
                          (e.g. ``'eth'``, ``'blockscout_eth'``).
        network:          Chain / network name (e.g. ``'main'``, ``'ethereum'``).
        api_key:          API key string (empty string ``''`` when not required).
        http:             Async HTTP client port.
        endpoint_builder: Builds signed API endpoint URLs from ``api_kind`` / ``network``.
        rate_limiter:     Optional token-bucket rate limiter.
        retry:            Optional retry policy (wraps calls with back-off).
        telemetry:        Optional structured telemetry recorder.
        cache:            Optional async key-value cache.

    GraphQL ports (optional, only used by transaction service):
        gql:              GraphQL execution client.
        gql_builder:      Builds typed GraphQL queries.
        federator:        Decides REST vs. GraphQL per feature.
    """

    api_kind: str
    network: str
    api_key: str
    http: HttpClient
    endpoint_builder: EndpointBuilder

    # Optional infra ports
    rate_limiter: RateLimiter | None = field(default=None)
    retry: RetryPolicy | None = field(default=None)
    telemetry: Telemetry | None = field(default=None)
    cache: Cache | None = field(default=None)

    # GraphQL ports (transaction service, future GraphQL support)
    gql: GraphQLClient | None = field(default=None)
    gql_builder: GraphQLQueryBuilder | None = field(default=None)
    federator: ProviderFederator | None = field(default=None)
