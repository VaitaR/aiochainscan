"""Offline verdict tests for the BlockScout host probe."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'agent' / 'probe_blockscout_hosts.py'


@pytest.fixture()
def probe_module() -> Any:
    spec = importlib.util.spec_from_file_location('probe_blockscout_hosts_under_test', _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault('probe_blockscout_hosts_under_test', module)
    spec.loader.exec_module(module)
    module.RETRY_DELAYS = ()
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('rpc_status', 'rpc_body', 'rpc_text', 'expected_rpc', 'expected_verdict'),
    [
        pytest.param(
            200,
            {
                'jsonrpc': '2.0',
                'id': 1,
                'error': {'code': -32005, 'message': 'Max calls rate limit reached'},
                'result': None,
            },
            None,
            'throttled',
            'INCONCLUSIVE',
            id='http-200-rate-limit-message-with-null-result',
        ),
        pytest.param(
            200,
            {
                'jsonrpc': '2.0',
                'id': 1,
                'error': {'code': 429, 'message': 'Request rejected'},
                'result': None,
            },
            None,
            'throttled',
            'INCONCLUSIVE',
            id='http-200-rate-limit-code-with-null-result',
        ),
        pytest.param(
            429,
            {'error': {'code': 429, 'message': 'Too many requests'}},
            None,
            'throttled',
            'INCONCLUSIVE',
            id='http-429',
        ),
        pytest.param(
            200,
            {'jsonrpc': '2.0', 'id': 1, 'result': '0x1'},
            None,
            'ok',
            'OK',
            id='matching-chain-id',
        ),
        pytest.param(
            200,
            {'jsonrpc': '2.0', 'id': 1, 'result': '0x2'},
            None,
            'chain-id-mismatch',
            'FAIL',
            id='mismatched-chain-id',
        ),
        pytest.param(
            200,
            {'jsonrpc': '2.0', 'id': 1, 'result': None},
            None,
            'error:TypeError',
            'FAIL',
            id='unrelated-null-result',
        ),
        pytest.param(
            200,
            {
                'jsonrpc': '2.0',
                'id': 1,
                'error': {'code': -32000, 'message': 'execution reverted'},
                'result': None,
            },
            None,
            'error:JSONRPCError',
            'FAIL',
            id='unrelated-json-rpc-error',
        ),
        pytest.param(
            200,
            {
                'jsonrpc': '2.0',
                'id': 1,
                'error': {'code': -32005, 'message': 'query exceeds the result limit'},
                'result': None,
            },
            None,
            'error:JSONRPCError',
            'FAIL',
            id='result-size-limit-is-not-rate-limit',
        ),
        pytest.param(
            200,
            None,
            'not-json',
            'error:JSONDecodeError',
            'FAIL',
            id='malformed-json',
        ),
    ],
)
async def test_probe_host_rpc_verdict(
    probe_module: Any,
    rpc_status: int,
    rpc_body: dict[str, Any] | None,
    rpc_text: str | None,
    expected_rpc: str,
    expected_verdict: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/api':
            return httpx.Response(200, json={'status': '1'}, request=request)
        if request.url.path == '/api/v2/stats':
            return httpx.Response(200, json={'total_blocks': 1}, request=request)
        if rpc_text is not None:
            return httpx.Response(
                rpc_status,
                text=rpc_text,
                headers={'content-type': 'application/json'},
                request=request,
            )
        return httpx.Response(rpc_status, json=rpc_body, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_module.probe_host(client, 1, 'fixture.example')

    assert result.verdict == expected_verdict
    assert result.rpc == expected_rpc
