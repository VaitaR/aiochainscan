"""Pydantic V2 models for normalized blockchain explorer data.

This module provides strongly-typed Pydantic models that handle automatic
hex-to-int conversion and field aliasing for both Etherscan and BlockScout
API response formats.

These models are designed to coexist with the existing TypedDict-based dto.py
for backwards compatibility during migration.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def parse_hex_or_int(v: Any) -> int | None:
    """Convert hex string or integer to int, handling various formats.

    Supports:
    - Hex strings: "0x1a", "0x0"
    - Decimal strings: "26", "0"
    - Integers: 26, 0
    - None/empty: None, ""

    Args:
        v: Value to parse (hex string, decimal string, int, or None)

    Returns:
        Parsed integer or None if input is empty/None
    """
    if v is None or v == '':
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        v = v.strip()
        if v == '':
            return None
        try:
            return int(v, 16) if v.startswith('0x') else int(v)
        except ValueError:
            return None
    return None


def parse_hex_or_int_zero(v: Any) -> int:
    """Parse hex/int with default of 0 instead of None."""
    result = parse_hex_or_int(v)
    return result if result is not None else 0


class TransactionDTO(BaseModel):
    """Normalized transaction data from blockchain explorer.

    Handles both Etherscan and BlockScout response formats with automatic
    hex-to-int conversion for numeric fields.
    """

    tx_hash: str = Field(default='', validation_alias='hash')
    block_number: int | None = Field(default=None, validation_alias='blockNumber')
    block_hash: str | None = Field(default=None, validation_alias='blockHash')
    from_address: str = Field(default='', validation_alias='from')
    to_address: str | None = Field(default=None, validation_alias='to')
    value: int = Field(default=0)
    gas: int = Field(default=0)
    gas_price: int | None = Field(default=None, validation_alias='gasPrice')
    gas_used: int | None = Field(default=None, validation_alias='gasUsed')
    cumulative_gas_used: int | None = Field(default=None, validation_alias='cumulativeGasUsed')
    timestamp: int | None = Field(default=None, validation_alias='timeStamp')
    nonce: int = Field(default=0)
    transaction_index: int | None = Field(default=None, validation_alias='transactionIndex')
    input_data: str = Field(default='', validation_alias='input')
    contract_address: str | None = Field(default=None, validation_alias='contractAddress')
    confirmations: int | None = Field(default=None)
    is_error: bool = Field(default=False, validation_alias='isError')
    tx_receipt_status: str | None = Field(default=None, validation_alias='txreceipt_status')

    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    @field_validator(
        'block_number',
        'gas',
        'gas_price',
        'gas_used',
        'cumulative_gas_used',
        'timestamp',
        'nonce',
        'transaction_index',
        'confirmations',
        mode='before',
    )
    @classmethod
    def _parse_hex_int_nullable(cls, v: Any) -> int | None:
        return parse_hex_or_int(v)

    @field_validator('value', mode='before')
    @classmethod
    def _parse_value(cls, v: Any) -> int:
        return parse_hex_or_int_zero(v)

    @field_validator('is_error', mode='before')
    @classmethod
    def _parse_is_error(cls, v: Any) -> bool:
        if v is None or v == '':
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('1', 'true', 'yes')
        if isinstance(v, int):
            return v != 0
        return False


class TokenTransferDTO(BaseModel):
    """Normalized ERC20/ERC721/ERC1155 token transfer data.

    Maps fields from both Etherscan and BlockScout token transfer endpoints.
    """

    tx_hash: str = Field(default='', validation_alias='hash')
    block_number: int | None = Field(default=None, validation_alias='blockNumber')
    block_hash: str | None = Field(default=None, validation_alias='blockHash')
    timestamp: int | None = Field(default=None, validation_alias='timeStamp')
    nonce: int | None = Field(default=None)
    from_address: str = Field(default='', validation_alias='from')
    to_address: str = Field(default='', validation_alias='to')
    contract_address: str = Field(default='', validation_alias='contractAddress')
    value: int = Field(default=0)
    token_name: str | None = Field(default=None, validation_alias='tokenName')
    token_symbol: str | None = Field(default=None, validation_alias='tokenSymbol')
    token_decimal: int | None = Field(default=None, validation_alias='tokenDecimal')
    token_id: str | None = Field(default=None, validation_alias='tokenID')
    transaction_index: int | None = Field(default=None, validation_alias='transactionIndex')
    gas: int | None = Field(default=None)
    gas_price: int | None = Field(default=None, validation_alias='gasPrice')
    gas_used: int | None = Field(default=None, validation_alias='gasUsed')
    cumulative_gas_used: int | None = Field(default=None, validation_alias='cumulativeGasUsed')
    confirmations: int | None = Field(default=None)

    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    @field_validator(
        'block_number',
        'timestamp',
        'nonce',
        'token_decimal',
        'transaction_index',
        'gas',
        'gas_price',
        'gas_used',
        'cumulative_gas_used',
        'confirmations',
        mode='before',
    )
    @classmethod
    def _parse_hex_int_nullable(cls, v: Any) -> int | None:
        return parse_hex_or_int(v)

    @field_validator('value', mode='before')
    @classmethod
    def _parse_value(cls, v: Any) -> int:
        return parse_hex_or_int_zero(v)


class BalanceDTO(BaseModel):
    """Account balance data.

    Represents native token (ETH, BNB, etc.) balance for an address.
    """

    address: str = Field(default='', validation_alias='account')
    balance: int = Field(default=0)

    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    @field_validator('balance', mode='before')
    @classmethod
    def _parse_balance(cls, v: Any) -> int:
        return parse_hex_or_int_zero(v)


class TokenBalanceDTO(BaseModel):
    """Token balance with metadata.

    Represents ERC20 token balance including token info and decimal handling.
    """

    address: str = Field(default='', validation_alias='account')
    contract_address: str = Field(default='', validation_alias='contractAddress')
    balance: int = Field(default=0)
    token_name: str | None = Field(default=None, validation_alias='tokenName')
    token_symbol: str | None = Field(default=None, validation_alias='tokenSymbol')
    token_decimal: int | None = Field(default=None, validation_alias='tokenDecimal')

    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    @field_validator('balance', mode='before')
    @classmethod
    def _parse_balance(cls, v: Any) -> int:
        return parse_hex_or_int_zero(v)

    @field_validator('token_decimal', mode='before')
    @classmethod
    def _parse_decimal(cls, v: Any) -> int | None:
        return parse_hex_or_int(v)

    @property
    def balance_decimal(self) -> float | None:
        """Return balance as decimal value using token decimals."""
        if self.token_decimal is None:
            return None
        return self.balance / (10**self.token_decimal)


class BlockDTO(BaseModel):
    """Normalized block information.

    Contains block header data from blockchain explorer APIs.
    """

    block_number: int | None = Field(default=None, validation_alias='blockNumber')
    block_hash: str | None = Field(default=None, validation_alias='hash')
    parent_hash: str | None = Field(default=None, validation_alias='parentHash')
    miner: str | None = Field(default=None)
    timestamp: int | None = Field(default=None, validation_alias='timeStamp')
    gas_limit: int | None = Field(default=None, validation_alias='gasLimit')
    gas_used: int | None = Field(default=None, validation_alias='gasUsed')
    tx_count: int | None = Field(default=None, validation_alias='txCount')
    difficulty: int | None = Field(default=None)
    total_difficulty: int | None = Field(default=None, validation_alias='totalDifficulty')
    size: int | None = Field(default=None)
    nonce: str | None = Field(default=None)
    extra_data: str | None = Field(default=None, validation_alias='extraData')
    block_reward: int | None = Field(default=None, validation_alias='blockReward')

    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    @field_validator(
        'block_number',
        'timestamp',
        'gas_limit',
        'gas_used',
        'tx_count',
        'difficulty',
        'total_difficulty',
        'size',
        'block_reward',
        mode='before',
    )
    @classmethod
    def _parse_hex_int_nullable(cls, v: Any) -> int | None:
        return parse_hex_or_int(v)


class LogEventDTO(BaseModel):
    """Normalized event log data.

    Represents decoded event logs from contract interactions.
    """

    address: str = Field(default='')
    block_number: int | None = Field(default=None, validation_alias='blockNumber')
    block_hash: str | None = Field(default=None, validation_alias='blockHash')
    tx_hash: str | None = Field(default=None, validation_alias='transactionHash')
    tx_index: int | None = Field(default=None, validation_alias='transactionIndex')
    log_index: int | None = Field(default=None, validation_alias='logIndex')
    timestamp: int | None = Field(default=None, validation_alias='timeStamp')
    data: str = Field(default='')
    topics: list[str] = Field(default_factory=list)
    removed: bool = Field(default=False)

    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    @field_validator(
        'block_number',
        'tx_index',
        'log_index',
        'timestamp',
        mode='before',
    )
    @classmethod
    def _parse_hex_int_nullable(cls, v: Any) -> int | None:
        return parse_hex_or_int(v)

    @field_validator('topics', mode='before')
    @classmethod
    def _ensure_topics_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(t) for t in v if t is not None]
        return []


class InternalTransactionDTO(BaseModel):
    """Normalized internal (trace) transaction data.

    Represents internal calls from contract executions.
    """

    tx_hash: str = Field(default='', validation_alias='hash')
    block_number: int | None = Field(default=None, validation_alias='blockNumber')
    timestamp: int | None = Field(default=None, validation_alias='timeStamp')
    from_address: str = Field(default='', validation_alias='from')
    to_address: str | None = Field(default=None, validation_alias='to')
    value: int = Field(default=0)
    contract_address: str | None = Field(default=None, validation_alias='contractAddress')
    input_data: str = Field(default='', validation_alias='input')
    call_type: str | None = Field(default=None, validation_alias='type')
    gas: int | None = Field(default=None)
    gas_used: int | None = Field(default=None, validation_alias='gasUsed')
    trace_id: str | None = Field(default=None, validation_alias='traceId')
    is_error: bool = Field(default=False, validation_alias='isError')
    error_code: str | None = Field(default=None, validation_alias='errCode')

    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    @field_validator(
        'block_number',
        'timestamp',
        'gas',
        'gas_used',
        mode='before',
    )
    @classmethod
    def _parse_hex_int_nullable(cls, v: Any) -> int | None:
        return parse_hex_or_int(v)

    @field_validator('value', mode='before')
    @classmethod
    def _parse_value(cls, v: Any) -> int:
        return parse_hex_or_int_zero(v)

    @field_validator('is_error', mode='before')
    @classmethod
    def _parse_is_error(cls, v: Any) -> bool:
        if v is None or v == '':
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('1', 'true', 'yes')
        if isinstance(v, int):
            return v != 0
        return False


class GasOracleDTO(BaseModel):
    """Normalized gas oracle information.

    All gas price fields are represented in wei.
    """

    safe_gas_price: int | None = Field(default=None, validation_alias='SafeGasPrice')
    propose_gas_price: int | None = Field(default=None, validation_alias='ProposeGasPrice')
    fast_gas_price: int | None = Field(default=None, validation_alias='FastGasPrice')
    suggest_base_fee: int | None = Field(default=None, validation_alias='suggestBaseFee')
    gas_used_ratio: str | None = Field(default=None, validation_alias='gasUsedRatio')

    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    @field_validator(
        'safe_gas_price',
        'propose_gas_price',
        'fast_gas_price',
        'suggest_base_fee',
        mode='before',
    )
    @classmethod
    def _parse_gwei_to_wei(cls, v: Any) -> int | None:
        """Parse gas prices - typically in Gwei, convert to wei."""
        parsed = parse_hex_or_int(v)
        if parsed is not None:
            # Etherscan returns Gwei, convert to wei
            return parsed * 10**9
        return None


class ContractSourceDTO(BaseModel):
    """Contract source code and metadata."""

    source_code: str = Field(default='', validation_alias='SourceCode')
    abi: str = Field(default='', validation_alias='ABI')
    contract_name: str = Field(default='', validation_alias='ContractName')
    compiler_version: str = Field(default='', validation_alias='CompilerVersion')
    optimization_used: bool = Field(default=False, validation_alias='OptimizationUsed')
    runs: int | None = Field(default=None, validation_alias='Runs')
    constructor_arguments: str = Field(default='', validation_alias='ConstructorArguments')
    evm_version: str = Field(default='', validation_alias='EVMVersion')
    library: str = Field(default='', validation_alias='Library')
    license_type: str = Field(default='', validation_alias='LicenseType')
    proxy: bool = Field(default=False, validation_alias='Proxy')
    implementation: str | None = Field(default=None, validation_alias='Implementation')
    swarm_source: str = Field(default='', validation_alias='SwarmSource')

    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    @field_validator('optimization_used', 'proxy', mode='before')
    @classmethod
    def _parse_bool(cls, v: Any) -> bool:
        if v is None or v == '':
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('1', 'true', 'yes')
        if isinstance(v, int):
            return v != 0
        return False

    @field_validator('runs', mode='before')
    @classmethod
    def _parse_runs(cls, v: Any) -> int | None:
        return parse_hex_or_int(v)
