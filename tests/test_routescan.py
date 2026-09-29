"""Offline contract tests for the Routescan scanner."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from aiochainscan import ChainscanClient
from aiochainscan.chain_registry import resolve_scanner_target
from aiochainscan.domain.method import Method
from aiochainscan.scanners import get_scanner_class
from aiochainscan.scanners.routescan_v2 import RoutescanV2
from tests.conftest import FakeNetwork


@pytest.mark.parametrize(
    ('chain_id', 'network', 'expected_path'),
    [
        (1, 'ethereum', 'mainnet/evm/1'),
        (43114, 'avalanche', 'mainnet/evm/43114'),
        (9745, 'plasma', 'mainnet/evm/9745'),
    ],
)
def test_routescan_url_shape(chain_id: int, network: str, expected_path: str) -> None:
    scanner = RoutescanV2(
        api_key='',
        network=network,
        url_builder=MagicMock(),
        chain_id=chain_id,
        network_client=FakeNetwork(response={}),
    )

    request = scanner._build_request(scanner.SPECS[Method.CONTRACT_SOURCE], address='0xabc')

    assert request['url'] == f'https://api.routescan.io/v2/network/{expected_path}/etherscan/api'
    assert request['params']['module'] == 'contract'
    assert request['params']['action'] == 'getsourcecode'
    assert request['params']['address'] == '0xabc'
    assert request['headers'] == {}


def test_routescan_optional_key_uses_header() -> None:
    scanner = RoutescanV2(
        api_key='registered-key',
        network='avalanche',
        url_builder=MagicMock(),
        chain_id=43114,
        network_client=FakeNetwork(response={}),
    )

    request = scanner._build_request(scanner.SPECS[Method.CONTRACT_SOURCE], address='0xabc')

    assert request['headers'] == {'apikey': 'registered-key'}
    assert 'apikey' not in request['params']


def test_routescan_is_registered_as_v2() -> None:
    assert get_scanner_class('routescan', 'v2') is RoutescanV2


def test_routescan_refuses_unverified_mode_chain() -> None:
    with pytest.raises(ValueError, match='not supported'):
        resolve_scanner_target('routescan', 'mode')


@pytest.mark.asyncio
async def test_routescan_default_limiter_is_conservative() -> None:
    client = ChainscanClient.from_config('routescan', 43114, api_key='')
    try:
        limiter: Any = client._network._rate_limiter
        assert limiter.max_rate == 1.0
        assert limiter.max_burst == 1.0
    finally:
        await client.close()
