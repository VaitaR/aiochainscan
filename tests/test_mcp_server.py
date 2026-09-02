"""MCP server revamp (P0.4): envelope, opaque cursors, curation, curated tools.

The agent-facing tool logic lives in :mod:`aiochainscan.mcp.tools` as plain
``client -> ToolResponse`` functions (no ``mcp`` dependency), so the whole
surface below runs offline against stub clients. FastMCP registration tests
are guarded with ``importorskip`` and only run under ``uv run --extra mcp``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from aiochainscan.domain.method import Method
from aiochainscan.exceptions import ChainscanClientApiError
from aiochainscan.mcp import tools as mcp_tools
from aiochainscan.mcp.abi_codec import (
    canonical_signature,
    decode_arguments,
    encode_arguments,
    selector,
)
from aiochainscan.mcp.cursors import (
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from aiochainscan.mcp.envelope import (
    DEFAULT_PAGE_SIZE,
    STRING_TRUNCATION_LIMIT,
    build_tool_response,
    format_units,
    truncate_long_strings,
)

WALLET = '0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed'
WALLET_OTHER = '0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359'
TOKEN = '0xdAC17F958D2ee523a2206206994597C13D831ec7'
TX_HASH = '0x' + 'ab' * 32
TRANSFER_ABI = [
    {
        'type': 'function',
        'name': 'transfer',
        'inputs': [
            {'name': 'to', 'type': 'address'},
            {'name': 'amount', 'type': 'uint256'},
        ],
        'outputs': [{'name': '', 'type': 'bool'}],
        'stateMutability': 'nonpayable',
    }
]
BALANCE_OF_ABI = [
    {
        'type': 'function',
        'name': 'balanceOf',
        'inputs': [{'name': 'owner', 'type': 'address'}],
        'outputs': [{'name': 'balance', 'type': 'uint256'}],
        'stateMutability': 'view',
    }
]


def eth_tx(block: int = 100, value: str = '1000000000000000000', **over: Any) -> dict[str, Any]:
    """Etherscan-shaped transaction item."""
    tx: dict[str, Any] = {
        'hash': '0x' + f'{block:064x}',
        'from': WALLET,
        'to': WALLET_OTHER,
        'value': value,
        'blockNumber': str(block),
        'timeStamp': '1700000000',
        'isError': '0',
        'input': '0x',
    }
    tx.update(over)
    return tx


class StubClient:
    """Offline stand-in exposing only the surface the MCP tools consume."""

    def __init__(self, *, currency: str = 'ETH') -> None:
        self.currency = currency
        self.scanner_name = 'blockscout'
        self.get_balance = _AsyncReturner('1500000000000000000')
        self.get_transactions = _AsyncReturner([])
        self.get_transaction = _AsyncReturner({})
        self.get_transaction_status = _AsyncReturner({})
        self.get_token_portfolio = _AsyncReturner([])
        self.get_nft_portfolio = _AsyncReturner([])
        self.get_token_info = _AsyncReturner({})
        self.get_token_holder_count = _AsyncReturner(0)
        self.get_contract_abi = _AsyncReturner('[]')
        self.eth_call = _AsyncReturner('0x')
        self.resolve_name = _AsyncReturner(None)
        self.lookup_address = _AsyncReturner(None)
        self.fetch_page = _AsyncReturner(([], None))
        self._supported: set[Method] = set()

    def supports_method(self, method: Method) -> bool:
        return method in self._supported

    def support(self, *methods: Method) -> StubClient:
        self._supported.update(methods)
        return self

    async def close(self) -> None:
        self.closed = True


class _AsyncReturner:
    """Callable returning a preset value; swap ``.value`` or set ``.error``."""

    def __init__(self, value: Any) -> None:
        self.value = value
        self.error: Exception | None = None
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append({'args': args, 'kwargs': kwargs})
        if self.error is not None:
            raise self.error
        return self.value


# ============================================================================
# Envelope
# ============================================================================


class TestEnvelope:
    def test_payload_excludes_content_text(self) -> None:
        response = build_tool_response(
            data={'x': 1},
            notes=['n'],
            instructions=['i'],
            content_text='summary',
        )
        payload = response.to_payload()
        assert set(payload) == {'data', 'notes', 'instructions', 'pagination'}
        assert payload['data'] == {'x': 1}
        assert payload['notes'] == ['n']
        assert payload['instructions'] == ['i']
        assert payload['pagination'] is None
        assert response.content_text == 'summary'

    def test_defaults_are_none(self) -> None:
        payload = build_tool_response(data=1).to_payload()
        assert payload['notes'] is None
        assert payload['instructions'] is None
        assert payload['pagination'] is None

    def test_pagination_payload_shape(self) -> None:
        from aiochainscan.mcp.envelope import NextCall, Pagination

        pagination = Pagination(
            has_more=True,
            items_shown=5,
            next_cursor='tok',
            next_call=NextCall(
                tool='get_transactions', params={'address': WALLET, 'cursor': 'tok'}
            ),
        )
        payload = build_tool_response(data=[], pagination=pagination).to_payload()
        assert payload['pagination'] == {
            'has_more': True,
            'items_shown': 5,
            'next_cursor': 'tok',
            'total': None,
            'next_call': {
                'tool': 'get_transactions',
                'params': {'address': WALLET, 'cursor': 'tok'},
            },
        }

    def test_pagination_auto_adds_instructions(self) -> None:
        from aiochainscan.mcp.envelope import NextCall, Pagination

        pagination = Pagination(
            has_more=True,
            items_shown=5,
            next_cursor='tok',
            next_call=NextCall(tool='t', params={}),
        )
        response = build_tool_response(data=[], pagination=pagination, instructions=['first'])
        assert response.instructions is not None
        assert response.instructions[0] == 'first'
        assert any('next_call' in item for item in response.instructions)

    def test_exhausted_pagination_adds_no_instructions(self) -> None:
        from aiochainscan.mcp.envelope import Pagination

        pagination = Pagination(has_more=False, items_shown=5, next_cursor=None, next_call=None)
        response = build_tool_response(data=[], pagination=pagination)
        assert response.instructions is None


class TestFormatUnits:
    def test_one_ether(self) -> None:
        assert format_units('1000000000000000000', 18) == '1'

    def test_fraction(self) -> None:
        assert format_units('1234500000000000000', 18) == '1.2345'

    def test_small(self) -> None:
        assert format_units('1', 18) == '0.000000000000000001'

    def test_zero(self) -> None:
        assert format_units('0', 18) == '0'

    def test_zero_int(self) -> None:
        assert format_units(0, 6) == '0'

    def test_six_decimals(self) -> None:
        assert format_units('1234567', 6) == '1.234567'

    def test_negative_truncates_toward_zero(self) -> None:
        """Regression: floor division produced '-2.5' for -1500 at 3 decimals."""
        assert format_units(-1500, 3) == '-1.5'
        assert format_units('-1500', 3) == '-1.5'

    def test_negative_exact_whole(self) -> None:
        assert format_units(-2000, 3) == '-2'
        assert format_units('-1000000000000000000', 18) == '-1'

    def test_negative_fraction(self) -> None:
        assert format_units('-1234500000000000000', 18) == '-1.2345'

    def test_invalid_falls_back_to_raw(self) -> None:
        assert format_units('not-a-number', 18) == 'not-a-number'


class TestTruncation:
    def test_short_string_untouched(self) -> None:
        assert truncate_long_strings('short')[0] == 'short'

    def test_long_string_flagged(self) -> None:
        value = 'x' * (STRING_TRUNCATION_LIMIT + 10)
        processed, truncated = truncate_long_strings(value)
        assert truncated is True
        assert processed == {
            'value_sample': 'x' * STRING_TRUNCATION_LIMIT,
            'value_truncated': True,
        }

    def test_nested_structures(self) -> None:
        value = {'items': [{'data': 'y' * (STRING_TRUNCATION_LIMIT + 1)}], 'keep': 'ok'}
        processed, truncated = truncate_long_strings(value)
        assert truncated is True
        assert processed['keep'] == 'ok'
        assert isinstance(processed['items'][0]['data'], dict)

    def test_scalars_pass_through(self) -> None:
        assert truncate_long_strings([1, True, None])[0] == [1, True, None]


# ============================================================================
# Cursors
# ============================================================================


class TestCursors:
    def test_roundtrip(self) -> None:
        payload = {'page': 3, 'offset': 50, 'text': 'välue'}
        assert decode_cursor(encode_cursor(payload)) == {**payload, 'v': 1}

    def test_encoded_cursor_is_urlsafe(self) -> None:
        token = encode_cursor({'page': 2})
        assert '=' not in token and '+' not in token and '/' not in token

    def test_invalid_token_raises(self) -> None:
        with pytest.raises(InvalidCursorError):
            decode_cursor('%%%not-base64%%%')

    def test_valid_base64_invalid_json_raises(self) -> None:
        import base64

        token = base64.urlsafe_b64encode(b'not json').decode()
        with pytest.raises(InvalidCursorError):
            decode_cursor(token)

    def test_empty_token_raises(self) -> None:
        with pytest.raises(InvalidCursorError):
            decode_cursor('')


# ============================================================================
# ABI codec
# ============================================================================


class TestAbiCodecSelectors:
    def test_balance_of_selector(self) -> None:
        inputs = [{'name': 'owner', 'type': 'address'}]
        assert selector('balanceOf', inputs) == '0x70a08231'

    def test_transfer_selector(self) -> None:
        inputs = [{'name': 'to', 'type': 'address'}, {'name': 'amount', 'type': 'uint256'}]
        assert selector('transfer', inputs) == '0xa9059cbb'

    def test_canonical_signature(self) -> None:
        inputs = [{'name': 'a', 'type': 'uint'}, {'name': 'b', 'type': 'bytes32[]'}]
        assert canonical_signature('f', inputs) == 'f(uint256,bytes32[])'


class TestAbiCodecEncode:
    def test_static_types_golden(self) -> None:
        inputs = [
            {'name': 'a', 'type': 'uint256'},
            {'name': 'b', 'type': 'address'},
            {'name': 'c', 'type': 'bool'},
        ]
        encoded = encode_arguments(inputs, [1, '0x' + '11' * 20, True])
        assert encoded == (
            (1).to_bytes(32, 'big')
            + bytes(12)
            + bytes.fromhex('11' * 20)
            + (1).to_bytes(32, 'big')
        )

    def test_numeric_string_coerced(self) -> None:
        encoded = encode_arguments([{'type': 'uint128'}], ['42'])
        assert encoded == (42).to_bytes(32, 'big')

    def test_string_encoding(self) -> None:
        encoded = encode_arguments([{'type': 'string'}], ['hi'])
        assert encoded == (
            (32).to_bytes(32, 'big') + (2).to_bytes(32, 'big') + b'hi'.ljust(32, b'\x00')
        )

    def test_dynamic_array(self) -> None:
        encoded = encode_arguments([{'type': 'uint256[]'}], [[1, 2]])
        assert encoded == (
            (32).to_bytes(32, 'big')
            + (2).to_bytes(32, 'big')
            + (1).to_bytes(32, 'big')
            + (2).to_bytes(32, 'big')
        )

    def test_fixed_bytes_right_padded(self) -> None:
        encoded = encode_arguments([{'type': 'bytes4'}], ['0xdeadbeef'])
        assert encoded == bytes.fromhex('deadbeef') + bytes(28)

    def test_arity_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match='2 argument'):
            encode_arguments([{'type': 'address'}, {'type': 'uint256'}], [WALLET])


class TestAbiCodecDecode:
    def test_uint_roundtrip(self) -> None:
        outputs = [{'name': 'balance', 'type': 'uint256'}]
        data = encode_arguments(outputs, [123456789012345678901234567890])
        assert decode_arguments(outputs, data) == {'balance': '123456789012345678901234567890'}

    def test_named_tuple_decodes_to_dict(self) -> None:
        outputs = [
            {
                'name': 'point',
                'type': 'tuple',
                'components': [
                    {'name': 'x', 'type': 'uint256'},
                    {'name': 'y', 'type': 'uint256'},
                ],
            }
        ]
        data = encode_arguments(outputs, [{'x': 1, 'y': 2}])
        assert decode_arguments(outputs, data) == {'point': {'x': '1', 'y': '2'}}

    def test_unnamed_output_indexed(self) -> None:
        outputs = [{'name': '', 'type': 'address'}]
        data = encode_arguments(outputs, [WALLET])
        assert decode_arguments(outputs, data) == {'0': WALLET.lower()}

    def test_string_roundtrip(self) -> None:
        outputs = [{'name': 's', 'type': 'string'}]
        data = encode_arguments(outputs, ['héllo'])
        assert decode_arguments(outputs, data) == {'s': 'héllo'}

    def test_bytes_roundtrip(self) -> None:
        outputs = [{'name': 'b', 'type': 'bytes'}]
        data = encode_arguments(outputs, ['0xdeadbeef01'])
        assert decode_arguments(outputs, data) == {'b': '0xdeadbeef01'}

    def test_dynamic_array_roundtrip(self) -> None:
        outputs = [{'name': 'xs', 'type': 'uint256[]'}]
        data = encode_arguments(outputs, [[3, 4, 5]])
        assert decode_arguments(outputs, data) == {'xs': ['3', '4', '5']}

    def test_trailing_garbage_rejected(self) -> None:
        outputs = [{'name': 'a', 'type': 'uint256'}]
        with pytest.raises(ValueError):
            decode_arguments(outputs, bytes(64))


class TestAbiCodecAgainstEthAbi:
    """Cross-check the pure-Python codec against eth-abi (dev/fallback extra)."""

    def test_encode_matches_eth_abi(self) -> None:
        eth_abi = pytest.importorskip('eth_abi')
        cases: list[tuple[list[dict[str, Any]], list[Any], list[str]]] = [
            (
                [{'type': 'uint256'}, {'type': 'int8'}, {'type': 'bool'}],
                [2**200, -3, False],
                ['uint256', 'int8', 'bool'],
            ),
            (
                [{'type': 'string'}, {'type': 'bytes'}],
                ['hello', b'\x01\x02'],
                ['string', 'bytes'],
            ),
            (
                [{'type': 'uint256[]'}, {'type': 'address'}],
                [[1, 2, 3], WALLET],
                ['uint256[]', 'address'],
            ),
            (
                [{'type': 'bytes4'}, {'type': 'bytes32'}],
                [b'\xaa\xbb\xcc\xdd', b'\x11' * 32],
                ['bytes4', 'bytes32'],
            ),
            (
                [
                    {
                        'type': 'tuple',
                        'components': [{'type': 'uint256'}, {'type': 'string'}],
                    }
                ],
                [[7, 'seven']],
                ['(uint256,string)'],
            ),
            (
                [{'type': 'uint8[3]'}],
                [[1, 2, 3]],
                ['uint8[3]'],
            ),
        ]
        for inputs, values, types in cases:
            ours = encode_arguments(inputs, values)
            theirs = eth_abi.encode(types, values)
            assert ours == theirs, f'mismatch for {types}'

    def test_decode_matches_eth_abi(self) -> None:
        eth_abi = pytest.importorskip('eth_abi')
        types = ['uint256', 'string', 'uint256[]']
        values = [5, 'abc', [9, 8]]
        data = eth_abi.encode(types, values)
        outputs = [{'name': str(i), 'type': t} for i, t in enumerate(types)]
        decoded = decode_arguments(outputs, data)
        expected = eth_abi.decode(types, data)
        assert [decoded['0'], decoded['1'], decoded['2']] == [
            str(expected[0]),
            expected[1],
            [str(v) for v in expected[2]],
        ]


# ============================================================================
# Tools
# ============================================================================


class TestGetWalletBalance:
    async def test_happy(self) -> None:
        client = StubClient()
        response = await mcp_tools.get_wallet_balance(client, WALLET)
        assert response.data is not None
        assert response.data['balance_wei'] == '1500000000000000000'
        assert response.data['balance'] == '1.5'
        assert response.data['currency'] == 'ETH'
        assert '1.5' in (response.content_text or '')

    async def test_zero(self) -> None:
        client = StubClient()
        client.get_balance.value = '0'
        response = await mcp_tools.get_wallet_balance(client, WALLET)
        assert response.data is not None and response.data['balance'] == '0'
        assert 'no' in (response.content_text or '').lower()


class TestGetAddressOverview:
    async def test_happy(self) -> None:
        client = StubClient()
        client.get_transactions.value = [eth_tx(), eth_tx(block=101)]
        client.get_token_portfolio.value = [
            {
                'contractAddress': TOKEN,
                'tokenSymbol': 'USDT',
                'tokenName': 'Tether',
                'tokenDecimals': '6',
                'tokenBalance': '1500000',
            }
        ]
        client.get_nft_portfolio.value = [{'collection': {'name': 'BAYC'}, 'value': '2'}]
        response = await mcp_tools.get_address_overview(client, WALLET)
        assert response.data is not None
        assert response.data['address'] == WALLET
        assert response.data['balance_wei'] == '1500000000000000000'
        assert len(response.data['transactions']) == 2
        assert response.data['tokens'][0]['symbol'] == 'USDT'
        assert response.data['tokens'][0]['balance'] == '1.5'
        assert len(response.data['nft_collections']) == 1
        assert response.content_text

    async def test_partial_failure_goes_to_notes(self) -> None:
        client = StubClient()
        client.get_transactions.value = [eth_tx()]
        client.get_token_portfolio.error = ChainscanClientApiError('boom', None)
        client.get_nft_portfolio.error = ChainscanClientApiError('boom', None)
        response = await mcp_tools.get_address_overview(client, WALLET)
        assert response.data is not None
        assert response.data['balance_wei'] == '1500000000000000000'
        assert response.data['tokens'] == []
        assert response.notes
        assert any('token' in note.lower() for note in response.notes)

    async def test_empty_everything(self) -> None:
        client = StubClient()
        response = await mcp_tools.get_address_overview(client, WALLET)
        assert response.data is not None
        assert response.data['transactions'] == []
        assert response.data['tokens'] == []


class TestGetTransactions:
    async def test_first_page_with_cursor(self) -> None:
        client = StubClient()
        client.support(Method.ACCOUNT_TRANSACTIONS)
        client.fetch_page.value = ([eth_tx(), eth_tx(block=101)], {'page': 2, 'offset': 2})
        response = await mcp_tools.get_transactions(client, WALLET, limit=2)
        assert response.data is not None
        assert len(response.data['transactions']) == 2
        assert response.data['total_shown'] == 2
        assert response.pagination is not None
        assert response.pagination.has_more is True
        assert response.pagination.next_call is not None
        next_params = response.pagination.next_call.params
        assert next_params['address'] == WALLET
        assert next_params['limit'] == 2
        # Cursor roundtrip: decoding the next_call cursor restores scanner state
        state = decode_cursor(next_params['cursor'])
        assert state['tool'] == 'get_transactions'
        assert state['cursor'] == {'page': 2, 'offset': 2}

    async def test_follow_up_page_uses_cursor(self) -> None:
        client = StubClient()
        client.support(Method.ACCOUNT_TRANSACTIONS)
        client.fetch_page.value = ([eth_tx()], None)
        token = encode_cursor({'tool': 'get_transactions', 'cursor': {'page': 3, 'offset': 1}})
        response = await mcp_tools.get_transactions(client, WALLET, cursor=token, limit=1)
        assert response.pagination is None
        sent = client.fetch_page.calls[0]['args'][1]
        assert sent['page'] == 3
        assert sent['offset'] == 1

    async def test_invalid_cursor_raises(self) -> None:
        client = StubClient()
        client.support(Method.ACCOUNT_TRANSACTIONS)
        with pytest.raises(ValueError, match='cursor'):
            await mcp_tools.get_transactions(client, WALLET, cursor='%%%')

    async def test_forged_cursor_cannot_override_address(self) -> None:
        """A cursor carrying a foreign address is rejected outright — the
        merged params may only ever advance pagination, never re-target the
        query."""
        client = StubClient()
        client.support(Method.ACCOUNT_TRANSACTIONS)
        token = encode_cursor(
            {
                'tool': 'get_transactions',
                'cursor': {'page': 2, 'offset': 1, 'address': '0x' + 'ee' * 20},
            }
        )
        with pytest.raises(ValueError, match='not allowed'):
            await mcp_tools.get_transactions(client, WALLET, cursor=token, limit=1)
        assert client.fetch_page.calls == []

    async def test_foreign_tool_cursor_rejected(self) -> None:
        """A cursor issued by tool A must not drive tool B."""
        client = StubClient()
        client.support(Method.ACCOUNT_TOKEN_PORTFOLIO)
        token = encode_cursor({'tool': 'get_transactions', 'cursor': {'page': 2}})
        with pytest.raises(ValueError, match='was not issued by'):
            await mcp_tools.get_token_portfolio(client, WALLET, cursor=token)
        assert client.fetch_page.calls == []

    async def test_cursor_without_tool_binding_rejected(self) -> None:
        """Pre-binding cursor tokens (no ``tool`` field) are stale/foreign."""
        client = StubClient()
        client.support(Method.ACCOUNT_TRANSACTIONS)
        token = encode_cursor({'cursor': {'page': 2, 'offset': 1}})
        with pytest.raises(ValueError, match='was not issued by'):
            await mcp_tools.get_transactions(client, WALLET, cursor=token)
        assert client.fetch_page.calls == []

    async def test_empty_page(self) -> None:
        client = StubClient()
        client.support(Method.ACCOUNT_TRANSACTIONS)
        client.fetch_page.value = ([], None)
        response = await mcp_tools.get_transactions(client, WALLET)
        assert response.data is not None and response.data['transactions'] == []
        assert response.pagination is None
        assert response.notes is not None

    async def test_unsupported_scanner_notes(self) -> None:
        client = StubClient()  # supports nothing
        response = await mcp_tools.get_transactions(client, WALLET)
        assert response.notes is not None
        assert any('scanner' in note.lower() for note in response.notes)

    async def test_curation_trims_fields(self) -> None:
        client = StubClient()
        client.support(Method.ACCOUNT_TRANSACTIONS)
        tx = eth_tx(input='0x' + 'ff' * 200)
        client.fetch_page.value = ([tx], None)
        response = await mcp_tools.get_transactions(client, WALLET)
        assert response.data is not None
        curated = response.data['transactions'][0]
        assert set(curated) <= {
            'hash',
            'from',
            'to',
            'value_wei',
            'value',
            'block_number',
            'timestamp',
            'is_error',
            'method_id',
        }
        assert curated['method_id'] == '0x' + 'ff' * 4

    async def test_limit_clamped(self) -> None:
        client = StubClient()
        client.support(Method.ACCOUNT_TRANSACTIONS)
        await mcp_tools.get_transactions(client, WALLET, limit=999)
        assert client.fetch_page.calls[0]['args'][1]['offset'] == DEFAULT_PAGE_SIZE


class TestGetTransactionInfo:
    async def test_decoded_with_abi(self) -> None:
        client = StubClient()
        client.support(Method.TX_BY_HASH, Method.CONTRACT_ABI)
        client.get_transaction.value = eth_tx(
            to=TOKEN,
            input='0xa9059cbb'
            + bytes(12).hex()
            + WALLET_OTHER[2:].lower()
            + (5).to_bytes(32, 'big').hex(),
        )
        client.get_contract_abi.value = json.dumps(TRANSFER_ABI)
        response = await mcp_tools.get_transaction_info(client, TX_HASH)
        assert response.data is not None
        assert response.data['decoded_input']['function'] == 'transfer'
        assert response.data['decoded_input']['args']['to'] == WALLET_OTHER.lower()
        assert 'raw_input' not in response.data

    async def test_without_abi_keeps_truncated_raw(self) -> None:
        client = StubClient()
        client.support(Method.TX_BY_HASH, Method.CONTRACT_ABI)
        long_input = '0xa9059cbb' + 'ab' * 400
        client.get_transaction.value = eth_tx(to=TOKEN, input=long_input)
        client.get_contract_abi.error = ChainscanClientApiError('NOTOK', None)
        response = await mcp_tools.get_transaction_info(client, TX_HASH)
        assert response.data is not None
        raw = response.data['raw_input']
        assert isinstance(raw, dict) and raw['value_truncated'] is True
        assert any('ABI' in note for note in response.notes or [])

    async def test_not_found(self) -> None:
        client = StubClient()
        client.support(Method.TX_BY_HASH)
        client.get_transaction.value = {}
        response = await mcp_tools.get_transaction_info(client, TX_HASH)
        assert response.data is None
        assert any('not found' in note.lower() for note in response.notes or [])

    async def test_unsupported_scanner_notes(self) -> None:
        client = StubClient()
        response = await mcp_tools.get_transaction_info(client, TX_HASH)
        assert response.notes is not None

    async def test_json_rpc_hex_values_normalized(self) -> None:
        client = StubClient()
        client.support(Method.TX_BY_HASH)
        client.get_transaction.value = eth_tx(value='0xde0b6b3a7640000', gasPrice='0x3b9aca00')
        response = await mcp_tools.get_transaction_info(client, TX_HASH)
        assert response.data is not None
        assert response.data['value_wei'] == '1000000000000000000'
        assert response.data['value'].startswith('1 ETH')
        assert response.data['gas_price_wei'] == '1000000000'


class TestTokenTools:
    async def test_token_info_happy(self) -> None:
        client = StubClient()
        client.support(Method.TOKEN_INFO, Method.TOKEN_HOLDER_COUNT)
        client.get_token_info.value = {
            'name': 'Tether USD',
            'symbol': 'USDT',
            'decimals': '6',
            'totalSupply': '1000000000000',
        }
        client.get_token_holder_count.value = 4210
        response = await mcp_tools.get_token_info(client, TOKEN)
        assert response.data is not None
        assert response.data['symbol'] == 'USDT'
        assert response.data['total_supply'] == '1000000000000'
        assert response.data['total_supply_formatted'] == '1000000'
        assert response.data['holder_count'] == 4210

    async def test_token_info_holder_count_unsupported(self) -> None:
        client = StubClient()
        client.support(Method.TOKEN_INFO)
        client.get_token_info.value = {'symbol': 'X', 'decimals': '18'}
        response = await mcp_tools.get_token_info(client, TOKEN)
        assert response.data is not None
        assert 'holder_count' not in response.data
        assert response.notes

    async def test_holders_with_pagination_and_total(self) -> None:
        client = StubClient()
        client.support(Method.TOKEN_HOLDERS, Method.TOKEN_HOLDER_COUNT, Method.TOKEN_INFO)
        client.get_token_info.value = {'decimals': '6', 'symbol': 'USDT'}
        client.get_token_holder_count.value = 4210
        client.fetch_page.value = (
            [
                {'address': WALLET, 'value': '1500000'},
                {'address': WALLET_OTHER, 'value': '500000'},
            ],
            {'address_hash': WALLET_OTHER, 'value': '500000'},
        )
        response = await mcp_tools.get_token_holders(client, TOKEN, limit=2)
        assert response.data is not None
        assert response.data['holders'][0]['balance'] == '1.5'
        assert response.data['holders'][0]['token_symbol'] == 'USDT'
        assert response.pagination is not None
        assert response.pagination.total == 4210
        assert response.pagination.next_call is not None
        assert response.pagination.next_call.tool == 'get_token_holders'

    async def test_holders_last_page(self) -> None:
        client = StubClient()
        client.support(Method.TOKEN_HOLDERS)
        client.fetch_page.value = ([{'address': WALLET, 'value': '1'}], None)
        response = await mcp_tools.get_token_holders(client, TOKEN)
        assert response.data is not None and response.data['holders']
        assert response.pagination is None

    async def test_holders_unsupported_notes(self) -> None:
        client = StubClient()
        response = await mcp_tools.get_token_holders(client, TOKEN)
        assert response.notes is not None
        assert any('scanner' in note.lower() for note in response.notes)

    async def test_top_holders_happy(self) -> None:
        client = StubClient()
        client.support(Method.TOKEN_TOP_HOLDERS)
        client.get_top_token_holders = _AsyncReturner([{'address': WALLET, 'value': '10'}])
        client.get_token_info.value = {'decimals': '0', 'symbol': 'X'}
        response = await mcp_tools.get_top_token_holders(client, TOKEN, limit=1)
        assert response.data is not None
        assert response.data['holders'][0]['address'] == WALLET
        assert client.get_top_token_holders.calls[0]['kwargs']['limit'] == 1

    async def test_top_holders_unsupported_notes(self) -> None:
        client = StubClient()
        response = await mcp_tools.get_top_token_holders(client, TOKEN)
        assert response.notes is not None

    async def test_token_portfolio_etherscan_shape(self) -> None:
        client = StubClient()
        client.support(Method.ACCOUNT_TOKEN_PORTFOLIO)
        client.fetch_page.value = (
            [
                {
                    'contractAddress': TOKEN,
                    'tokenSymbol': 'USDT',
                    'tokenName': 'Tether',
                    'tokenDecimals': '6',
                    'tokenBalance': '2500000',
                }
            ],
            None,
        )
        response = await mcp_tools.get_token_portfolio(client, WALLET)
        assert response.data is not None
        holding = response.data['tokens'][0]
        assert holding['contract_address'] == TOKEN
        assert holding['balance'] == '2.5'

    async def test_token_portfolio_blockscout_v2_shape(self) -> None:
        client = StubClient()
        client.support(Method.ACCOUNT_TOKEN_PORTFOLIO)
        client.fetch_page.value = (
            [
                {
                    'token': {
                        'address_hash': TOKEN,
                        'symbol': 'USDT',
                        'decimals': 6,
                        'name': 'Tether',
                    },
                    'value': '2500000',
                }
            ],
            None,
        )
        response = await mcp_tools.get_token_portfolio(client, WALLET)
        assert response.data is not None
        holding = response.data['tokens'][0]
        assert holding['symbol'] == 'USDT'
        assert holding['balance'] == '2.5'


class TestReadContract:
    async def test_happy_path(self) -> None:
        client = StubClient()
        client.support(Method.CONTRACT_ABI, Method.PROXY_ETH_CALL)
        client.get_contract_abi.value = json.dumps(BALANCE_OF_ABI)
        client.eth_call.value = '0x' + (1000).to_bytes(32, 'big').hex()
        response = await mcp_tools.read_contract(client, TOKEN, 'balanceOf', args=f'["{WALLET}"]')
        assert response.data is not None
        assert response.data['function'] == 'balanceOf'
        assert response.data['result'] == {'balance': '1000'}
        call_data = client.eth_call.calls[0]['kwargs']['data']
        assert call_data == '0x70a08231' + bytes(12).hex() + WALLET[2:].lower()
        assert client.eth_call.calls[0]['kwargs']['to'] == TOKEN

    async def test_invalid_args_json(self) -> None:
        client = StubClient()
        with pytest.raises(ValueError, match='args'):
            await mcp_tools.read_contract(client, TOKEN, 'balanceOf', args='not json')

    async def test_arity_mismatch(self) -> None:
        client = StubClient()
        client.support(Method.CONTRACT_ABI)
        client.get_contract_abi.value = json.dumps(BALANCE_OF_ABI)
        with pytest.raises(ValueError, match='1 argument'):
            await mcp_tools.read_contract(client, TOKEN, 'balanceOf', args='[]')

    async def test_unknown_function_notes_available(self) -> None:
        client = StubClient()
        client.support(Method.CONTRACT_ABI)
        client.get_contract_abi.value = json.dumps(TRANSFER_ABI)
        response = await mcp_tools.read_contract(client, TOKEN, 'balanceOf', args='[]')
        assert response.data is None
        assert any('transfer' in note for note in response.notes or [])

    async def test_no_abi_notes(self) -> None:
        client = StubClient()
        client.support(Method.CONTRACT_ABI)
        client.get_contract_abi.error = ChainscanClientApiError(
            'NOTOK', 'Contract source code not verified'
        )
        response = await mcp_tools.read_contract(client, TOKEN, 'balanceOf', args='[]')
        assert response.data is None
        assert any('verified' in note.lower() for note in response.notes or [])

    async def test_abi_unsupported_notes(self) -> None:
        client = StubClient()
        response = await mcp_tools.read_contract(client, TOKEN, 'balanceOf', args='[]')
        assert response.notes is not None

    async def test_empty_result_notes(self) -> None:
        client = StubClient()
        client.support(Method.CONTRACT_ABI, Method.PROXY_ETH_CALL)
        client.get_contract_abi.value = json.dumps(BALANCE_OF_ABI)
        client.eth_call.value = '0x'
        response = await mcp_tools.read_contract(client, TOKEN, 'balanceOf', args=f'["{WALLET}"]')
        assert response.data is not None
        assert response.data['result'] is None
        assert response.notes


class TestResolveEns:
    async def test_forward(self) -> None:
        client = StubClient()
        client.resolve_name.value = WALLET
        response = await mcp_tools.resolve_ens(client, 'vitalik.eth')
        assert response.data is not None
        assert response.data['address'] == WALLET
        assert 'vitalik.eth' in (response.content_text or '')

    async def test_reverse(self) -> None:
        client = StubClient()
        client.lookup_address.value = 'vitalik.eth'
        response = await mcp_tools.resolve_ens(client, WALLET)
        assert response.data is not None
        assert response.data['ens_name'] == 'vitalik.eth'

    async def test_no_name(self) -> None:
        client = StubClient()
        response = await mcp_tools.resolve_ens(client, WALLET)
        assert response.data is not None
        assert response.data['ens_name'] is None
        assert response.notes

    async def test_invalid_address(self) -> None:
        client = StubClient()
        with pytest.raises(ValueError):
            await mcp_tools.resolve_ens(client, '0x123')


class TestListChains:
    def test_includes_ethereum(self) -> None:
        response = mcp_tools.list_chains()
        assert response.data is not None
        entry = next(c for c in response.data['chains'] if c['chain_id'] == 1)
        assert entry['name'] == 'ethereum'
        assert 'eth' in entry['aliases']

    def test_query_filter(self) -> None:
        response = mcp_tools.list_chains(query='base')
        assert response.data is not None
        names = {c['name'] for c in response.data['chains']}
        assert 'base' in names
        assert 'ethereum' not in names

    def test_blockscout_availability_flag(self) -> None:
        response = mcp_tools.list_chains(query='gnosis')
        assert response.data is not None
        entry = response.data['chains'][0]
        assert entry['blockscout'] is not None


class TestClientPool:
    async def test_reuses_client_per_target(self) -> None:
        created: list[StubClient] = []

        def factory(scanner: str, network: str) -> StubClient:
            client = StubClient()
            created.append(client)
            return client

        pool = mcp_tools.ClientPool(factory=factory)  # type: ignore[arg-type]
        first = pool.get('blockscout', 'ethereum')
        second = pool.get('blockscout', 'ethereum')
        other = pool.get('blockscout', 'gnosis')
        assert first is second
        assert first is not other
        assert len(created) == 2
        await pool.aclose_all()

    async def test_close_all_closes_clients(self) -> None:
        pool = mcp_tools.ClientPool(factory=lambda s, n: StubClient())  # type: ignore[arg-type]
        client = pool.get('blockscout', 'ethereum')
        await pool.aclose_all()
        assert getattr(client, 'closed', False) is True


class TestDefaultScanner:
    def test_default_scanner_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert mcp_tools.resolve_default_scanner() == 'blockscout'
        monkeypatch.setenv('AIOCHAINSCAN_MCP_SCANNER', 'etherscan')
        assert mcp_tools.resolve_default_scanner() == 'etherscan'


# ============================================================================
# FastMCP registration (requires the mcp extra: uv run --extra mcp pytest)
# ============================================================================


class TestFastMcpRegistration:
    def test_server_registers_all_tools(self) -> None:
        pytest.importorskip('mcp')
        from aiochainscan.mcp.server import TOOL_NAMES, create_mcp_server

        server = create_mcp_server(pool=_stub_pool())
        import asyncio

        listed = asyncio.run(server.list_tools())
        names = {tool.name for tool in listed}
        assert set(TOOL_NAMES) <= names
        assert 'read_contract' in names
        assert 'get_address_overview' in names
        assert 'list_chains' in names

    def test_call_tool_returns_envelope_content(self) -> None:
        pytest.importorskip('mcp')
        from mcp.types import CallToolResult, TextContent

        from aiochainscan.mcp.server import create_mcp_server

        server = create_mcp_server(pool=_stub_pool())
        import asyncio

        result = asyncio.run(
            server.call_tool('get_wallet_balance', {'address': WALLET, 'chain': 'ethereum'})
        )
        if isinstance(result, CallToolResult):
            assert any(
                isinstance(block, TextContent) and '1.5' in block.text for block in result.content
            )
            assert result.structuredContent is not None
            assert result.structuredContent['data']['balance'] == '1.5'
        else:  # pragma: no cover - FastMCP without CallToolResult passthrough
            pytest.fail('expected CallToolResult passthrough')


def _stub_pool() -> Any:
    def factory(scanner: str, network: str) -> StubClient:
        return StubClient()

    return mcp_tools.ClientPool(factory=factory)  # type: ignore[arg-type]
