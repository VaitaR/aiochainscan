from datetime import date
from typing import Any

from aiochainscan.adapters.aiohttp_client import AiohttpClient
from aiochainscan.adapters.endpoint_builder_urlbuilder import UrlBuilderEndpoint
from aiochainscan.adapters.structlog_telemetry import StructlogTelemetry
from aiochainscan.capabilities import (
    FEATURE_SUPPORT as _FEATURE_SUPPORT_SRC,
)
from aiochainscan.capabilities import (
    get_supported_features as _caps_get_supported_features,
)
from aiochainscan.capabilities import (
    get_supported_scanners as _caps_get_supported_scanners,
)
from aiochainscan.capabilities import (
    is_feature_supported as _caps_is_feature_supported,
)
from aiochainscan.client import Client  # noqa: F401
from aiochainscan.config import ChainScanConfig, ScannerConfig, config  # noqa: F401
from aiochainscan.domain.dto import (
    AddressBalanceDTO,
    BeaconWithdrawalDTO,
    BlockDTO,
    DailySeriesDTO,
    EthPriceDTO,
    GasOracleDTO,
    InternalTxDTO,
    LogEntryDTO,
    MinedBlockDTO,
    NormalTxDTO,
    ProxyTxDTO,
    TokenTransferDTO,
    TransactionDTO,
)
from aiochainscan.domain.models import Address, BlockNumber, TxHash  # re-export domain VOs
from aiochainscan.ports.cache import Cache
from aiochainscan.ports.endpoint_builder import EndpointBuilder
from aiochainscan.ports.http_client import HttpClient
from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry
from aiochainscan.services.account import (
    get_account_balance_by_blockno as get_account_balance_by_blockno_service,
)
from aiochainscan.services.account import (
    get_address_balance,  # facade use-case
    normalize_beacon_withdrawals,
    normalize_internal_txs,
    normalize_mined_blocks,
    normalize_normal_txs,
    normalize_token_transfers,
)
from aiochainscan.services.account import (
    get_address_balances as get_address_balances_service,
)
from aiochainscan.services.account import (
    get_beacon_chain_withdrawals as get_beacon_chain_withdrawals_service,
)
from aiochainscan.services.account import (
    get_internal_transactions as get_internal_transactions_service,
)
from aiochainscan.services.account import (
    get_mined_blocks as get_mined_blocks_service,
)
from aiochainscan.services.account import (
    get_normal_transactions as get_normal_transactions_service,
)
from aiochainscan.services.account import (
    get_token_transfers as get_token_transfers_service,
)

# service function + normalization
from aiochainscan.services.block import (
    get_block_by_number,  # facade use-case
    normalize_block,
)
from aiochainscan.services.contract import (
    check_proxy_contract_verification as check_proxy_contract_verification_service,
)
from aiochainscan.services.contract import (
    check_verification_status as check_verification_status_service,
)
from aiochainscan.services.contract import (
    get_contract_abi as get_contract_abi_service,
)
from aiochainscan.services.contract import (
    get_contract_creation as get_contract_creation_service,
)
from aiochainscan.services.contract import (
    get_contract_source_code as get_contract_source_code_service,
)
from aiochainscan.services.contract import (
    verify_contract_source_code as verify_contract_source_code_service,
)
from aiochainscan.services.contract import (
    verify_proxy_contract as verify_proxy_contract_service,
)
from aiochainscan.services.gas import (
    get_gas_oracle as get_gas_oracle_service,
)
from aiochainscan.services.gas import (
    normalize_gas_oracle,
)
from aiochainscan.services.logs import normalize_log_entry, normalize_logs
from aiochainscan.services.proxy import (
    estimate_gas as estimate_gas_service,
)
from aiochainscan.services.proxy import (
    eth_call as eth_call_service,
)
from aiochainscan.services.proxy import get_block_number as get_block_number_service
from aiochainscan.services.proxy import (
    get_block_tx_count_by_number as get_block_tx_count_by_number_service,
)
from aiochainscan.services.proxy import (
    get_code as get_code_service,
)
from aiochainscan.services.proxy import (
    get_gas_price as get_gas_price_service,
)
from aiochainscan.services.proxy import (
    get_storage_at as get_storage_at_service,
)
from aiochainscan.services.proxy import (
    get_tx_by_block_number_and_index as get_tx_by_block_number_and_index_service,
)
from aiochainscan.services.proxy import (
    get_tx_count as get_tx_count_service,
)
from aiochainscan.services.proxy import (
    get_tx_receipt as get_tx_receipt_service,
)
from aiochainscan.services.proxy import (
    get_uncle_by_block_number_and_index as get_uncle_by_block_number_and_index_service,
)
from aiochainscan.services.proxy import (
    normalize_proxy_tx,
)
from aiochainscan.services.proxy import (
    send_raw_tx as send_raw_tx_service,
)
from aiochainscan.services.stats import (
    normalize_daily_average_block_size,
    normalize_daily_average_block_time,
    normalize_daily_average_gas_limit,
    normalize_daily_average_gas_price,
    normalize_daily_average_network_difficulty,
    normalize_daily_average_network_hash_rate,
    normalize_daily_block_count,
    normalize_daily_block_rewards,
    normalize_daily_network_tx_fee,
    normalize_daily_network_utilization,
    normalize_daily_new_address_count,
    normalize_daily_total_gas_used,
    normalize_daily_transaction_count,
    normalize_daily_uncle_block_count,
    normalize_eth_price,
    normalize_ether_historical_daily_market_cap,
    normalize_ether_historical_price,
)
from aiochainscan.services.token import (
    TokenBalanceDTO,
    normalize_token_balance,
)

# service functions
from aiochainscan.services.token import (
    get_token_balance as get_token_balance_service,
)
from aiochainscan.services.transaction import (
    get_transaction_by_hash,  # facade use-case
    normalize_transaction,
)

__all__ = [
    'Client',
    'ChainScanConfig',
    'ScannerConfig',
    'config',
    # Domain VOs
    'Address',
    'BlockNumber',
    'TxHash',
    # Services (facade)
    'get_address_balance',
    'get_address_balances',
    'get_normal_transactions',
    'get_internal_transactions',
    'get_token_transfers',
    'get_mined_blocks',
    'get_beacon_chain_withdrawals',
    'get_account_balance_by_blockno',
    'get_block_by_number',
    'get_transaction_by_hash',
    'get_token_balance',
    'get_gas_oracle',
    'normalize_gas_oracle',
    'normalize_token_balance',
    'TokenBalanceDTO',
    'normalize_block',
    'normalize_transaction',
    'normalize_log_entry',
    'normalize_logs',
    'normalize_eth_price',
    'normalize_daily_transaction_count',
    'normalize_daily_new_address_count',
    'normalize_daily_network_tx_fee',
    'normalize_daily_network_utilization',
    'normalize_daily_average_block_size',
    'normalize_daily_block_rewards',
    'normalize_daily_average_block_time',
    'normalize_daily_uncle_block_count',
    'normalize_daily_average_gas_limit',
    'normalize_daily_total_gas_used',
    'normalize_daily_average_gas_price',
    'normalize_daily_block_count',
    'normalize_daily_average_network_hash_rate',
    'normalize_daily_average_network_difficulty',
    'normalize_ether_historical_daily_market_cap',
    'normalize_ether_historical_price',
    'DailySeriesDTO',
    'ProxyTxDTO',
    'LogEntryDTO',
    'BlockDTO',
    'TransactionDTO',
    'GasOracleDTO',
    # New facade helpers
    'get_daily_average_block_size',
    'get_daily_block_rewards',
    'get_daily_average_block_time',
    'get_daily_uncle_block_count',
    'get_daily_average_gas_limit',
    'get_daily_total_gas_used',
    'get_daily_average_gas_price',
    'get_daily_block_count',
    'get_daily_average_network_hash_rate',
    'get_daily_average_network_difficulty',
    'get_ether_historical_daily_market_cap',
    'get_ether_historical_price',
    'get_block_number',
    'get_gas_price',
    'get_tx_count',
    'get_code',
    'eth_call',
    'get_storage_at',
    'get_block_tx_count_by_number',
    'get_tx_by_block_number_and_index',
    'get_uncle_by_block_number_and_index',
    'estimate_gas',
    'send_raw_tx',
    'get_tx_receipt',
    'normalize_proxy_tx',
    # Account DTOs/normalizers
    'NormalTxDTO',
    'InternalTxDTO',
    'TokenTransferDTO',
    'MinedBlockDTO',
    'BeaconWithdrawalDTO',
    'AddressBalanceDTO',
    'normalize_normal_txs',
    'normalize_internal_txs',
    'normalize_token_transfers',
    'normalize_mined_blocks',
    'normalize_beacon_withdrawals',
    'normalize_address_balances',
    # Contract facade
    'get_contract_abi',
    'get_contract_source_code',
    'verify_contract_source_code',
    'check_verification_status',
    'verify_proxy_contract',
    'check_proxy_contract_verification',
    'get_contract_creation',
    # Context helper
    'open_default_session',
    # Typed facade helpers (experimental, non-breaking)
    'get_block_typed',
    'get_transaction_typed',
    'get_logs_typed',
    'get_token_balance_typed',
    'get_gas_oracle_typed',
    'get_daily_transaction_count_typed',
    'get_daily_new_address_count_typed',
    'get_daily_network_tx_fee_typed',
    'get_daily_network_utilization_typed',
    'get_daily_average_block_size_typed',
    'get_daily_block_rewards_typed',
    'get_daily_average_block_time_typed',
    'get_daily_uncle_block_count_typed',
    'get_daily_average_gas_limit_typed',
    'get_daily_total_gas_used_typed',
    'get_daily_average_gas_price_typed',
    'get_eth_price_typed',
    # Capabilities facade (read-only)
    'list_feature_matrix',
    'is_feature_supported',
    'get_supported_scanners_for_feature',
    'get_supported_features_for',
]


async def get_balance(
    *,
    address: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> int:
    """Fetch address balance using the default aiohttp adapter.

    Convenience facade for simple use without manual client wiring.
    """

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_address_balance(
            address=Address(address),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _cache=cache,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


# --- Capabilities read-only facade ---


def list_feature_matrix() -> dict[str, set[tuple[str, str]]]:
    """Return a read-only snapshot of feature→(scanner, network) matrix.

    Source-of-truth: `aiochainscan.capabilities.FEATURE_SUPPORT`.
    """

    return {feature: set(pairs) for feature, pairs in _FEATURE_SUPPORT_SRC.items()}


def is_feature_supported(feature: str, scanner_id: str, network: str) -> bool:
    """Check if a feature is supported by (scanner_id, network)."""

    return _caps_is_feature_supported(feature, scanner_id, network)


def get_supported_scanners_for_feature(feature: str) -> set[tuple[str, str]]:
    """Get all (scanner_id, network) pairs supporting a feature."""

    return _caps_get_supported_scanners(feature)


def get_supported_features_for(scanner_id: str, network: str) -> set[str]:
    """Get all features supported by (scanner_id, network)."""

    return _caps_get_supported_features(scanner_id, network)


async def get_block(
    *,
    tag: int | str,
    full: bool,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    """Fetch block by number via default adapter."""

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_block_by_number(
            tag=tag,
            full=full,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _cache=cache,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


# --- Typed facade helpers (non-breaking, return DTOs) ---


async def get_block_typed(
    *,
    tag: int | str,
    full: bool,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> BlockDTO:
    data = await get_block(
        tag=tag,
        full=full,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        endpoint_builder=endpoint_builder,
        rate_limiter=rate_limiter,
        retry=retry,
        cache=cache,
        telemetry=telemetry,
    )
    return normalize_block(data)


async def get_eth_price_typed(
    *,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> EthPriceDTO:
    data = await get_eth_price(
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        endpoint_builder=endpoint_builder,
        rate_limiter=rate_limiter,
        retry=retry,
        cache=cache,
        telemetry=telemetry,
    )
    return normalize_eth_price(data)


async def get_transaction_typed(
    *,
    txhash: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> TransactionDTO:
    data = await get_transaction(
        txhash=txhash,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        endpoint_builder=endpoint_builder,
        rate_limiter=rate_limiter,
        retry=retry,
        cache=cache,
        telemetry=telemetry,
    )
    return normalize_transaction(data)


async def get_logs_typed(
    *,
    start_block: int | str,
    end_block: int | str,
    address: str,
    api_kind: str,
    network: str,
    api_key: str,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
    page: int | str | None = None,
    offset: int | str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[LogEntryDTO]:
    items = await get_logs(
        start_block=start_block,
        end_block=end_block,
        address=address,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        topics=topics,
        topic_operators=topic_operators,
        page=page,
        offset=offset,
        http=http,
        endpoint_builder=endpoint_builder,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
    )
    return normalize_logs(items)


async def get_token_balance_typed(
    *,
    holder: str,
    token_contract: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> TokenBalanceDTO:
    value = await get_token_balance(
        holder=holder,
        token_contract=token_contract,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        endpoint_builder=endpoint_builder,
        rate_limiter=rate_limiter,
        retry=retry,
        cache=cache,
        telemetry=telemetry,
    )
    return normalize_token_balance(
        holder=Address(holder), token_contract=Address(token_contract), value=value
    )


async def get_gas_oracle_typed(
    *,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> GasOracleDTO:
    data = await get_gas_oracle(
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        endpoint_builder=endpoint_builder,
        rate_limiter=rate_limiter,
        retry=retry,
        cache=cache,
        telemetry=telemetry,
    )
    return normalize_gas_oracle(data)


async def get_daily_transaction_count_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_transaction_count(**kwargs)
    return normalize_daily_transaction_count(items)


async def get_daily_new_address_count_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_new_address_count(**kwargs)
    return normalize_daily_new_address_count(items)


async def get_daily_network_tx_fee_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_network_tx_fee(**kwargs)
    return normalize_daily_network_tx_fee(items)


async def get_daily_network_utilization_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_network_utilization(**kwargs)
    return normalize_daily_network_utilization(items)


async def get_daily_average_block_size_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_average_block_size(**kwargs)
    return normalize_daily_average_block_size(items)


async def get_daily_block_rewards_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_block_rewards(**kwargs)
    return normalize_daily_block_rewards(items)


async def get_daily_average_block_time_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_average_block_time(**kwargs)
    return normalize_daily_average_block_time(items)


async def get_daily_uncle_block_count_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_uncle_block_count(**kwargs)
    return normalize_daily_uncle_block_count(items)


async def get_daily_average_gas_limit_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_average_gas_limit(**kwargs)
    return normalize_daily_average_gas_limit(items)


async def get_daily_total_gas_used_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_total_gas_used(**kwargs)
    return normalize_daily_total_gas_used(items)


async def get_daily_average_gas_price_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_average_gas_price(**kwargs)
    return normalize_daily_average_gas_price(items)


async def get_address_balances(
    *,
    addresses: list[str],
    tag: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_address_balances_service(
            addresses=addresses,
            tag=tag,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_normal_transactions(
    *,
    address: str,
    start_block: int | None = None,
    end_block: int | None = None,
    sort: str | None = None,
    page: int | None = None,
    offset: int | None = None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_normal_transactions_service(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort=sort,
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_internal_transactions(
    *,
    address: str | None = None,
    start_block: int | None = None,
    end_block: int | None = None,
    sort: str | None = None,
    page: int | None = None,
    offset: int | None = None,
    txhash: str | None = None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_internal_transactions_service(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort=sort,
            page=page,
            offset=offset,
            txhash=txhash,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_token_transfers(
    *,
    address: str | None = None,
    contract_address: str | None = None,
    start_block: int | None = None,
    end_block: int | None = None,
    sort: str | None = None,
    page: int | None = None,
    offset: int | None = None,
    token_standard: str = 'erc20',
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_token_transfers_service(
            address=address,
            contract_address=contract_address,
            start_block=start_block,
            end_block=end_block,
            sort=sort,
            page=page,
            offset=offset,
            token_standard=token_standard,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_mined_blocks(
    *,
    address: str,
    blocktype: str = 'blocks',
    page: int | None = None,
    offset: int | None = None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_mined_blocks_service(
            address=address,
            blocktype=blocktype,
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_beacon_chain_withdrawals(
    *,
    address: str,
    start_block: int | None = None,
    end_block: int | None = None,
    sort: str | None = None,
    page: int | None = None,
    offset: int | None = None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_beacon_chain_withdrawals_service(
            address=address,
            start_block=start_block,
            end_block=end_block,
            sort=sort,
            page=page,
            offset=offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_account_balance_by_blockno(
    *,
    address: str,
    blockno: int,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> str:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_account_balance_by_blockno_service(
            address=address,
            blockno=blockno,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_transaction(
    *,
    txhash: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    """Fetch transaction by hash via default adapter."""

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_transaction_by_hash(
            txhash=TxHash(txhash),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _cache=cache,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_token_balance(
    *,
    holder: str,
    token_contract: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> int:
    """Fetch ERC-20 token balance via default adapter."""

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_token_balance_service(
            holder=Address(holder),
            token_contract=Address(token_contract),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _cache=cache,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


# Backward-compatible alias
get_token_balance_facade = get_token_balance


async def get_gas_oracle(
    *,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    """Fetch gas oracle via default adapter."""

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_gas_oracle_service(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _cache=cache,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


# Backward-compatible alias
get_gas_oracle_facade = get_gas_oracle


async def get_logs(
    *,
    start_block: int | str,
    end_block: int | str,
    address: str,
    api_kind: str,
    network: str,
    api_key: str,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
    page: int | str | None = None,
    offset: int | str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    """Fetch logs via default adapter."""

    from aiochainscan.services.logs import get_logs as get_logs_service

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_logs_service(
            start_block=start_block,
            end_block=end_block,
            address=address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            topics=topics,
            topic_operators=topic_operators,
            page=page,
            offset=offset,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_eth_price(
    *,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    cache: Cache | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    """Fetch ETH price via default adapter."""

    from aiochainscan.services.stats import get_eth_price as get_eth_price_service

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_eth_price_service(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _cache=cache,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_daily_transaction_count(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    """Fetch daily transaction count via default adapter."""

    from aiochainscan.services.stats import (
        get_daily_transaction_count as get_daily_transaction_count_service,
    )

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_daily_transaction_count_service(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_daily_new_address_count(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    """Fetch daily new address count via default adapter."""

    from aiochainscan.services.stats import (
        get_daily_new_address_count as get_daily_new_address_count_service,
    )

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_daily_new_address_count_service(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_daily_network_tx_fee(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    """Fetch daily network transaction fee via default adapter."""

    from aiochainscan.services.stats import (
        get_daily_network_tx_fee as get_daily_network_tx_fee_service,
    )

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_daily_network_tx_fee_service(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_daily_network_utilization(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    """Fetch daily network utilization via default adapter."""

    from aiochainscan.services.stats import (
        get_daily_network_utilization as get_daily_network_utilization_service,
    )

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_daily_network_utilization_service(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


# Additional facade helpers for remaining daily series
async def get_daily_average_block_size(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    from aiochainscan.services.stats import get_daily_average_block_size as svc

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await svc(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_daily_block_rewards(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    from aiochainscan.services.stats import get_daily_block_rewards as svc

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await svc(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_daily_average_block_time(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    from aiochainscan.services.stats import get_daily_average_block_time as svc

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await svc(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_daily_uncle_block_count(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    from aiochainscan.services.stats import get_daily_uncle_block_count as svc

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await svc(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_daily_average_gas_limit(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    from aiochainscan.services.stats import get_daily_average_gas_limit as svc

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await svc(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_daily_total_gas_used(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    from aiochainscan.services.stats import get_daily_total_gas_used as svc

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await svc(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_daily_average_gas_price(
    *,
    start_date: date,
    end_date: date,
    api_kind: str,
    network: str,
    api_key: str,
    sort: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    from aiochainscan.services.stats import get_daily_average_gas_price as svc

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await svc(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            sort=sort,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_block_number(
    *,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> str:
    """Fetch latest block number via default adapter."""

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_block_number_service(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_gas_price(
    *,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> str:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_gas_price_service(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_tx_count(
    *,
    address: str,
    tag: int | str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> str:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_tx_count_service(
            address=address,
            tag=tag,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_code(
    *,
    address: str,
    tag: int | str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> str:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_code_service(
            address=address,
            tag=tag,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def eth_call(
    *,
    to: str,
    data: str,
    tag: int | str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> str:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await eth_call_service(
            to=to,
            data=data,
            tag=tag,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_storage_at(
    *,
    address: str,
    position: str,
    tag: int | str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> str:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_storage_at_service(
            address=address,
            position=position,
            tag=tag,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_block_tx_count_by_number(
    *,
    tag: int | str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> str:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_block_tx_count_by_number_service(
            tag=tag,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_tx_by_block_number_and_index(
    *,
    tag: int | str,
    index: int | str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_tx_by_block_number_and_index_service(
            tag=tag,
            index=index,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_uncle_by_block_number_and_index(
    *,
    tag: int | str,
    index: int | str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_uncle_by_block_number_and_index_service(
            tag=tag,
            index=index,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def estimate_gas(
    *,
    to: str,
    value: str,
    gas_price: str,
    gas: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> str:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await estimate_gas_service(
            to=to,
            value=value,
            gas_price=gas_price,
            gas=gas,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def send_raw_tx(
    *,
    raw_hex: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await send_raw_tx_service(
            raw_hex=raw_hex,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_tx_receipt(
    *,
    txhash: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_tx_receipt_service(
            txhash=txhash,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_contract_abi(
    *,
    address: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> str:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_contract_abi_service(
            address=address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_contract_source_code(
    *,
    address: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_contract_source_code_service(
            address=address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def verify_contract_source_code(
    *,
    contract_address: str,
    source_code: str,
    contract_name: str,
    compiler_version: str,
    optimization_used: bool,
    runs: int,
    constructor_arguements: str,
    api_kind: str,
    network: str,
    api_key: str,
) -> dict[str, Any]:
    http: HttpClient | None = None
    endpoint: EndpointBuilder | None = None
    telemetry: Telemetry | None = None
    http = http or AiohttpClient()
    endpoint = endpoint or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await verify_contract_source_code_service(
            contract_address=contract_address,
            source_code=source_code,
            contract_name=contract_name,
            compiler_version=compiler_version,
            optimization_used=optimization_used,
            runs=runs,
            constructor_arguements=constructor_arguements,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def check_verification_status(
    *,
    guid: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await check_verification_status_service(
            guid=guid,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def verify_proxy_contract(
    *,
    address: str,
    expected_implementation: str | None,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await verify_proxy_contract_service(
            address=address,
            expected_implementation=expected_implementation,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def check_proxy_contract_verification(
    *,
    guid: str,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> dict[str, Any]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await check_proxy_contract_verification_service(
            guid=guid,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


async def get_contract_creation(
    *,
    contract_addresses: list[str],
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> list[dict[str, Any]]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_contract_creation_service(
            contract_addresses=contract_addresses,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
        )
    finally:
        await http.aclose()


class _DefaultSession:
    def __init__(self, http: HttpClient, endpoint: EndpointBuilder, telemetry: Telemetry) -> None:
        self.http = http
        self.endpoint = endpoint
        self.telemetry = telemetry

    async def aclose(self) -> None:
        await self.http.aclose()


async def open_default_session() -> _DefaultSession:
    """Open a reusable default session for multiple facade calls.

    Returns an object with `http`, `endpoint`, and `telemetry` attributes.
    Caller should `await session.aclose()` when done.
    """
    http = AiohttpClient()
    endpoint = UrlBuilderEndpoint()
    telemetry = StructlogTelemetry()
    return _DefaultSession(http, endpoint, telemetry)
