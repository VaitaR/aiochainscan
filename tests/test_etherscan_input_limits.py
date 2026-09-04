"""Wire-spelling and doc-declared input-limit tests for the Etherscan-like scanner.

Covers two unrelated fixes bundled in the same change:

1. ``CONTRACT_VERIFY`` wire param names realigned to the current
   ``verifysourcecode`` docs (``constructorArguments`` / ``evmVersion`` /
   ``licenseType`` instead of the legacy ``constructorArguements`` /
   lowercase ``evmversion`` / a missing license param).
2. Client-side refusal of two doc-declared input ceilings we used to let
   sail through to the API unchecked: ``getcontractcreation`` (up to 5
   addresses) and ``topholders`` (``offset`` up to 1000).

No live HTTP: ``FakeNetwork`` records the outgoing request/data, mirroring
``tests/test_new_spec_endpoints.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from aiochainscan.core.url_builder import UrlBuilder
from aiochainscan.domain.method import Method
from aiochainscan.exceptions import InputLimitExceededError
from aiochainscan.scanners.etherscan_v2 import EtherscanV2
from tests.conftest import FakeNetwork


def _etherscan(network: FakeNetwork) -> EtherscanV2:
    return EtherscanV2(
        api_key='test_key',
        network='main',
        url_builder=UrlBuilder('test_key', 'eth', 'main'),
        network_client=network,
    )


def _wire_data(fake: FakeNetwork) -> dict[str, Any]:
    assert len(fake.calls) == 1, f'expected one request, saw {fake.calls!r}'
    return dict(fake.calls[0]['data'])


def _wire_params(fake: FakeNetwork) -> dict[str, Any]:
    assert len(fake.calls) == 1, f'expected one request, saw {fake.calls!r}'
    return dict(fake.calls[0]['params'])


# ---------------------------------------------------------------------------
# Part 1: CONTRACT_VERIFY wire spellings
# ---------------------------------------------------------------------------


class TestContractVerifyWireSpellings:
    async def test_constructor_arguments_uses_documented_spelling(self) -> None:
        fake = FakeNetwork(response={'result': 'guid-123'})
        await _etherscan(fake).call(
            Method.CONTRACT_VERIFY,
            contract_address='0x1234567890123456789012345678901234567890',
            source_code='contract C {}',
            code_format='solidity-single-file',
            contract_name='C',
            compiler_version='v0.8.20+commit.a1b79de6',
            optimization_used='0',
            runs='200',
            constructor_arguments='deadbeef',
        )
        data = _wire_data(fake)
        assert data['constructorArguments'] == 'deadbeef'
        assert (
            'constructorArguements' not in data
        ), 'legacy misspelling must not be sent once the documented spelling is used'

    async def test_evm_version_uses_documented_spelling(self) -> None:
        fake = FakeNetwork(response={'result': 'guid-123'})
        await _etherscan(fake).call(
            Method.CONTRACT_VERIFY,
            contract_address='0x1234567890123456789012345678901234567890',
            source_code='contract C {}',
            code_format='solidity-single-file',
            contract_name='C',
            compiler_version='v0.8.20+commit.a1b79de6',
            optimization_used='0',
            runs='200',
            evm_version='paris',
        )
        data = _wire_data(fake)
        assert data['evmVersion'] == 'paris'
        assert (
            'evmversion' not in data
        ), 'lowercase evmversion must not be sent once evmVersion is used'

    async def test_license_type_threads_to_wire(self) -> None:
        fake = FakeNetwork(response={'result': 'guid-123'})
        await _etherscan(fake).call(
            Method.CONTRACT_VERIFY,
            contract_address='0x1234567890123456789012345678901234567890',
            source_code='contract C {}',
            code_format='solidity-single-file',
            contract_name='C',
            compiler_version='v0.8.20+commit.a1b79de6',
            optimization_used='0',
            runs='200',
            license_type='3',
        )
        data = _wire_data(fake)
        assert data['licenseType'] == '3'

    async def test_public_param_names_unchanged(self) -> None:
        """The public (client-facing) param names must stay stable — only the
        wire spellings changed."""
        fake = FakeNetwork(response={'result': 'guid-123'})
        await _etherscan(fake).call(
            Method.CONTRACT_VERIFY,
            contract_address='0x1234567890123456789012345678901234567890',
            source_code='contract C {}',
            code_format='solidity-single-file',
            contract_name='C',
            compiler_version='v0.8.20+commit.a1b79de6',
            optimization_used='0',
            runs='200',
            constructor_arguments='deadbeef',
            evm_version='paris',
            license_type='3',
        )
        data = _wire_data(fake)
        assert data['constructorArguments'] == 'deadbeef'
        assert data['evmVersion'] == 'paris'
        assert data['licenseType'] == '3'


# ---------------------------------------------------------------------------
# Part 2: doc-declared input limits
# ---------------------------------------------------------------------------


class TestContractCreationAddressLimit:
    async def test_five_addresses_pass_through_unchanged(self) -> None:
        addresses = ','.join(f'0x{i:040x}' for i in range(1, 6))
        fake = FakeNetwork(response={'result': []})
        result = await _etherscan(fake).call(
            Method.CONTRACT_CREATION, contract_addresses=addresses
        )
        assert result == []
        params = _wire_params(fake)
        assert params['contractaddresses'] == addresses

    async def test_six_addresses_raises_before_any_request(self) -> None:
        addresses = ','.join(f'0x{i:040x}' for i in range(1, 7))
        fake = FakeNetwork(response={'result': []})
        with pytest.raises(InputLimitExceededError) as exc_info:
            await _etherscan(fake).call(Method.CONTRACT_CREATION, contract_addresses=addresses)
        assert exc_info.value.limit == 5
        assert exc_info.value.provided == 6
        assert '5' in str(exc_info.value)
        assert '6' in str(exc_info.value)
        assert fake.calls == [], 'the oversized request must never reach the network'

    async def test_list_input_is_also_counted(self) -> None:
        addresses = [f'0x{i:040x}' for i in range(1, 7)]
        fake = FakeNetwork(response={'result': []})
        with pytest.raises(InputLimitExceededError):
            await _etherscan(fake).call(Method.CONTRACT_CREATION, contract_addresses=addresses)


class TestTopHoldersLimit:
    async def test_offset_at_1000_passes_through_unchanged(self) -> None:
        fake = FakeNetwork(response={'result': []})
        result = await _etherscan(fake).call(
            Method.TOKEN_TOP_HOLDERS,
            contract_address='0x1234567890123456789012345678901234567890',
            offset=1000,
        )
        assert result == []
        params = _wire_params(fake)
        assert params['offset'] == 1000

    async def test_offset_at_1001_raises_before_any_request(self) -> None:
        fake = FakeNetwork(response={'result': []})
        with pytest.raises(InputLimitExceededError) as exc_info:
            await _etherscan(fake).call(
                Method.TOKEN_TOP_HOLDERS,
                contract_address='0x1234567890123456789012345678901234567890',
                offset=1001,
            )
        assert exc_info.value.limit == 1000
        assert exc_info.value.provided == 1001
        assert fake.calls == [], 'the oversized request must never reach the network'
