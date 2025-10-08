from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

aiohttp = pytest.importorskip('aiohttp')
pytest.importorskip('aiohttp_retry')

from aiohttp import ClientResponseError, ClientTimeout
from aiohttp_retry import ExponentialRetry

from aiochainscan.network import Network


class StubUrlBuilder:
    """Minimal UrlBuilder replacement pointing to a fixed endpoint."""

    def __init__(self, url: str) -> None:
        self.API_URL = url

    @staticmethod
    def filter_and_sign(
        params: dict[str, Any] | None, headers: dict[str, str] | None
    ) -> tuple[dict[str, Any], dict[str, str]]:
        return dict(params or {}), dict(headers or {})


class CountingThrottler:
    """Deterministic throttler enforcing a hard concurrency ceiling."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._active = 0
        self.max_seen = 0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "CountingThrottler":
        while True:
            async with self._lock:
                if self._active < self._limit:
                    self._active += 1
                    self.max_seen = max(self.max_seen, self._active)
                    break
            await asyncio.sleep(0)
        return self

    async def __aexit__(self, *_: Any) -> None:
        async with self._lock:
            self._active -= 1


async def _retry_after_honored_once(fake_server: Any) -> None:
    builder = StubUrlBuilder(f'{fake_server.base_url}/429_once')
    retry_options = ExponentialRetry(attempts=2, statuses={429})
    network = Network(
        builder,
        timeout=ClientTimeout(total=5),
        retry_options=retry_options,
        use_cffi=False,
        loop=fake_server.loop,
    )
    try:
        start = time.perf_counter()
        payload = await network.get()
        elapsed = time.perf_counter() - start
    finally:
        await network.close()

    assert payload == {'ok': True}
    assert fake_server.state['429_once'] == 2
    assert elapsed >= 1.0
    assert elapsed < 2.5


async def _retry_sustained_429(fake_server: Any) -> None:
    builder = StubUrlBuilder(f'{fake_server.base_url}/429_sustained')
    retry_options = ExponentialRetry(attempts=3, statuses={429})
    network = Network(
        builder,
        timeout=ClientTimeout(total=5),
        retry_options=retry_options,
        use_cffi=False,
        loop=fake_server.loop,
    )
    try:
        with pytest.raises(ClientResponseError) as exc_info:
            await network.get()
    finally:
        await network.close()

    err = exc_info.value
    assert err.status == 429
    assert err.headers.get('Retry-After') == '2'
    assert fake_server.state['429_sustained'] == 3


async def _timeout_raises(fake_server: Any) -> None:
    builder = StubUrlBuilder(f'{fake_server.base_url}/timeout')
    network = Network(
        builder,
        timeout=ClientTimeout(total=0.05),
        retry_options=ExponentialRetry(attempts=1),
        use_cffi=False,
        loop=fake_server.loop,
    )
    try:
        with pytest.raises(asyncio.TimeoutError):
            await network.get()
    finally:
        await network.close()

    assert fake_server.state['timeout'] == 1


async def _no_retry_on_non_retryable(fake_server: Any) -> None:
    builder = StubUrlBuilder(f'{fake_server.base_url}/forbidden')
    retry_options = ExponentialRetry(attempts=4, statuses={429})
    network = Network(
        builder,
        timeout=ClientTimeout(total=5),
        retry_options=retry_options,
        use_cffi=False,
        loop=fake_server.loop,
    )
    try:
        with pytest.raises(ClientResponseError) as exc_info:
            await network.get()
    finally:
        await network.close()

    assert exc_info.value.status == 403
    assert fake_server.state['forbidden'] == 1


async def _throttler_enforces(fake_server: Any) -> None:
    builder = StubUrlBuilder(f'{fake_server.base_url}/ok')
    throttler = CountingThrottler(limit=2)
    network = Network(
        builder,
        timeout=ClientTimeout(total=5),
        throttler=throttler,
        retry_options=ExponentialRetry(attempts=1),
        use_cffi=False,
        loop=fake_server.loop,
    )

    async def do_request() -> Any:
        return await network.get()

    try:
        await asyncio.gather(*(do_request() for _ in range(5)))
    finally:
        await network.close()

    assert fake_server.state['ok_total'] == 5
    assert fake_server.state['ok_max'] <= 2
    assert throttler.max_seen <= 2


def test_retry_after_honored_once(fake_server: Any) -> None:
    fake_server.run(_retry_after_honored_once(fake_server))


def test_retry_sustained_429_gives_rate_limit_error(fake_server: Any) -> None:
    fake_server.run(_retry_sustained_429(fake_server))


def test_timeout_raises_timeout_error(fake_server: Any) -> None:
    fake_server.run(_timeout_raises(fake_server))


def test_no_retry_on_non_retryable_4xx(fake_server: Any) -> None:
    fake_server.run(_no_retry_on_non_retryable(fake_server))


def test_throttler_enforces_concurrency(fake_server: Any) -> None:
    fake_server.run(_throttler_enforces(fake_server))
