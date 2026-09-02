"""Track D: normalized domain models + the honest ``chain``/``provider`` constructor.

Purely offline — real fixture-shaped dicts (mirroring the field aliases
already handled dually in ``mcp/tools.py`` and ``domain/contract.py``), no
network access, no assertion that any current dict-returning method changed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aiochainscan.core.client import ChainscanClient
from aiochainscan.domain.normalize import (
    normalize_block,
    normalize_internal_transaction,
    normalize_log,
    normalize_token_transfer,
    normalize_transaction,
)
from aiochainscan.domain.normalized import (
    Block,
    InternalTransaction,
    Log,
    TokenTransfer,
    Transaction,
)

FIXTURES_DIR = Path(__file__).parent / 'fixtures' / 'blockscout_v2'


def load_fixture(name: str) -> dict:
    """Load a real response recorded live from the keyless BlockScout V2 API
    (see aiochainscan/domain/normalize.py module docstring for endpoints)."""
    return json.loads((FIXTURES_DIR / name).read_text())


ETHERSCAN_TX = {
    'hash': '0xetherscan',
    'blockNumber': '12345678',
    'from': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
    'to': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
    'value': '2000000000000000000',
    'gas': '21000',
    'gasPrice': '30000000000',
    'gasUsed': '42000',
    'nonce': '5',
    'timeStamp': '1234567890',
    'isError': '0',
    'input': '0x',
}

BLOCKSCOUT_V2_TX = {
    'hash': '0xblockscout',
    'block_number': 12345678,
    'from': {'hash': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'},
    'to': {'hash': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'},
    'value': '2000000000000000000',
    'gas_limit': '21000',
    'gas_price': '30000000000',
    'gas_used': '42000',
    'timestamp': '1234567890',
}


def test_normalize_transaction_etherscan_shape():
    tx = normalize_transaction(ETHERSCAN_TX)
    assert isinstance(tx, Transaction)
    assert tx.hash == '0xetherscan'
    assert tx.block_number == 12345678
    assert tx.from_address == '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
    assert tx.value_wei == 2000000000000000000
    assert isinstance(tx.value_wei, int)
    assert tx.gas_used == 42000
    assert tx.gas_price_wei == 30000000000
    assert tx.nonce == 5
    assert tx.is_error is False
    assert tx.timestamp == datetime(2009, 2, 13, 23, 31, 30, tzinfo=UTC)
    assert tx.provider_data['hash'] == '0xetherscan'
    with pytest.raises(TypeError):
        tx.provider_data['hash'] = 'mutated'  # type: ignore[index]


def test_normalize_transaction_blockscout_v2_shape():
    tx = normalize_transaction(BLOCKSCOUT_V2_TX)
    assert tx.hash == '0xblockscout'
    assert tx.block_number == 12345678
    assert tx.from_address == '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
    assert tx.gas_used == 42000
    assert tx.gas_price_wei == 30000000000
    # Not established from any repo fixture for BlockScout V2 native shape:
    assert tx.nonce is None
    assert tx.is_error is None


def test_transaction_is_frozen_and_slotted():
    tx = normalize_transaction(ETHERSCAN_TX)
    with pytest.raises(AttributeError):
        tx.hash = 'mutated'  # type: ignore[misc]
    assert not hasattr(tx, '__dict__')


def test_normalize_token_transfer_etherscan_and_blockscout_shapes():
    etherscan_transfer = {
        'hash': '0xT',
        'blockNumber': '100',
        'from': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        'to': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        'contractAddress': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        'tokenSymbol': 'USDC',
        'tokenName': 'USD Coin',
        'tokenDecimal': '6',
        'value': '1500000',
        'timeStamp': '1234567890',
    }
    xfer = normalize_token_transfer(etherscan_transfer)
    assert isinstance(xfer, TokenTransfer)
    assert xfer.token_symbol == 'USDC'
    assert xfer.token_decimals == 6
    assert xfer.value_raw == 1500000
    assert isinstance(xfer.value_raw, int)

    blockscout_portfolio_shape = {
        'token': {
            'address_hash': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
            'symbol': 'USDC',
            'name': 'USD Coin',
            'decimals': '6',
        },
        'value': '5878047570',
    }
    xfer2 = normalize_token_transfer(blockscout_portfolio_shape)
    assert xfer2.token_symbol == 'USDC'
    assert xfer2.contract_address == '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
    assert xfer2.value_raw == 5878047570


def test_normalize_internal_transaction():
    item = {
        'hash': '0xI',
        'blockNumber': '100',
        'from': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        'to': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        'contractAddress': '',
        'value': '1000',
        'gas': '2300',
        'gasUsed': '2300',
        'isError': '0',
        'timeStamp': '1600000000',
    }
    itx = normalize_internal_transaction(item)
    assert isinstance(itx, InternalTransaction)
    assert itx.value_wei == 1000
    assert itx.is_error is False
    assert itx.contract_address is None  # empty string -> unmapped, never invented


def test_normalize_log_matches_contract_iter_events_aliases():
    etherscan_log = {
        'address': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        'blockNumber': '100',
        'transactionHash': '0x' + '1' * 64,
        'logIndex': '0x2',
        'topics': ['0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'],
        'data': '0x0',
    }
    log = normalize_log(etherscan_log)
    assert isinstance(log, Log)
    assert log.log_index == 2
    assert log.transaction_hash == '0x' + '1' * 64
    assert log.topics == ('0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',)

    blockscout_log = {
        'address': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
        'block_number': 100,
        'transaction_hash': '0x' + '2' * 64,
        'index': 3,
        'topics': ['0xabc'],
        'data': '0x',
    }
    log2 = normalize_log(blockscout_log)
    assert log2.log_index == 3
    assert log2.transaction_hash == '0x' + '2' * 64


def test_normalize_block_jsonrpc_shape():
    block = normalize_block(
        {
            'number': '0x2a',
            'hash': '0xdeadbeef',
            'timestamp': '0x1',
            'gasUsed': '0x5208',
            'gasLimit': '0x1c9c380',
            'miner': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
            'difficulty': '0x0',
        }
    )
    assert isinstance(block, Block)
    assert block.number == 42
    assert block.hash == '0xdeadbeef'
    assert block.timestamp == datetime(1970, 1, 1, 0, 0, 1, tzinfo=UTC)
    assert block.gas_used == 21000
    assert block.gas_limit == 30000000
    assert block.miner == '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
    assert block.difficulty == 0


def test_normalize_block_native_v2_fixture():
    block = normalize_block(load_fixture('block.json'))
    assert block.number == 19_500_000
    assert block.hash == '0x52345c9721dcf84f8e659f8bda44b93d4e9b003bbd0693bb1bca601bbde3bb26'
    assert block.timestamp == datetime(2024, 3, 23, 21, 34, 59, tzinfo=UTC)
    assert block.gas_used == 29_971_151
    assert block.gas_limit == 30_000_000
    assert block.miner == '0x6d2e03b7EfFEae98BD302A9F836D0d6Ab0002766'
    assert block.difficulty == 0


def test_normalize_block_jsonrpc_fixture_matches_etherscan_like_shape():
    block = normalize_block(load_fixture('block_jsonrpc.json'))
    assert block.number is not None
    assert block.gas_used is not None
    assert block.gas_limit is not None
    assert block.miner is not None
    assert block.timestamp is not None


def test_normalize_transaction_blockscout_v2_native_fixture():
    tx = normalize_transaction(load_fixture('transaction.json'))
    assert tx.nonce is not None  # fixture-confirmed present, was wrongly flagged unmapped
    assert tx.is_error is False  # status == "ok" -> not an error
    assert tx.gas is not None
    assert tx.gas_used is not None
    assert tx.gas_price_wei is not None
    assert tx.timestamp is not None
    assert tx.from_address is not None
    assert tx.to_address is not None


def test_normalize_transaction_blockscout_calldata_comes_from_raw_input():
    """BlockScout V2 names the calldata field ``raw_input``; Etherscan uses ``input``."""
    raw = load_fixture('transaction.json')
    assert 'input' not in raw  # guard: if BlockScout ever adds `input`, revisit the alias order
    tx = normalize_transaction(raw)
    assert tx.input_data == raw['raw_input']


def test_normalize_token_transfer_blockscout_v2_native_fixture():
    xfer = normalize_token_transfer(load_fixture('token_transfer.json'))
    assert xfer.transaction_hash is not None
    assert xfer.transaction_hash != ''
    assert xfer.contract_address is not None
    assert xfer.token_symbol == 'SOS'
    assert xfer.token_decimals == 0
    assert xfer.value_raw == 1
    assert xfer.block_number is not None
    assert xfer.timestamp is not None


def test_normalize_internal_transaction_blockscout_v2_native_fixture():
    itx = normalize_internal_transaction(load_fixture('internal_transaction.json'))
    # Fixture-confirmed absent, not merely unmapped: no per-call hash key exists.
    assert itx.hash is None
    assert itx.transaction_hash is not None
    assert itx.call_index is not None
    assert itx.gas is not None
    # Fixture-confirmed absent: the schema has no gas_used/gasUsed key.
    assert itx.gas_used is None
    assert itx.is_error is False  # success: true
    assert itx.block_number is not None
    assert itx.timestamp is not None


def test_provider_data_never_loses_unknown_fields():
    item = {**ETHERSCAN_TX, 'someFutureField': 'unmapped-but-preserved'}
    tx = normalize_transaction(item)
    assert tx.provider_data['someFutureField'] == 'unmapped-but-preserved'


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_new_constructor_chain_provider_resolves_like_from_config():
    a = ChainscanClient(chain='ethereum', provider='etherscan', api_key='k')
    b = ChainscanClient.from_config('etherscan', 'ethereum', api_key='k')
    assert a.scanner_name == b.scanner_name
    assert a.scanner_version == b.scanner_version
    assert a.api_kind == b.api_kind
    assert a.network == b.network
    assert a.chain_id == b.chain_id


def test_new_constructor_accepts_chain_id_int():
    client = ChainscanClient(chain=8453, provider='etherscan', api_key='k')
    assert client.chain_id == 8453


def test_new_constructor_blockscout_no_api_key_required():
    client = ChainscanClient(chain='ethereum', provider='blockscout_v2')
    assert client.scanner_name == 'blockscout'
    assert client.scanner_version == 'v2'


def test_old_positional_constructor_still_works():
    client = ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'test_key')
    assert client.scanner_name == 'etherscan'
    assert client.api_key == 'test_key'


def test_mixing_new_and_old_style_rejected():
    with pytest.raises(TypeError):
        ChainscanClient('etherscan', network='ethereum', chain='ethereum', provider='etherscan')


def test_chain_without_provider_rejected():
    with pytest.raises(TypeError):
        ChainscanClient(chain='ethereum', api_key='k')


def test_incomplete_positional_style_rejected():
    with pytest.raises(TypeError):
        ChainscanClient(scanner_name='etherscan')
