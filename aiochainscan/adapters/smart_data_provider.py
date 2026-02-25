from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from time import monotonic
from typing import Any, TypeVar

from aiochainscan.core.context import ProviderContext
from aiochainscan.domain.models import Address, TxHash

T = TypeVar('T')


class SmartDataProvider:
    """Transport router for GraphQL-vs-REST data retrieval.

    Services should delegate transport decisions here and keep business logic
    transport-agnostic.
    """

    def __init__(self, ctx: ProviderContext) -> None:
        self._ctx = ctx

    def _can_use_graphql(self, feature: str) -> bool:
        return (
            self._ctx.federator is not None
            and self._ctx.gql is not None
            and self._ctx.gql_builder is not None
            and self._ctx.federator.should_use_graphql(
                feature, api_kind=self._ctx.api_kind, network=self._ctx.network
            )
        )

    def _candidate_urls(self, base_url: str) -> list[str]:
        base = base_url.rstrip('/')
        return [
            f'{base}/graphql',
            f'{base}/api/graphql',
            f'{base}/api/v1/graphql',
            f'{base}/graphiql',
        ]

    async def fetch_logs_page(
        self,
        *,
        address: Address,
        start_block: int | str,
        end_block: int | str,
        topics: list[str] | None,
        cursor: str | None,
        page_size: int | None,
        gql_headers: Mapping[str, str] | None,
        rest_fallback: Callable[[], Awaitable[tuple[list[dict[str, Any]], str | None]]],
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not self._can_use_graphql('logs'):
            return await rest_fallback()

        endpoint = self._ctx.endpoint_builder.open(
            api_key=self._ctx.api_key,
            api_kind=self._ctx.api_kind,
            network=self._ctx.network,
        )
        gql_client = self._ctx.gql
        gql_builder = self._ctx.gql_builder
        if gql_client is None or gql_builder is None:
            return await rest_fallback()

        query, variables = gql_builder.build_logs_query(
            address=str(address),
            start_block=start_block,
            end_block=end_block,
            topics=topics,
            after_cursor=cursor,
            first=page_size,
        )
        _, headers = endpoint.filter_and_sign(params=None, headers=None)
        if gql_headers:
            merged_headers = dict(headers)
            merged_headers.update(gql_headers)
            headers = merged_headers

        async def _do_gql(gql_url: str) -> Any:
            if self._ctx.rate_limiter is not None:
                await self._ctx.rate_limiter.acquire(
                    key=f'{self._ctx.api_kind}:{self._ctx.network}:logs:gql'
                )
            start = monotonic()
            try:
                return await gql_client.execute(gql_url, query, variables, headers=headers)
            finally:
                if self._ctx.telemetry is not None:
                    duration_ms = int((monotonic() - start) * 1000)
                    await self._ctx.telemetry.record_event(
                        'logs.get_logs.duration',
                        {
                            'api_kind': self._ctx.api_kind,
                            'network': self._ctx.network,
                            'duration_ms': duration_ms,
                            'provider_type': 'graphql',
                        },
                    )

        last_exc: Exception | None = None
        for gql_url in self._candidate_urls(endpoint.base_url):
            try:
                data: Any
                if self._ctx.retry is not None:

                    async def _runner(url: str = gql_url) -> Any:
                        return await _do_gql(url)

                    data = await self._ctx.retry.run(_runner)
                else:
                    data = await _do_gql(gql_url)

                items, next_cursor = gql_builder.map_logs_response(data)
                if self._ctx.telemetry is not None:
                    await self._ctx.telemetry.record_event(
                        'logs.get_logs.ok',
                        {
                            'api_kind': self._ctx.api_kind,
                            'network': self._ctx.network,
                            'items': len(items),
                            'provider_type': 'graphql',
                        },
                    )
                return items, next_cursor
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue

        if self._ctx.telemetry is not None and last_exc is not None:
            await self._ctx.telemetry.record_error(
                'logs.get_logs.error',
                last_exc,
                {
                    'api_kind': self._ctx.api_kind,
                    'network': self._ctx.network,
                    'provider_type': 'graphql',
                },
            )

        return await rest_fallback()

    async def fetch_transaction_by_hash(
        self,
        *,
        txhash: TxHash,
        cache_key: str,
        cache_ttl_seconds: int,
        rest_fallback: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        if not self._can_use_graphql('transaction_by_hash'):
            return await rest_fallback()

        endpoint = self._ctx.endpoint_builder.open(
            api_key=self._ctx.api_key,
            api_kind=self._ctx.api_kind,
            network=self._ctx.network,
        )
        gql_client = self._ctx.gql
        gql_builder = self._ctx.gql_builder
        if gql_client is None or gql_builder is None:
            return await rest_fallback()

        query, variables = gql_builder.build_transaction_by_hash_query(txhash=str(txhash))
        _, headers = endpoint.filter_and_sign(params=None, headers=None)

        async def _do_gql(gql_url: str) -> Any:
            if self._ctx.rate_limiter is not None:
                await self._ctx.rate_limiter.acquire(
                    key=f'{self._ctx.api_kind}:{self._ctx.network}:tx:gql'
                )
            start = monotonic()
            try:
                return await gql_client.execute(gql_url, query, variables, headers=headers)
            finally:
                if self._ctx.telemetry is not None:
                    duration_ms = int((monotonic() - start) * 1000)
                    await self._ctx.telemetry.record_event(
                        'transaction.get_transaction_by_hash.duration',
                        {
                            'api_kind': self._ctx.api_kind,
                            'network': self._ctx.network,
                            'duration_ms': duration_ms,
                            'provider_type': 'graphql',
                        },
                    )

        last_exc: Exception | None = None
        for gql_url in self._candidate_urls(endpoint.base_url):
            try:
                data: Any
                if self._ctx.retry is not None:

                    async def _runner(url: str = gql_url) -> Any:
                        return await _do_gql(url)

                    data = await self._ctx.retry.run(_runner)
                else:
                    data = await _do_gql(gql_url)

                mapped = gql_builder.map_transaction_response(data)
                if isinstance(mapped, dict) and mapped:
                    if self._ctx.telemetry is not None:
                        await self._ctx.telemetry.record_event(
                            'transaction.get_transaction_by_hash.ok',
                            {
                                'api_kind': self._ctx.api_kind,
                                'network': self._ctx.network,
                                'provider_type': 'graphql',
                            },
                        )
                    if self._ctx.cache is not None:
                        await self._ctx.cache.set(cache_key, mapped, ttl_seconds=cache_ttl_seconds)
                    return mapped
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue

        if self._ctx.telemetry is not None and last_exc is not None:
            await self._ctx.telemetry.record_error(
                'transaction.get_transaction_by_hash.error',
                last_exc,
                {
                    'api_kind': self._ctx.api_kind,
                    'network': self._ctx.network,
                    'provider_type': 'graphql',
                },
            )

        return await rest_fallback()
