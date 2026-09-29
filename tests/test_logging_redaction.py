"""Credential redaction for third-party HTTP request log records."""

from __future__ import annotations

import logging

import httpx
import pytest

from aiochainscan import ChainscanClient
from aiochainscan._redaction import _HTTP_LOG_FILTER, install_http_logging_filter

SECRET = 'SECRETKEY123'


def _client_with_mock_transport() -> ChainscanClient:
    client = ChainscanClient.from_config('etherscan', 'ethereum', api_key=SECRET)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={'status': '1', 'message': 'OK', 'result': '42'},
            request=request,
        )

    client._network._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.mark.asyncio
async def test_httpx_request_record_redacts_query_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client_with_mock_transport()
    try:
        with caplog.at_level(logging.INFO, logger='httpx'):
            assert await client.get_balance('0x0000000000000000000000000000000000000001') == '42'

        records = [record for record in caplog.records if record.name == 'httpx']
        assert records
        assert all(SECRET not in record.getMessage() for record in records)
        assert any('HTTP Request:' in record.getMessage() for record in records)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_httpx_request_record_leaks_without_redaction_filter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger('httpx')
    client = _client_with_mock_transport()
    original_filters = list(logger.filters)
    for existing in original_filters:
        logger.removeFilter(existing)
    try:
        caplog.clear()
        with caplog.at_level(logging.INFO, logger='httpx'):
            assert await client.get_balance('0x0000000000000000000000000000000000000001') == '42'

        records = [record for record in caplog.records if record.name == 'httpx']
        assert records
        assert any(SECRET in record.getMessage() for record in records)
    finally:
        for existing in original_filters:
            logger.addFilter(existing)
        await client.close()


@pytest.mark.asyncio
async def test_httpx_redaction_filter_is_a_singleton() -> None:
    logger = logging.getLogger('httpx')
    install_http_logging_filter()
    install_http_logging_filter()
    client = _client_with_mock_transport()
    try:
        assert [existing for existing in logger.filters if existing is _HTTP_LOG_FILTER] == [
            _HTTP_LOG_FILTER
        ]
    finally:
        await client.close()
