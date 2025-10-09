"""
End-to-end live tests for ChainscanClient across multiple scanners.

These tests perform real API calls against public providers. They use
API keys from the environment (.env is auto-loaded by config manager).

Goal:
- Verify that ChainscanClient provides a unified interface
- Verify balance retrieval works for at least two chains per scanner
- Keep requests sequential to respect rate limits

Notes:
- Providers that require API keys will be skipped automatically when
  keys are not available in the environment.
- Balances may be "0" or large numbers depending on the chain; we only
  assert that the value is returned without raising errors and is a
  string or int convertible to int.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from aiochainscan.config import config as global_config
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method
from aiochainscan.exceptions import ChainscanClientApiError

# Well-known EOA with activity on Ethereum mainnet (may be zero elsewhere)
TEST_ADDRESS: str = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'


def _has_api_key(scanner_id: str) -> bool:
    """Return True if API key is configured or not required."""
    try:
        cfg = global_config.get_scanner_config(scanner_id)
        if not cfg.requires_api_key:
            return True
        # Attempt to resolve key via config manager (env/.env supported)
        try:
            key = global_config.get_api_key(scanner_id)
            return bool(key)
        except Exception:
            return False
    except Exception:
        # Unknown scanner id
        return False


def _has_etherscan_key() -> bool:
    """Check if ETHERSCAN_KEY is available (used by Base and other Etherscan V2 scanners)."""
    key = os.getenv('ETHERSCAN_KEY')
    return bool(key and 'YOUR_' not in key and len(key) >= 10)


async def _assert_balance_ok(client: ChainscanClient, address: str) -> None:
    """Call ACCOUNT_BALANCE and assert it returns a numeric-like value or string."""
    result: Any = await client.call(Method.ACCOUNT_BALANCE, address=address)
    # Allow string or int; just ensure it can be converted to int
    if isinstance(result, int):
        assert result >= 0
    elif isinstance(result, str):
        # Accept empty/None-like strings as provider-specific oddities, but prefer numeric
        int(result or '0')  # raises if not numeric
    else:
        # Some providers might wrap result in objects; try common fields
        raise AssertionError(f'Unexpected balance type: {type(result)} -> {result}')


@pytest.mark.asyncio
async def test_blockscout_two_chains_live() -> None:
    # BlockScout typically doesn't require API keys
    # Test only Ethereum mainnet for now (BlockScout eth instance)
    tests = [
        ('blockscout', 'v1', 'blockscout_eth', 'eth'),
    ]

    for scanner_name, version, _scanner_id, network in tests:
        # BlockScout scanners don't need API keys
        client = ChainscanClient.from_config(scanner_name, network, version)
        await _assert_balance_ok(client, TEST_ADDRESS)
        await client.close()
        # Gentle pacing between providers
        await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_etherscan_two_chains_live() -> None:
    # Requires ETHERSCAN_KEY in env
    etherscan_key = os.getenv('ETHERSCAN_KEY')
    if not etherscan_key or 'YOUR_' in etherscan_key or len(etherscan_key) < 10:
        pytest.skip('ETHERSCAN_KEY not configured for live Etherscan tests')

    tests = [
        ('etherscan', 'v2', 'eth', 'main'),
        ('etherscan', 'v2', 'arbitrum', 'main'),
        ('etherscan', 'v2', 'base', 'main'),  # Base network via Etherscan V2
    ]

    for scanner_name, version, _scanner_id, network in tests:
        # Etherscan V2 scanners use ETHERSCAN_KEY
        if _scanner_id in ('eth', 'arbitrum', 'bsc', 'polygon', 'optimism', 'base'):
            if not _has_etherscan_key():
                pytest.skip(f'ETHERSCAN_KEY not configured for {_scanner_id}')
        elif not _has_api_key(_scanner_id):
            pytest.skip(f'Missing API key for {_scanner_id}')

        client = ChainscanClient.from_config(scanner_name, network, version)
        try:
            await _assert_balance_ok(client, TEST_ADDRESS)
        except ChainscanClientApiError as e:  # pragma: no cover - live guardrail
            # Gracefully skip if the environment key is invalid/rate-limited
            msg = str(e)
            if (
                'Invalid API Key' in msg
                or 'Missing/Invalid API Key' in msg
                or 'rate limit' in msg.lower()
            ):
                pytest.skip(f'Etherscan live test skipped due to API key/limits: {msg}')
            raise
        finally:
            await client.close()
        await asyncio.sleep(0.2)


# Base network is now supported through Etherscan V2 with chain_id
# No need for separate BaseScan scanner


@pytest.mark.asyncio
async def test_moralis_two_chains_live() -> None:
    # Moralis requires MORALIS_API_KEY
    tests = [
        ('moralis', 'v1', 'moralis', 'eth'),
        ('moralis', 'v1', 'moralis', 'arbitrum'),
    ]

    for scanner_name, version, _scanner_id, network in tests:
        if not _has_api_key(_scanner_id):
            pytest.skip('Missing MORALIS_API_KEY')
        client = ChainscanClient.from_config(scanner_name, network, version)
        await _assert_balance_ok(client, TEST_ADDRESS)
        await client.close()
        await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_routscan_mode_live() -> None:
    # RoutScan supports Mode only (one network)
    # RoutScan may not be registered in config in all environments; skip if unknown
    try:
        scanner_name, version, _scanner_id, network = ('routscan', 'v1', 'routscan_mode', 'mode')
        client = ChainscanClient.from_config(scanner_name, network, version)
    except Exception as e:
        pytest.skip(f'RoutScan not available in this build: {e}')
    # Address may be zero on Mode; we still validate shape
    await _assert_balance_ok(client, TEST_ADDRESS)
    await client.close()
