from __future__ import annotations

from typing import TypedDict


class GasOracleDTO(TypedDict, total=False):
    """Normalized gas oracle information.

    All gas price fields are represented in wei. Ratios are floats in [0, 1].
    """

    safe_gas_price_wei: int
    propose_gas_price_wei: int
    fast_gas_price_wei: int
    suggest_base_fee_wei: int
    gas_used_ratio: float


class TransactionDTO(TypedDict, total=False):
    tx_hash: str
    block_number: int | None
    from_address: str | None
    to_address: str | None
    value_wei: int | None
    gas: int | None
    gas_price_wei: int | None
    nonce: int | None
    input: str | None


class BlockDTO(TypedDict, total=False):
    block_number: int | None
    hash: str | None
    parent_hash: str | None
    miner: str | None
    timestamp: int | None
    gas_limit: int | None
    gas_used: int | None
    tx_count: int | None


class LogEntryDTO(TypedDict, total=False):
    address: str
    block_number: int | None
    tx_hash: str | None
    data: str | None
    topics: list[str]


class EthPriceDTO(TypedDict, total=False):
    eth_usd: float | None
    eth_btc: float | None
    eth_usd_timestamp: int | None
    eth_btc_timestamp: int | None


class DailySeriesDTO(TypedDict, total=False):
    """Normalized daily series point.

    Keys are optional to allow best-effort normalization across providers.
    """

    utc_date: str | None
    unix_timestamp: int | None
    value: float | None


class ProxyTxDTO(TypedDict, total=False):
    """Normalized transaction DTO from proxy.eth_getTransactionByHash."""

    tx_hash: str | None
    block_number: int | None
    from_address: str | None
    to_address: str | None
    value_wei: int | None
    gas: int | None
    gas_price_wei: int | None
    nonce: int | None
    input: str | None


class NormalTxDTO(TypedDict, total=False):
    blockNumber: str | None
    timeStamp: str | None
    hash: str | None
    nonce: str | None
    blockHash: str | None
    transactionIndex: str | None
    from_: str | None
    to: str | None
    value: str | None
    gas: str | None
    gasPrice: str | None
    isError: str | None
    txreceipt_status: str | None
    input: str | None
    contractAddress: str | None
    cumulativeGasUsed: str | None
    gasUsed: str | None
    confirmations: str | None


class InternalTxDTO(TypedDict, total=False):
    blockNumber: str | None
    timeStamp: str | None
    hash: str | None
    from_: str | None
    to: str | None
    value: str | None
    contractAddress: str | None
    input: str | None
    type: str | None
    gas: str | None
    gasUsed: str | None
    traceId: str | None
    isError: str | None
    errCode: str | None


class TokenTransferDTO(TypedDict, total=False):
    blockNumber: str | None
    timeStamp: str | None
    hash: str | None
    nonce: str | None
    blockHash: str | None
    from_: str | None
    contractAddress: str | None
    to: str | None
    value: str | None
    tokenName: str | None
    tokenSymbol: str | None
    tokenDecimal: str | None
    transactionIndex: str | None
    gas: str | None
    gasPrice: str | None
    gasUsed: str | None
    cumulativeGasUsed: str | None
    input: str | None
    confirmations: str | None


class MinedBlockDTO(TypedDict, total=False):
    blockNumber: str | None
    timeStamp: str | None
    blockReward: str | None


class BeaconWithdrawalDTO(TypedDict, total=False):
    blockNumber: str | None
    timeStamp: str | None
    address: str | None
    amount: str | None
