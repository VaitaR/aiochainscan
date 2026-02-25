"""Tests for Pydantic V2 DTOs.

Tests cover:
- Hex string parsing in various formats
- Model validation with missing/partial fields
- Alias mapping from API responses
- Performance benchmarks comparing old vs new parsing
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from aiochainscan.domain.dto_v2 import (
    BalanceDTO,
    BlockDTO,
    ContractSourceDTO,
    GasOracleDTO,
    InternalTransactionDTO,
    LogEventDTO,
    TokenBalanceDTO,
    TokenTransferDTO,
    TransactionDTO,
    parse_hex_or_int,
    parse_hex_or_int_zero,
)


class TestHexParsing:
    """Test hex string to int conversion."""

    @pytest.mark.parametrize(
        'input_value,expected',
        [
            ('0x1a', 26),
            ('0x0', 0),
            ('0x', None),  # Invalid hex
            ('0xdeadbeef', 3735928559),
            ('26', 26),
            ('0', 0),
            ('123456789', 123456789),
            (26, 26),
            (0, 0),
            (None, None),
            ('', None),
            ('   ', None),
            ('  0x1a  ', 26),  # With whitespace
            ('  26  ', 26),  # Decimal with whitespace
        ],
    )
    def test_parse_hex_or_int(self, input_value: Any, expected: int | None) -> None:
        """Test hex/int parsing with various input formats."""
        assert parse_hex_or_int(input_value) == expected

    @pytest.mark.parametrize(
        'input_value,expected',
        [
            ('0x1a', 26),
            (None, 0),
            ('', 0),
            (0, 0),
            ('0', 0),
        ],
    )
    def test_parse_hex_or_int_zero(self, input_value: Any, expected: int) -> None:
        """Test hex/int parsing with zero default."""
        assert parse_hex_or_int_zero(input_value) == expected


class TestTransactionDTO:
    """Test TransactionDTO model."""

    def test_full_etherscan_response(self) -> None:
        """Test parsing a complete Etherscan transaction response."""
        data = {
            'hash': '0xabc123',
            'blockNumber': '0x100',
            'blockHash': '0xblockhash',
            'from': '0xsender',
            'to': '0xreceiver',
            'value': '0x56bc75e2d63100000',  # 100 ETH in wei
            'gas': '21000',
            'gasPrice': '0x4a817c800',  # 20 Gwei
            'gasUsed': '21000',
            'timeStamp': '1609459200',
            'nonce': '5',
            'input': '0x',
            'isError': '0',
        }

        tx = TransactionDTO.model_validate(data)

        assert tx.tx_hash == '0xabc123'
        assert tx.block_number == 256
        assert tx.from_address == '0xsender'
        assert tx.to_address == '0xreceiver'
        assert tx.value == 100000000000000000000
        assert tx.gas == 21000
        assert tx.gas_price == 20000000000
        assert tx.timestamp == 1609459200
        assert tx.nonce == 5
        assert tx.is_error is False

    def test_minimal_data(self) -> None:
        """Test parsing with minimal data - all fields have defaults."""
        tx = TransactionDTO.model_validate({})

        assert tx.tx_hash == ''
        assert tx.block_number is None
        assert tx.from_address == ''
        assert tx.value == 0
        assert tx.is_error is False

    def test_blockscout_response_format(self) -> None:
        """Test BlockScout API format (may use different field names)."""
        data = {
            'hash': '0xdef456',
            'blockNumber': 12345,  # BlockScout may return int directly
            'from': '0xsender',
            'to': None,  # Contract creation
            'value': 0,
            'gas': 100000,
        }

        tx = TransactionDTO.model_validate(data)

        assert tx.tx_hash == '0xdef456'
        assert tx.block_number == 12345
        assert tx.to_address is None
        assert tx.value == 0

    def test_is_error_variants(self) -> None:
        """Test is_error field parsing with different formats."""
        assert TransactionDTO.model_validate({'isError': '1'}).is_error is True
        assert TransactionDTO.model_validate({'isError': '0'}).is_error is False
        assert TransactionDTO.model_validate({'isError': 1}).is_error is True
        assert TransactionDTO.model_validate({'isError': True}).is_error is True
        assert TransactionDTO.model_validate({'isError': 'true'}).is_error is True

    def test_extra_fields_ignored(self) -> None:
        """Test that extra unknown fields are ignored."""
        data = {
            'hash': '0x123',
            'unknownField': 'should be ignored',
            'anotherExtra': 12345,
        }

        tx = TransactionDTO.model_validate(data)
        assert tx.tx_hash == '0x123'
        # No error raised for extra fields


class TestTokenTransferDTO:
    """Test TokenTransferDTO model."""

    def test_erc20_transfer(self) -> None:
        """Test parsing ERC20 token transfer."""
        data = {
            'hash': '0xtx123',
            'blockNumber': '15000000',
            'timeStamp': '1660000000',
            'from': '0xsender',
            'to': '0xreceiver',
            'contractAddress': '0xtoken',
            'value': '1000000000000000000',  # 1 token (18 decimals)
            'tokenName': 'Test Token',
            'tokenSymbol': 'TEST',
            'tokenDecimal': '18',
        }

        transfer = TokenTransferDTO.model_validate(data)

        assert transfer.tx_hash == '0xtx123'
        assert transfer.block_number == 15000000
        assert transfer.from_address == '0xsender'
        assert transfer.to_address == '0xreceiver'
        assert transfer.value == 1000000000000000000
        assert transfer.token_name == 'Test Token'
        assert transfer.token_symbol == 'TEST'
        assert transfer.token_decimal == 18

    def test_nft_transfer_with_token_id(self) -> None:
        """Test NFT transfer with tokenID field."""
        data = {
            'hash': '0xnft',
            'from': '0xowner',
            'to': '0xbuyer',
            'contractAddress': '0xnftcontract',
            'tokenID': '12345',
            'value': '1',
        }

        transfer = TokenTransferDTO.model_validate(data)

        assert transfer.token_id == '12345'
        assert transfer.value == 1


class TestBalanceDTO:
    """Test BalanceDTO model."""

    def test_balance_parsing(self) -> None:
        """Test balance with various formats."""
        # With account alias
        balance = BalanceDTO.model_validate(
            {
                'account': '0xaddress',
                'balance': '1000000000000000000',
            }
        )
        assert balance.address == '0xaddress'
        assert balance.balance == 1000000000000000000

        # Hex balance
        balance = BalanceDTO.model_validate(
            {
                'account': '0xaddr2',
                'balance': '0xde0b6b3a7640000',
            }
        )
        assert balance.balance == 1000000000000000000


class TestTokenBalanceDTO:
    """Test TokenBalanceDTO model."""

    def test_with_decimals(self) -> None:
        """Test token balance with decimal calculation."""
        data = {
            'account': '0xholder',
            'contractAddress': '0xtoken',
            'balance': '1000000',
            'tokenName': 'USD Coin',
            'tokenSymbol': 'USDC',
            'tokenDecimal': '6',
        }

        tb = TokenBalanceDTO.model_validate(data)

        assert tb.balance == 1000000
        assert tb.token_decimal == 6
        assert tb.balance_decimal == 1.0  # 1 USDC

    def test_balance_decimal_none_without_decimals(self) -> None:
        """Test balance_decimal returns None if decimals not set."""
        tb = TokenBalanceDTO.model_validate({'balance': '1000000'})
        assert tb.balance_decimal is None


class TestBlockDTO:
    """Test BlockDTO model."""

    def test_block_parsing(self) -> None:
        """Test block data parsing."""
        data = {
            'blockNumber': '0xf4240',  # 1000000
            'hash': '0xblockhash',
            'parentHash': '0xparent',
            'miner': '0xminer',
            'timeStamp': '1438270000',
            'gasLimit': '0x47e7c4',
            'gasUsed': '0x5208',
        }

        block = BlockDTO.model_validate(data)

        assert block.block_number == 1000000
        assert block.block_hash == '0xblockhash'
        assert block.gas_limit == 4712388
        assert block.gas_used == 21000


class TestLogEventDTO:
    """Test LogEventDTO model."""

    def test_log_event(self) -> None:
        """Test log event parsing."""
        data = {
            'address': '0xcontract',
            'blockNumber': '0x100',
            'transactionHash': '0xtxhash',
            'transactionIndex': '0x5',
            'logIndex': '0x0',
            'data': '0xdata',
            'topics': [
                '0xtopic0',
                '0xtopic1',
                '0xtopic2',
            ],
        }

        log = LogEventDTO.model_validate(data)

        assert log.address == '0xcontract'
        assert log.block_number == 256
        assert log.tx_hash == '0xtxhash'
        assert log.tx_index == 5
        assert log.log_index == 0
        assert len(log.topics) == 3
        assert log.topics[0] == '0xtopic0'

    def test_topics_none(self) -> None:
        """Test topics defaults to empty list."""
        log = LogEventDTO.model_validate({'address': '0x123', 'topics': None})
        assert log.topics == []

    def test_topics_with_none_values(self) -> None:
        """Test topics list with None values filtered."""
        log = LogEventDTO.model_validate(
            {
                'address': '0x123',
                'topics': ['0xtopic0', None, '0xtopic2'],
            }
        )
        assert log.topics == ['0xtopic0', '0xtopic2']


class TestInternalTransactionDTO:
    """Test InternalTransactionDTO model."""

    def test_internal_tx(self) -> None:
        """Test internal transaction parsing."""
        data = {
            'hash': '0xparenttx',
            'blockNumber': '12345678',
            'timeStamp': '1600000000',
            'from': '0xcontract',
            'to': '0xreceiver',
            'value': '1000000000000000000',
            'type': 'call',
            'gas': '100000',
            'gasUsed': '21000',
            'isError': '0',
        }

        itx = InternalTransactionDTO.model_validate(data)

        assert itx.tx_hash == '0xparenttx'
        assert itx.call_type == 'call'
        assert itx.is_error is False


class TestGasOracleDTO:
    """Test GasOracleDTO model."""

    def test_gas_oracle(self) -> None:
        """Test gas oracle parsing with Gwei to Wei conversion."""
        data = {
            'SafeGasPrice': '20',
            'ProposeGasPrice': '25',
            'FastGasPrice': '30',
            'suggestBaseFee': '15',
            'gasUsedRatio': '0.5,0.6,0.7',
        }

        oracle = GasOracleDTO.model_validate(data)

        # Values converted from Gwei to Wei
        assert oracle.safe_gas_price == 20 * 10**9
        assert oracle.propose_gas_price == 25 * 10**9
        assert oracle.fast_gas_price == 30 * 10**9


class TestContractSourceDTO:
    """Test ContractSourceDTO model."""

    def test_contract_source(self) -> None:
        """Test contract source parsing."""
        data = {
            'SourceCode': 'pragma solidity ^0.8.0;',
            'ABI': '[{"type":"function"}]',
            'ContractName': 'MyContract',
            'CompilerVersion': 'v0.8.17',
            'OptimizationUsed': '1',
            'Runs': '200',
            'Proxy': '0',
        }

        source = ContractSourceDTO.model_validate(data)

        assert source.source_code == 'pragma solidity ^0.8.0;'
        assert source.contract_name == 'MyContract'
        assert source.optimization_used is True
        assert source.runs == 200
        assert source.proxy is False


class TestAliasMapping:
    """Test that alias mapping works correctly."""

    def test_transaction_aliases(self) -> None:
        """Test TransactionDTO accepts both snake_case and original API names."""
        # Using API names (aliases)
        tx1 = TransactionDTO.model_validate(
            {
                'hash': '0x123',
                'blockNumber': '100',
                'gasPrice': '20000000000',
            }
        )

        # Using Python names (with populate_by_name=True)
        tx2 = TransactionDTO(
            tx_hash='0x123',
            block_number=100,
            gas_price=20000000000,
        )

        assert tx1.tx_hash == tx2.tx_hash
        assert tx1.block_number == tx2.block_number
        assert tx1.gas_price == tx2.gas_price

    def test_model_dump_uses_python_names(self) -> None:
        """Test that model_dump uses Python attribute names."""
        tx = TransactionDTO.model_validate(
            {
                'hash': '0x123',
                'blockNumber': '100',
            }
        )

        dumped = tx.model_dump()

        assert 'tx_hash' in dumped
        assert 'block_number' in dumped
        assert 'hash' not in dumped

    def test_model_dump_mode_info(self) -> None:
        """Test model dump behavior documentation.

        Note: We use validation_alias for one-way parsing from API responses.
        This means by_alias=True won't serialize back to API format.
        If bi-directional aliasing is needed in the future, use Field(alias=...)
        instead of Field(validation_alias=...).
        """
        tx = TransactionDTO.model_validate(
            {
                'hash': '0x123',
                'blockNumber': '100',
            }
        )

        # With validation_alias, by_alias doesn't affect output
        dumped = tx.model_dump(by_alias=True)

        # Still uses Python field names since we only have validation_alias
        assert 'tx_hash' in dumped
        assert tx.tx_hash == '0x123'


@pytest.mark.benchmark
class TestPerformanceBenchmark:
    """Performance benchmarks for DTO parsing."""

    @pytest.fixture
    def sample_transactions(self) -> list[dict[str, Any]]:
        """Generate sample transaction data."""
        return [
            {
                'hash': f'0x{i:064x}',
                'blockNumber': hex(15000000 + i),
                'from': f'0x{"a" * 40}',
                'to': f'0x{"b" * 40}',
                'value': hex(10**18 * i),
                'gas': '21000',
                'gasPrice': hex(20 * 10**9),
                'gasUsed': '21000',
                'timeStamp': str(1600000000 + i),
                'nonce': str(i),
                'input': '0x',
                'isError': '0',
            }
            for i in range(1000)
        ]

    def test_benchmark_pydantic_parsing(
        self, sample_transactions: list[dict[str, Any]], benchmark: Any
    ) -> None:
        """Benchmark Pydantic V2 model parsing."""

        def parse_all() -> list[TransactionDTO]:
            return [TransactionDTO.model_validate(tx) for tx in sample_transactions]

        result = benchmark(parse_all)
        assert len(result) == 1000

    def test_benchmark_orjson_vs_stdlib(self, benchmark: Any) -> None:
        """Benchmark orjson vs stdlib json parsing."""
        import orjson

        sample_data = {
            'status': '1',
            'result': [
                {
                    'hash': f'0x{i:064x}',
                    'blockNumber': str(i),
                    'value': str(10**18),
                }
                for i in range(100)
            ],
        }

        json_bytes = orjson.dumps(sample_data)

        def parse_orjson() -> dict:
            return orjson.loads(json_bytes)

        result = benchmark(parse_orjson)
        assert result['status'] == '1'

    def test_compare_parsing_performance(self, sample_transactions: list[dict[str, Any]]) -> None:
        """Compare old vs new parsing approach (informational test)."""
        import orjson

        # Simulate old approach: stdlib json + manual normalization
        json_str = json.dumps(sample_transactions)

        def old_approach() -> list[dict]:
            data = json.loads(json_str)
            results = []
            for tx in data:
                normalized = {
                    'tx_hash': tx.get('hash', ''),
                    'block_number': (
                        int(tx['blockNumber'], 16)
                        if tx.get('blockNumber', '').startswith('0x')
                        else int(tx.get('blockNumber', 0))
                    ),
                    'value': (
                        int(tx['value'], 16)
                        if tx.get('value', '').startswith('0x')
                        else int(tx.get('value', 0))
                    ),
                }
                results.append(normalized)
            return results

        # New approach: orjson + Pydantic
        json_bytes = orjson.dumps(sample_transactions)

        def new_approach() -> list[TransactionDTO]:
            data = orjson.loads(json_bytes)
            return [TransactionDTO.model_validate(tx) for tx in data]

        # Time both approaches
        iterations = 10

        start = time.perf_counter()
        for _ in range(iterations):
            old_approach()
        old_time = time.perf_counter() - start

        start = time.perf_counter()
        for _ in range(iterations):
            new_approach()
        new_time = time.perf_counter() - start

        # Just log the comparison, don't fail on performance
        print(f'\nOld approach: {old_time:.4f}s for {iterations} iterations')
        print(f'New approach: {new_time:.4f}s for {iterations} iterations')
        print(f'Ratio: {new_time / old_time:.2f}x')

        # Verify correctness
        old_result = old_approach()
        new_result = new_approach()

        assert len(old_result) == len(new_result) == 1000
        assert old_result[0]['tx_hash'] == new_result[0].tx_hash
