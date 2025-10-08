"""Pytest configuration for aiochainscan tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Iterator, TypeVar

import pytest


def pytest_configure(config):
    """Configure pytest - display API key status for integration tests."""
    # Only show API key status if integration tests are being run
    if config.getoption('keyword', None) == 'integration' or 'test_integration' in str(
        config.args
    ):
        try:
            from tests.test_integration import print_api_key_status

            print_api_key_status()
        except ImportError:
            pass


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers and information."""
    integration_tests = []
    unit_tests = []

    for item in items:
        if 'test_integration' in str(item.fspath):
            integration_tests.append(item)
        else:
            unit_tests.append(item)

    # If only integration tests are being run, show the status
    if integration_tests and not unit_tests:
        try:
            from tests.test_integration import print_api_key_status

            print_api_key_status()
        except ImportError:
            pass


@pytest.fixture(scope='session', autouse=True)
def integration_test_setup():
    """Setup for integration tests - show API key status if needed."""
    # This fixture runs automatically for all test sessions
    pass


T = TypeVar('T')


@dataclass(slots=True)
class FakeServer:
    """Lightweight container describing the in-process aiohttp test server."""

    base_url: str
    state: dict[str, Any]
    loop: asyncio.AbstractEventLoop

    def run(self, coro: Awaitable[T]) -> T:
        """Execute the given coroutine on the server's event loop."""

        return self.loop.run_until_complete(coro)


def _build_fake_app() -> Any:
    """Create an aiohttp web application implementing deterministic endpoints."""

    pytest.importorskip('aiohttp')
    from aiohttp import web  # Lazy import to avoid hard dependency at import time

    state: dict[str, Any] = {
        '429_once': 0,
        '429_sustained': 0,
        'timeout': 0,
        'forbidden': 0,
        'ok_total': 0,
        'ok_active': 0,
        'ok_max': 0,
    }

    app = web.Application()
    app['state'] = state
    app['timeout_delay'] = 0.2
    app['ok_delay'] = 0.05

    async def handle_429_once(request: web.Request) -> web.Response:
        state['429_once'] += 1
        if state['429_once'] == 1:
            return web.json_response(
                {'status': '0', 'message': 'too many requests'},
                status=429,
                headers={'Retry-After': '1'},
            )
        return web.json_response({'status': '1', 'result': {'ok': True}})

    async def handle_429_sustained(request: web.Request) -> web.Response:
        state['429_sustained'] += 1
        return web.json_response(
            {'status': '0', 'message': 'limit'},
            status=429,
            headers={'Retry-After': '2'},
        )

    async def handle_timeout(request: web.Request) -> web.Response:
        state['timeout'] += 1
        await asyncio.sleep(app['timeout_delay'])
        return web.json_response({'status': '1', 'result': 'slow'})

    async def handle_forbidden(request: web.Request) -> web.Response:
        state['forbidden'] += 1
        return web.json_response({'status': '0', 'message': 'forbidden'}, status=403)

    async def handle_ok(request: web.Request) -> web.Response:
        state['ok_total'] += 1
        state['ok_active'] += 1
        state['ok_max'] = max(state['ok_max'], state['ok_active'])
        try:
            await asyncio.sleep(app['ok_delay'])
            return web.json_response({'status': '1', 'result': {'value': state['ok_total']}})
        finally:
            state['ok_active'] -= 1

    app.router.add_get('/429_once', handle_429_once)
    app.router.add_get('/429_sustained', handle_429_sustained)
    app.router.add_get('/timeout', handle_timeout)
    app.router.add_get('/forbidden', handle_forbidden)
    app.router.add_get('/ok', handle_ok)

    return app


@pytest.fixture
def fake_app() -> Any:
    """Provide the configured aiohttp application used by network retry tests."""

    return _build_fake_app()


@pytest.fixture
def fake_server(fake_app: Any) -> Iterator[FakeServer]:
    """Spin up an aiohttp server exposing deterministic retry/timeout behaviour."""

    pytest.importorskip('aiohttp')
    from aiohttp import web

    loop = asyncio.new_event_loop()
    try:
        current_loop = asyncio.get_event_loop()
    except RuntimeError:
        current_loop = None
    asyncio.set_event_loop(loop)

    runner = web.AppRunner(fake_app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, '127.0.0.1', 0)
    loop.run_until_complete(site.start())

    sockets = getattr(site._server, 'sockets', None)
    if not sockets:
        raise RuntimeError('Failed to determine bound port for fake server')
    port = sockets[0].getsockname()[1]

    server = FakeServer(base_url=f'http://127.0.0.1:{port}', state=fake_app['state'], loop=loop)
    try:
        yield server
    finally:
        loop.run_until_complete(runner.cleanup())
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        asyncio.set_event_loop(current_loop)


@pytest.fixture
def fake_base_url(fake_server: FakeServer) -> str:
    """Return the base URL for the in-process aiohttp test server."""

    return fake_server.base_url
