from collections.abc import Mapping
from datetime import date
from typing import Any

__version__ = '0.2.1'

from aiochainscan.adapters.aiohttp_client import AiohttpClient
from aiochainscan.adapters.endpoint_builder_urlbuilder import UrlBuilderEndpoint
from aiochainscan.adapters.retry_exponential import ExponentialBackoffRetry
from aiochainscan.adapters.simple_rate_limiter import SimpleRateLimiter
from aiochainscan.adapters.structlog_telemetry import StructlogTelemetry
from aiochainscan.capabilities import FEATURE_SUPPORT as _FEATURE_SUPPORT_SRC
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
from aiochainscan.config import config_manager as _config_manager
from aiochainscan.core.client import ChainscanClient  # unified client export
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
from aiochainscan.domain.models import Address, BlockNumber, Page, TxHash  # re-export domain VOs
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
    normalize_address_balances,
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
    get_all_internal_transactions_optimized as get_all_internal_transactions_optimized_service,
)
from aiochainscan.services.account import (
    get_all_transactions_optimized as get_all_transactions_optimized_service,
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
from aiochainscan.services.contract import get_contract_abi as get_contract_abi_service
from aiochainscan.services.contract import get_contract_creation as get_contract_creation_service
from aiochainscan.services.contract import (
    get_contract_source_code as get_contract_source_code_service,
)
from aiochainscan.services.contract import (
    verify_contract_source_code as verify_contract_source_code_service,
)
from aiochainscan.services.contract import (
    verify_proxy_contract as verify_proxy_contract_service,
)
from aiochainscan.services.gas import get_gas_oracle as get_gas_oracle_service
from aiochainscan.services.gas import normalize_gas_oracle
from aiochainscan.services.logs import get_logs_page as get_logs_page_service
from aiochainscan.services.logs import normalize_log_entry, normalize_logs
from aiochainscan.services.proxy import estimate_gas as estimate_gas_service
from aiochainscan.services.proxy import eth_call as eth_call_service
from aiochainscan.services.proxy import get_block_number as get_block_number_service
from aiochainscan.services.proxy import (
    get_block_tx_count_by_number as get_block_tx_count_by_number_service,
)
from aiochainscan.services.proxy import get_code as get_code_service
from aiochainscan.services.proxy import get_gas_price as get_gas_price_service
from aiochainscan.services.proxy import get_storage_at as get_storage_at_service
from aiochainscan.services.proxy import (
    get_tx_by_block_number_and_index as get_tx_by_block_number_and_index_service,
)
from aiochainscan.services.proxy import get_tx_count as get_tx_count_service
from aiochainscan.services.proxy import get_tx_receipt as get_tx_receipt_service
from aiochainscan.services.proxy import (
    get_uncle_by_block_number_and_index as get_uncle_by_block_number_and_index_service,
)
from aiochainscan.services.proxy import normalize_proxy_tx
from aiochainscan.services.proxy import send_raw_tx as send_raw_tx_service
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
from aiochainscan.services.token import TokenBalanceDTO, normalize_token_balance

# service functions
from aiochainscan.services.token import get_token_balance as get_token_balance_service
from aiochainscan.services.transaction import (
    get_transaction_by_hash,  # facade use-case
    normalize_transaction,
)

__all__ = [
    'Client',
    'ChainscanClient',
    'ChainScanConfig',
    'ScannerConfig',
    'config',
    # Domain VOs
    'Address',
    'BlockNumber',
    'TxHash',
    'Page',
    # Services (facade)
    'get_address_balance',
    'get_address_balances',
    'get_normal_transactions',
    'get_all_transactions_optimized',
    'get_all_transactions_optimized_typed',
    'get_all_internal_transactions_optimized',
    'get_all_logs_optimized',
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
    # Adapters (public DI helpers)
    'AiohttpClient',
    'UrlBuilderEndpoint',
    'StructlogTelemetry',
    'SimpleRateLimiter',
    'ExponentialBackoffRetry',
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
    'get_token_transfers_page_typed',
    'get_address_transactions_page_typed',
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
    'get_daily_block_count_typed',
    'get_daily_average_network_hash_rate_typed',
    'get_daily_average_network_difficulty_typed',
    'get_ether_historical_daily_market_cap_typed',
    'get_ether_historical_price_typed',
    # Capabilities facade (read-only)
    'list_feature_matrix',
    'is_feature_supported',
    'get_supported_scanners_for_feature',
    'get_supported_features_for',
    'get_logs_page_typed',
    'get_capabilities_overview',
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


def get_capabilities_overview() -> dict[str, Any]:
    """Return merged read-only overview of capabilities and scanner configs.

    - features: a copy of feature->(scanner, network) pairs
    - scanners: metadata from configuration manager (name, domain, networks, etc.)
    """

    return {
        'features': {feature: set(pairs) for feature, pairs in _FEATURE_SUPPORT_SRC.items()},
        'scanners': _config_manager.list_all_configurations(),
    }


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


async def get_logs_page_typed(
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
    cursor: str | None = None,
    page_size: int | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    gql_headers: Mapping[str, str] | None = None,
) -> Page[LogEntryDTO]:
    """GraphQL-capable typed facade returning Page[LogEntryDTO].

    Uses GraphQL when available and configured via a simple federator; falls back
    to REST and encodes pagination state into an opaque cursor.
    """
    from aiochainscan.adapters.aiohttp_graphql_client import AiohttpGraphQLClient
    from aiochainscan.adapters.blockscout_graphql_builder import (
        BlockscoutGraphQLBuilder,
    )
    from aiochainscan.adapters.simple_provider_federator import SimpleProviderFederator

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    gql = AiohttpGraphQLClient()
    gql_builder = BlockscoutGraphQLBuilder()
    federator = SimpleProviderFederator()
    try:
        items, next_cursor = await get_logs_page_service(
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
            cursor=cursor,
            page_size=page_size,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
            _gql=gql,
            _gql_builder=gql_builder,
            _federator=federator,
            gql_headers=gql_headers,
        )
        return Page(items=normalize_logs(items), next_cursor=next_cursor)
    finally:
        await http.aclose()


async def get_token_transfers_page_typed(
    *,
    address: str | None = None,
    token_contract: str | None = None,
    api_kind: str,
    network: str,
    api_key: str,
    first: int | None = None,
    after: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> Page[TokenTransferDTO]:
    """GraphQL-capable typed facade returning Page[TokenTransferDTO]."""
    from aiochainscan.adapters.aiohttp_graphql_client import AiohttpGraphQLClient
    from aiochainscan.adapters.blockscout_graphql_builder import (
        BlockscoutGraphQLBuilder,
    )
    from aiochainscan.adapters.simple_provider_federator import SimpleProviderFederator
    from aiochainscan.services.account import normalize_token_transfers

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    gql = AiohttpGraphQLClient()
    gql_builder = BlockscoutGraphQLBuilder()
    federator = SimpleProviderFederator()
    try:
        # GraphQL path when token_contract or address available
        items: list[dict[str, Any]] = []
        next_cursor: str | None = None
        if federator.should_use_graphql('token_transfers', api_kind=api_kind, network=network):
            base = endpoint.open(
                api_key=api_key, api_kind=api_kind, network=network
            ).base_url.rstrip('/')
            candidates = [
                f'{base}/api/v1/graphql',
                f'{base}/api/graphql',
                f'{base}/graphql',
                f'{base}/graphiql',
            ]
            query, variables = gql_builder.build_token_transfers_query(
                address=address,
                token_contract=token_contract,
                after_cursor=after,
                first=first,
            )
            _, headers = endpoint.open(
                api_key=api_key, api_kind=api_kind, network=network
            ).filter_and_sign(params=None, headers=None)
            for u in candidates:
                try:
                    data = await gql.execute(u, query, variables, headers)
                    items, next_cursor = gql_builder.map_token_transfers_response(data)
                    break
                except Exception:
                    continue
        if not items:
            # Fallback: REST page (page/offset → not cursor). Return opaque cursors as None.
            items = await get_token_transfers_service(
                address=address,
                contract_address=token_contract,
                start_block=None,
                end_block=None,
                sort=None,
                page=None,
                offset=None,
                token_standard='erc20',
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=endpoint,
            )
        return Page(items=normalize_token_transfers(items), next_cursor=next_cursor)
    finally:
        await http.aclose()


async def get_address_transactions_page_typed(
    *,
    address: str,
    api_kind: str,
    network: str,
    api_key: str,
    first: int | None = None,
    after: str | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
) -> Page[NormalTxDTO]:
    from aiochainscan.adapters.aiohttp_graphql_client import AiohttpGraphQLClient
    from aiochainscan.adapters.blockscout_graphql_builder import BlockscoutGraphQLBuilder
    from aiochainscan.adapters.simple_provider_federator import SimpleProviderFederator
    from aiochainscan.services.account import normalize_normal_txs

    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    gql = AiohttpGraphQLClient()
    gql_builder = BlockscoutGraphQLBuilder()
    federator = SimpleProviderFederator()
    try:
        items: list[dict[str, Any]] = []
        next_cursor: str | None = None
        if federator.should_use_graphql(
            'address_transactions', api_kind=api_kind, network=network
        ):
            base = endpoint.open(
                api_key=api_key, api_kind=api_kind, network=network
            ).base_url.rstrip('/')
            candidates = [
                f'{base}/api/v1/graphql',
                f'{base}/api/graphql',
                f'{base}/graphql',
                f'{base}/graphiql',
            ]
            query, variables = gql_builder.build_address_transactions_query(
                address=address, after_cursor=after, first=first
            )
            _, headers = endpoint.open(
                api_key=api_key, api_kind=api_kind, network=network
            ).filter_and_sign(params=None, headers=None)
            for u in candidates:
                try:
                    data = await gql.execute(u, query, variables, headers)
                    items, next_cursor = gql_builder.map_address_transactions_response(data)
                    break
                except Exception:
                    continue
        if not items:
            # fallback: REST txlist page; opaque cursor=N/A
            from aiochainscan.services.account import (
                get_normal_transactions as get_normal_transactions_service,
            )

            items = await get_normal_transactions_service(
                address=address,
                start_block=None,
                end_block=None,
                sort=None,
                page=None,
                offset=None,
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=endpoint,
            )
        return Page(items=normalize_normal_txs(items), next_cursor=next_cursor)
    finally:
        await http.aclose()


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


async def get_daily_block_count_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_block_count(**kwargs)
    return normalize_daily_block_count(items)


async def get_daily_average_network_hash_rate_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_daily_average_network_hash_rate(**kwargs)
    return normalize_daily_average_network_hash_rate(items)


async def get_daily_average_network_difficulty_typed(
    **kwargs: Any,
) -> list[DailySeriesDTO]:
    items = await get_daily_average_network_difficulty(**kwargs)
    return normalize_daily_average_network_difficulty(items)


async def get_ether_historical_daily_market_cap_typed(
    **kwargs: Any,
) -> list[DailySeriesDTO]:
    items = await get_ether_historical_daily_market_cap(**kwargs)
    return normalize_ether_historical_daily_market_cap(items)


async def get_ether_historical_price_typed(**kwargs: Any) -> list[DailySeriesDTO]:
    items = await get_ether_historical_price(**kwargs)
    return normalize_ether_historical_price(items)


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


async def get_all_transactions_optimized(
    *,
    address: str,
    start_block: int | None = None,
    end_block: int | None = None,
    max_concurrent: int = 5,
    max_offset: int = 10_000,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    min_range_width: int = 1_000,
    max_attempts_per_range: int = 3,
    prefer_paging: bool | None = None,
    stats: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Optimized fetch of all normal transactions via services layer.

    Uses range splitting + priority queue under the hood, respects rate limits
    and works with Blockscout without API key.
    """
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_all_transactions_optimized_service(
            address=address,
            start_block=start_block,
            end_block=end_block,
            max_concurrent=max_concurrent,
            max_offset=max_offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
            min_range_width=min_range_width,
            max_attempts_per_range=max_attempts_per_range,
            prefer_paging=prefer_paging,
            stats=stats,
        )
    finally:
        await http.aclose()


async def get_all_transactions_optimized_typed(
    *,
    address: str,
    start_block: int | None = None,
    end_block: int | None = None,
    max_concurrent: int = 5,
    max_offset: int = 10_000,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    min_range_width: int = 1_000,
    max_attempts_per_range: int = 3,
) -> list[NormalTxDTO]:
    items = await get_all_transactions_optimized(
        address=address,
        start_block=start_block,
        end_block=end_block,
        max_concurrent=max_concurrent,
        max_offset=max_offset,
        api_kind=api_kind,
        network=network,
        api_key=api_key,
        http=http,
        endpoint_builder=endpoint_builder,
        rate_limiter=rate_limiter,
        retry=retry,
        telemetry=telemetry,
        min_range_width=min_range_width,
        max_attempts_per_range=max_attempts_per_range,
    )
    return normalize_normal_txs(items)


async def get_all_internal_transactions_optimized(
    *,
    address: str,
    start_block: int | None = None,
    end_block: int | None = None,
    max_concurrent: int = 5,
    max_offset: int = 10_000,
    api_kind: str,
    network: str,
    api_key: str,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    min_range_width: int = 1_000,
    max_attempts_per_range: int = 3,
    stats: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        return await get_all_internal_transactions_optimized_service(
            address=address,
            start_block=start_block,
            end_block=end_block,
            max_concurrent=max_concurrent,
            max_offset=max_offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
            min_range_width=min_range_width,
            max_attempts_per_range=max_attempts_per_range,
            stats=stats,
        )
    finally:
        await http.aclose()


async def get_all_logs_optimized(
    *,
    address: str,
    start_block: int | None = None,
    end_block: int | None = None,
    max_concurrent: int = 3,
    max_offset: int = 1_000,
    api_kind: str,
    network: str,
    api_key: str,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
    http: HttpClient | None = None,
    endpoint_builder: EndpointBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    retry: RetryPolicy | None = None,
    telemetry: Telemetry | None = None,
    min_range_width: int = 1_000,
    max_attempts_per_range: int = 3,
    stats: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    http = http or AiohttpClient()
    endpoint = endpoint_builder or UrlBuilderEndpoint()
    telemetry = telemetry or StructlogTelemetry()
    try:
        from aiochainscan.services.logs import (
            get_all_logs_optimized as get_all_logs_optimized_service,
        )

        return await get_all_logs_optimized_service(
            address=address,
            start_block=start_block,
            end_block=end_block,
            max_concurrent=max_concurrent,
            max_offset=max_offset,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
            topics=topics,
            topic_operators=topic_operators,
            _rate_limiter=rate_limiter,
            _retry=retry,
            _telemetry=telemetry,
            min_range_width=min_range_width,
            max_attempts_per_range=max_attempts_per_range,
            stats=stats,
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


async def get_daily_block_count(
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
    from aiochainscan.services.stats import get_daily_block_count as svc

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


async def get_daily_average_network_hash_rate(
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
    from aiochainscan.services.stats import get_daily_average_network_hash_rate as svc

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


async def get_daily_average_network_difficulty(
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
    from aiochainscan.services.stats import get_daily_average_network_difficulty as svc

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


async def get_ether_historical_daily_market_cap(
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
    from aiochainscan.services.stats import get_ether_historical_daily_market_cap as svc

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


async def get_ether_historical_price(
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
    from aiochainscan.services.stats import get_ether_historical_price as svc

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
