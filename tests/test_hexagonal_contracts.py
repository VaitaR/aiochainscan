"""Focused tests for the executable hexagonal import contracts."""

from typing import Any

import pytest

from aiochainscan import Method
from aiochainscan.core.method import Method as CoreMethod
from aiochainscan.domain.method import Method as DomainMethod
from aiochainscan.services.ens_resolver import ENSResolver
from aiochainscan.services.pagination import PageProvider, page_fetcher


def test_method_compatibility_imports_preserve_identity() -> None:
    assert Method is CoreMethod is DomainMethod


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    async def get(self, key: str) -> Any | None:
        return self.values.get(key)

    async def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def clear(self) -> None:
        self.values.clear()


class FakeENSClient:
    chain_id = 1
    network = 'ethereum'

    async def call(self, method: Method, **params: Any) -> Any:
        raise AssertionError(f'unexpected network call: {method}, {params}')


@pytest.mark.asyncio
async def test_ens_resolver_uses_injected_cache() -> None:
    cache = FakeCache()
    cache.values['name:vitalik.eth'] = '0xcached'

    resolver = ENSResolver(FakeENSClient(), cache=cache)

    assert resolver._cache is cache
    assert await resolver.resolve_name('vitalik.eth') == '0xcached'


def test_ens_resolver_without_cache_injection_is_uncached() -> None:
    resolver = ENSResolver(FakeENSClient())

    assert resolver._cache is None


class StructuralPageProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[Method, dict[str, Any]]] = []

    async def fetch_page(
        self, method: Method, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        self.calls.append((method, params))
        return [{'hash': '0x1'}], None


@pytest.mark.asyncio
async def test_pagination_accepts_structural_page_provider() -> None:
    provider = StructuralPageProvider()
    assert isinstance(provider, PageProvider)

    fetch = page_fetcher(provider, Method.ACCOUNT_TRANSACTIONS)
    assert await fetch({'address': '0xabc'}) == ([{'hash': '0x1'}], None)
    assert provider.calls == [(Method.ACCOUNT_TRANSACTIONS, {'address': '0xabc'})]
