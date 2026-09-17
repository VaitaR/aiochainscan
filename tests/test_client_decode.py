"""The decode surface on the client: ABI resolution plus decoding, in one call."""

import json
from typing import Any

import pytest

from aiochainscan.core.mixins import DecodeMixin
from aiochainscan.domain.method import Method

PROXY = '0x1111111111111111111111111111111111111111'
IMPLEMENTATION = '0x2222222222222222222222222222222222222222'
PLAIN = '0x3333333333333333333333333333333333333333'
UNVERIFIED = '0x4444444444444444444444444444444444444444'
HOLDER = '0x5555555555555555555555555555555555555555'

ERC20_ABI = [
    {
        'type': 'function',
        'name': 'transfer',
        'inputs': [
            {'name': 'to', 'type': 'address'},
            {'name': 'value', 'type': 'uint256'},
        ],
        'outputs': [{'name': '', 'type': 'bool'}],
        'stateMutability': 'nonpayable',
    },
    {
        'type': 'event',
        'name': 'Transfer',
        'inputs': [
            {'indexed': True, 'name': 'from', 'type': 'address'},
            {'indexed': True, 'name': 'to', 'type': 'address'},
            {'indexed': False, 'name': 'value', 'type': 'uint256'},
        ],
    },
]

# transfer(address,uint256) — selector, recipient, 1_000_000
TRANSFER_CALLDATA = '0xa9059cbb' + '0' * 24 + HOLDER[2:] + f'{1_000_000:064x}'
TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'


class FakeHost(DecodeMixin):
    """A client stand-in that answers only the two ABI-resolution methods."""

    def __init__(
        self,
        *,
        abis: dict[str, list[dict[str, Any]]] | None = None,
        proxies: dict[str, str] | None = None,
    ) -> None:
        self._abis = {address.lower(): abi for address, abi in (abis or {}).items()}
        self._proxies = {a.lower(): impl for a, impl in (proxies or {}).items()}
        self.calls: list[tuple[Method, str]] = []

    async def call(self, method: Method, **params: Any) -> Any:
        address = str(params.get('address', '')).lower()
        self.calls.append((method, address))
        if method is Method.CONTRACT_SOURCE:
            implementation = self._proxies.get(address)
            if implementation is None:
                return [{'Proxy': '0'}]
            return [{'Proxy': '1', 'Implementation': implementation}]
        if method is Method.CONTRACT_ABI:
            abi = self._abis.get(address)
            if abi is None:
                raise ValueError('Contract source code not verified')
            return json.dumps(abi)
        raise AssertionError(f'unexpected method {method}')


@pytest.fixture
def host() -> FakeHost:
    return FakeHost(
        abis={IMPLEMENTATION: ERC20_ABI, PLAIN: ERC20_ABI},
        proxies={PROXY: IMPLEMENTATION},
    )


class TestDecodeInput:
    async def test_decodes_against_a_supplied_abi(self, host: FakeHost) -> None:
        decoded = await host.decode_input(TRANSFER_CALLDATA, abi=ERC20_ABI)

        assert decoded['decoded_func'] == 'transfer'
        assert decoded['decoded_data']['to'].lower() == HOLDER
        assert decoded['decoded_data']['value'] == 1_000_000
        assert host.calls == []

    async def test_accepts_the_abi_as_json(self, host: FakeHost) -> None:
        decoded = await host.decode_input(TRANSFER_CALLDATA, abi=json.dumps(ERC20_ABI))

        assert decoded['decoded_func'] == 'transfer'

    async def test_follows_a_proxy_to_the_decoding_abi(self, host: FakeHost) -> None:
        decoded = await host.decode_input(TRANSFER_CALLDATA, address=PROXY)

        assert decoded['decoded_func'] == 'transfer'
        assert (Method.CONTRACT_ABI, IMPLEMENTATION) in host.calls
        assert (Method.CONTRACT_ABI, PROXY) not in host.calls

    async def test_without_abi_or_address_it_says_which_to_pass(self, host: FakeHost) -> None:
        with pytest.raises(ValueError, match='abi=.*address='):
            await host.decode_input(TRANSFER_CALLDATA)

    async def test_unverified_contract_yields_no_function(self, host: FakeHost) -> None:
        decoded = await host.decode_input(TRANSFER_CALLDATA, address=UNVERIFIED)

        assert decoded == {'decoded_func': '', 'decoded_data': {}}


class TestDecodeTransactions:
    async def test_resolves_one_abi_per_destination(self, host: FakeHost) -> None:
        txs = [
            {'hash': f'0x{index:02x}', 'to': PROXY, 'input': TRANSFER_CALLDATA}
            for index in range(5)
        ]

        decoded = await host.decode_transactions(txs)

        assert [tx['decoded_func'] for tx in decoded] == ['transfer'] * 5
        assert sum(1 for method, _ in host.calls if method is Method.CONTRACT_ABI) == 1

    async def test_keeps_rows_it_cannot_decode(self, host: FakeHost) -> None:
        txs = [
            {'hash': '0x01', 'to': PLAIN, 'input': TRANSFER_CALLDATA},
            {'hash': '0x02', 'to': UNVERIFIED, 'input': TRANSFER_CALLDATA},
            {'hash': '0x03', 'to': None, 'input': '0x'},
        ]

        decoded = await host.decode_transactions(txs)

        assert [tx['hash'] for tx in decoded] == ['0x01', '0x02', '0x03']
        assert [tx['decoded_func'] for tx in decoded] == ['transfer', '', '']

    async def test_does_not_mutate_the_caller_s_records(self, host: FakeHost) -> None:
        txs = [{'hash': '0x01', 'to': PLAIN, 'input': TRANSFER_CALLDATA}]

        await host.decode_transactions(txs)

        assert txs == [{'hash': '0x01', 'to': PLAIN, 'input': TRANSFER_CALLDATA}]

    async def test_a_supplied_abi_skips_every_lookup(self, host: FakeHost) -> None:
        txs = [{'hash': '0x01', 'to': PROXY, 'input': TRANSFER_CALLDATA}]

        decoded = await host.decode_transactions(txs, abi=ERC20_ABI)

        assert decoded[0]['decoded_func'] == 'transfer'
        assert host.calls == []

    async def test_empty_input_is_an_empty_result(self, host: FakeHost) -> None:
        assert await host.decode_transactions([]) == []


class TestDecodeLogs:
    async def test_decodes_against_the_emitter_s_abi(self, host: FakeHost) -> None:
        logs = [
            {
                'address': PROXY,
                'topics': [
                    TRANSFER_TOPIC,
                    '0x' + '0' * 24 + PLAIN[2:],
                    '0x' + '0' * 24 + HOLDER[2:],
                ],
                'data': f'0x{1_000_000:064x}',
            }
        ]

        decoded = await host.decode_logs(logs)

        assert decoded[0]['decoded_data']['value'] == 1_000_000
        assert 'decoded_data' not in logs[0]

    async def test_an_undeclared_event_is_left_alone(self, host: FakeHost) -> None:
        logs = [{'address': PLAIN, 'topics': ['0x' + 'ab' * 32], 'data': '0x'}]

        decoded = await host.decode_logs(logs)

        assert 'decoded_data' not in decoded[0]
