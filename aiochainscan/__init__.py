"""aiochainscan – async blockchain explorer client.

Uses PEP 562 module-level ``__getattr__`` for lazy imports so that
``from aiochainscan import ChainscanClient`` does not trigger loading
of every adapter, service, and facade function.
"""

from __future__ import annotations

from typing import Any

__version__ = '0.4.1'

# ---------------------------------------------------------------------------
# Lazy-import registry: symbol_name -> (module_path, attribute_name)
# ---------------------------------------------------------------------------
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # --- Core ---
    'ChainscanClient': ('aiochainscan.core.client', 'ChainscanClient'),
    'Method': ('aiochainscan.core.method', 'Method'),
    # --- Config ---
    'ChainScanConfig': ('aiochainscan.config', 'ChainScanConfig'),
    'ScannerConfig': ('aiochainscan.config', 'ScannerConfig'),
    'config': ('aiochainscan.config', 'config'),
    # --- Domain value objects ---
    'Address': ('aiochainscan.domain.models', 'Address'),
    'BlockNumber': ('aiochainscan.domain.models', 'BlockNumber'),
    'TxHash': ('aiochainscan.domain.models', 'TxHash'),
    'Page': ('aiochainscan.domain.models', 'Page'),
    # --- Smart contract ---
    'SmartContract': ('aiochainscan.domain.contract', 'SmartContract'),
    'DecodedEvent': ('aiochainscan.domain.contract', 'DecodedEvent'),
    'DecodedTransaction': ('aiochainscan.domain.contract', 'DecodedTransaction'),
    # --- ENS ---
    'ENSResolver': ('aiochainscan.services.ens_resolver', 'ENSResolver'),
    # --- Progress ---
    'ProgressCallback': ('aiochainscan.ports.progress', 'ProgressCallback'),
    'console_progress': ('aiochainscan.utils.progress_helpers', 'console_progress'),
    'tqdm_progress': ('aiochainscan.utils.progress_helpers', 'tqdm_progress'),
    'rich_progress': ('aiochainscan.utils.progress_helpers', 'rich_progress'),
    'logging_progress': ('aiochainscan.utils.progress_helpers', 'logging_progress'),
    'silent_progress': ('aiochainscan.utils.progress_helpers', 'silent_progress'),
    'callback_with_interval': ('aiochainscan.utils.progress_helpers', 'callback_with_interval'),
    # --- DTOs ---
    'AddressBalanceDTO': ('aiochainscan.domain.dto', 'AddressBalanceDTO'),
    'BeaconWithdrawalDTO': ('aiochainscan.domain.dto', 'BeaconWithdrawalDTO'),
    'BlockDTO': ('aiochainscan.domain.dto', 'BlockDTO'),
    'DailySeriesDTO': ('aiochainscan.domain.dto', 'DailySeriesDTO'),
    'EthPriceDTO': ('aiochainscan.domain.dto', 'EthPriceDTO'),
    'GasOracleDTO': ('aiochainscan.domain.dto', 'GasOracleDTO'),
    'InternalTxDTO': ('aiochainscan.domain.dto', 'InternalTxDTO'),
    'LogEntryDTO': ('aiochainscan.domain.dto', 'LogEntryDTO'),
    'MinedBlockDTO': ('aiochainscan.domain.dto', 'MinedBlockDTO'),
    'NormalTxDTO': ('aiochainscan.domain.dto', 'NormalTxDTO'),
    'ProxyTxDTO': ('aiochainscan.domain.dto', 'ProxyTxDTO'),
    'TokenTransferDTO': ('aiochainscan.domain.dto', 'TokenTransferDTO'),
    'TransactionDTO': ('aiochainscan.domain.dto', 'TransactionDTO'),
    'TokenBalanceDTO': ('aiochainscan.services.token', 'TokenBalanceDTO'),
    # --- V2 DTOs (Pydantic) ---
    'TransactionDTOv2': ('aiochainscan.domain.dto_v2', 'TransactionDTO'),
    'InternalTransactionDTOv2': ('aiochainscan.domain.dto_v2', 'InternalTransactionDTO'),
    'TokenTransferDTOv2': ('aiochainscan.domain.dto_v2', 'TokenTransferDTO'),
    'LogEventDTOv2': ('aiochainscan.domain.dto_v2', 'LogEventDTO'),
    'BlockDTOv2': ('aiochainscan.domain.dto_v2', 'BlockDTO'),
    # --- Adapters ---
    'HttpxClientAdapter': ('aiochainscan.adapters.httpx_client', 'HttpxClientAdapter'),
    'TenacityRetryAdapter': ('aiochainscan.adapters.tenacity_retry', 'TenacityRetryAdapter'),
    'AioLimiterAdapter': ('aiochainscan.adapters.aiolimiter_adapter', 'AioLimiterAdapter'),
    'UrlBuilderEndpoint': (
        'aiochainscan.adapters.endpoint_builder_urlbuilder',
        'UrlBuilderEndpoint',
    ),
    'StructlogTelemetry': ('aiochainscan.adapters.structlog_telemetry', 'StructlogTelemetry'),
    'SimpleRateLimiter': ('aiochainscan.adapters.simple_rate_limiter', 'SimpleRateLimiter'),
    'ExponentialBackoffRetry': (
        'aiochainscan.adapters.retry_exponential',
        'ExponentialBackoffRetry',
    ),
    # --- Ports ---
    'HttpClient': ('aiochainscan.ports.http_client', 'HttpClient'),
    'EndpointBuilder': ('aiochainscan.ports.endpoint_builder', 'EndpointBuilder'),
    'Cache': ('aiochainscan.ports.cache', 'Cache'),
    'RateLimiter': ('aiochainscan.ports.rate_limiter', 'RateLimiter'),
    'RetryPolicy': ('aiochainscan.ports.rate_limiter', 'RetryPolicy'),
    'Telemetry': ('aiochainscan.ports.telemetry', 'Telemetry'),
    # --- Service re-exports ---
    'get_address_balance': ('aiochainscan.services.account', 'get_address_balance'),
    'get_block_by_number': ('aiochainscan.services.block', 'get_block_by_number'),
    'get_transaction_by_hash': ('aiochainscan.services.transaction', 'get_transaction_by_hash'),
    # --- Normalizers ---
    'normalize_block': ('aiochainscan.services.block', 'normalize_block'),
    'normalize_transaction': ('aiochainscan.services.transaction', 'normalize_transaction'),
    'normalize_gas_oracle': ('aiochainscan.services.gas', 'normalize_gas_oracle'),
    'normalize_token_balance': ('aiochainscan.services.token', 'normalize_token_balance'),
    'normalize_log_entry': ('aiochainscan.services.logs', 'normalize_log_entry'),
    'normalize_logs': ('aiochainscan.services.logs', 'normalize_logs'),
    'normalize_proxy_tx': ('aiochainscan.services.proxy', 'normalize_proxy_tx'),
    'normalize_normal_txs': ('aiochainscan.services.account', 'normalize_normal_txs'),
    'normalize_internal_txs': ('aiochainscan.services.account', 'normalize_internal_txs'),
    'normalize_token_transfers': ('aiochainscan.services.account', 'normalize_token_transfers'),
    'normalize_mined_blocks': ('aiochainscan.services.account', 'normalize_mined_blocks'),
    'normalize_beacon_withdrawals': (
        'aiochainscan.services.account',
        'normalize_beacon_withdrawals',
    ),
    'normalize_address_balances': ('aiochainscan.services.account', 'normalize_address_balances'),
    'normalize_eth_price': ('aiochainscan.services.stats', 'normalize_eth_price'),
    'normalize_daily_transaction_count': (
        'aiochainscan.services.stats',
        'normalize_daily_transaction_count',
    ),
    'normalize_daily_new_address_count': (
        'aiochainscan.services.stats',
        'normalize_daily_new_address_count',
    ),
    'normalize_daily_network_tx_fee': (
        'aiochainscan.services.stats',
        'normalize_daily_network_tx_fee',
    ),
    'normalize_daily_network_utilization': (
        'aiochainscan.services.stats',
        'normalize_daily_network_utilization',
    ),
    'normalize_daily_average_block_size': (
        'aiochainscan.services.stats',
        'normalize_daily_average_block_size',
    ),
    'normalize_daily_block_rewards': (
        'aiochainscan.services.stats',
        'normalize_daily_block_rewards',
    ),
    'normalize_daily_average_block_time': (
        'aiochainscan.services.stats',
        'normalize_daily_average_block_time',
    ),
    'normalize_daily_uncle_block_count': (
        'aiochainscan.services.stats',
        'normalize_daily_uncle_block_count',
    ),
    'normalize_daily_average_gas_limit': (
        'aiochainscan.services.stats',
        'normalize_daily_average_gas_limit',
    ),
    'normalize_daily_total_gas_used': (
        'aiochainscan.services.stats',
        'normalize_daily_total_gas_used',
    ),
    'normalize_daily_average_gas_price': (
        'aiochainscan.services.stats',
        'normalize_daily_average_gas_price',
    ),
    'normalize_daily_block_count': ('aiochainscan.services.stats', 'normalize_daily_block_count'),
    'normalize_daily_average_network_hash_rate': (
        'aiochainscan.services.stats',
        'normalize_daily_average_network_hash_rate',
    ),
    'normalize_daily_average_network_difficulty': (
        'aiochainscan.services.stats',
        'normalize_daily_average_network_difficulty',
    ),
    'normalize_ether_historical_daily_market_cap': (
        'aiochainscan.services.stats',
        'normalize_ether_historical_daily_market_cap',
    ),
    'normalize_ether_historical_price': (
        'aiochainscan.services.stats',
        'normalize_ether_historical_price',
    ),
    # --- Deprecation helper ---
    '_warn_facade_deprecation': ('aiochainscan._facade', '_warn_facade_deprecation'),
    # --- Facade functions (deprecated, lazy-loaded from _facade) ---
    'get_balance': ('aiochainscan._facade', 'get_balance'),
    'get_block': ('aiochainscan._facade', 'get_block'),
    'get_address_balances': ('aiochainscan._facade', 'get_address_balances'),
    'get_normal_transactions': ('aiochainscan._facade', 'get_normal_transactions'),
    'get_all_transactions_optimized': ('aiochainscan._facade', 'get_all_transactions_optimized'),
    'get_all_transactions_optimized_typed': (
        'aiochainscan._facade',
        'get_all_transactions_optimized_typed',
    ),
    'get_all_internal_transactions_optimized': (
        'aiochainscan._facade',
        'get_all_internal_transactions_optimized',
    ),
    'get_all_logs_optimized': ('aiochainscan._facade', 'get_all_logs_optimized'),
    'get_internal_transactions': ('aiochainscan._facade', 'get_internal_transactions'),
    'get_token_transfers': ('aiochainscan._facade', 'get_token_transfers'),
    'get_mined_blocks': ('aiochainscan._facade', 'get_mined_blocks'),
    'get_beacon_chain_withdrawals': ('aiochainscan._facade', 'get_beacon_chain_withdrawals'),
    'get_account_balance_by_blockno': ('aiochainscan._facade', 'get_account_balance_by_blockno'),
    'get_transaction': ('aiochainscan._facade', 'get_transaction'),
    'get_token_balance': ('aiochainscan._facade', 'get_token_balance'),
    'get_gas_oracle': ('aiochainscan._facade', 'get_gas_oracle'),
    'get_logs': ('aiochainscan._facade', 'get_logs'),
    'get_eth_price': ('aiochainscan._facade', 'get_eth_price'),
    'get_daily_transaction_count': ('aiochainscan._facade', 'get_daily_transaction_count'),
    'get_daily_new_address_count': ('aiochainscan._facade', 'get_daily_new_address_count'),
    'get_daily_network_tx_fee': ('aiochainscan._facade', 'get_daily_network_tx_fee'),
    'get_daily_network_utilization': ('aiochainscan._facade', 'get_daily_network_utilization'),
    'get_daily_average_block_size': ('aiochainscan._facade', 'get_daily_average_block_size'),
    'get_daily_block_rewards': ('aiochainscan._facade', 'get_daily_block_rewards'),
    'get_daily_average_block_time': ('aiochainscan._facade', 'get_daily_average_block_time'),
    'get_daily_uncle_block_count': ('aiochainscan._facade', 'get_daily_uncle_block_count'),
    'get_daily_average_gas_limit': ('aiochainscan._facade', 'get_daily_average_gas_limit'),
    'get_daily_total_gas_used': ('aiochainscan._facade', 'get_daily_total_gas_used'),
    'get_daily_average_gas_price': ('aiochainscan._facade', 'get_daily_average_gas_price'),
    'get_daily_block_count': ('aiochainscan._facade', 'get_daily_block_count'),
    'get_daily_average_network_hash_rate': (
        'aiochainscan._facade',
        'get_daily_average_network_hash_rate',
    ),
    'get_daily_average_network_difficulty': (
        'aiochainscan._facade',
        'get_daily_average_network_difficulty',
    ),
    'get_ether_historical_daily_market_cap': (
        'aiochainscan._facade',
        'get_ether_historical_daily_market_cap',
    ),
    'get_ether_historical_price': ('aiochainscan._facade', 'get_ether_historical_price'),
    'get_block_number': ('aiochainscan._facade', 'get_block_number'),
    'get_gas_price': ('aiochainscan._facade', 'get_gas_price'),
    'get_tx_count': ('aiochainscan._facade', 'get_tx_count'),
    'get_code': ('aiochainscan._facade', 'get_code'),
    'eth_call': ('aiochainscan._facade', 'eth_call'),
    'get_storage_at': ('aiochainscan._facade', 'get_storage_at'),
    'get_block_tx_count_by_number': ('aiochainscan._facade', 'get_block_tx_count_by_number'),
    'get_tx_by_block_number_and_index': (
        'aiochainscan._facade',
        'get_tx_by_block_number_and_index',
    ),
    'get_uncle_by_block_number_and_index': (
        'aiochainscan._facade',
        'get_uncle_by_block_number_and_index',
    ),
    'estimate_gas': ('aiochainscan._facade', 'estimate_gas'),
    'send_raw_tx': ('aiochainscan._facade', 'send_raw_tx'),
    'get_tx_receipt': ('aiochainscan._facade', 'get_tx_receipt'),
    'get_contract_abi': ('aiochainscan._facade', 'get_contract_abi'),
    'get_contract_source_code': ('aiochainscan._facade', 'get_contract_source_code'),
    'verify_contract_source_code': ('aiochainscan._facade', 'verify_contract_source_code'),
    'check_verification_status': ('aiochainscan._facade', 'check_verification_status'),
    'verify_proxy_contract': ('aiochainscan._facade', 'verify_proxy_contract'),
    'check_proxy_contract_verification': (
        'aiochainscan._facade',
        'check_proxy_contract_verification',
    ),
    'get_contract_creation': ('aiochainscan._facade', 'get_contract_creation'),
    'open_default_session': ('aiochainscan._facade', 'open_default_session'),
    # --- Typed facade helpers ---
    'get_block_typed': ('aiochainscan._facade', 'get_block_typed'),
    'get_transaction_typed': ('aiochainscan._facade', 'get_transaction_typed'),
    'get_logs_typed': ('aiochainscan._facade', 'get_logs_typed'),
    'get_logs_page_typed': ('aiochainscan._facade', 'get_logs_page_typed'),
    'get_token_transfers_page_typed': ('aiochainscan._facade', 'get_token_transfers_page_typed'),
    'get_address_transactions_page_typed': (
        'aiochainscan._facade',
        'get_address_transactions_page_typed',
    ),
    'get_token_balance_typed': ('aiochainscan._facade', 'get_token_balance_typed'),
    'get_gas_oracle_typed': ('aiochainscan._facade', 'get_gas_oracle_typed'),
    'get_eth_price_typed': ('aiochainscan._facade', 'get_eth_price_typed'),
    'get_daily_transaction_count_typed': (
        'aiochainscan._facade',
        'get_daily_transaction_count_typed',
    ),
    'get_daily_new_address_count_typed': (
        'aiochainscan._facade',
        'get_daily_new_address_count_typed',
    ),
    'get_daily_network_tx_fee_typed': ('aiochainscan._facade', 'get_daily_network_tx_fee_typed'),
    'get_daily_network_utilization_typed': (
        'aiochainscan._facade',
        'get_daily_network_utilization_typed',
    ),
    'get_daily_average_block_size_typed': (
        'aiochainscan._facade',
        'get_daily_average_block_size_typed',
    ),
    'get_daily_block_rewards_typed': ('aiochainscan._facade', 'get_daily_block_rewards_typed'),
    'get_daily_average_block_time_typed': (
        'aiochainscan._facade',
        'get_daily_average_block_time_typed',
    ),
    'get_daily_uncle_block_count_typed': (
        'aiochainscan._facade',
        'get_daily_uncle_block_count_typed',
    ),
    'get_daily_average_gas_limit_typed': (
        'aiochainscan._facade',
        'get_daily_average_gas_limit_typed',
    ),
    'get_daily_total_gas_used_typed': ('aiochainscan._facade', 'get_daily_total_gas_used_typed'),
    'get_daily_average_gas_price_typed': (
        'aiochainscan._facade',
        'get_daily_average_gas_price_typed',
    ),
    'get_daily_block_count_typed': ('aiochainscan._facade', 'get_daily_block_count_typed'),
    'get_daily_average_network_hash_rate_typed': (
        'aiochainscan._facade',
        'get_daily_average_network_hash_rate_typed',
    ),
    'get_daily_average_network_difficulty_typed': (
        'aiochainscan._facade',
        'get_daily_average_network_difficulty_typed',
    ),
    'get_ether_historical_daily_market_cap_typed': (
        'aiochainscan._facade',
        'get_ether_historical_daily_market_cap_typed',
    ),
    'get_ether_historical_price_typed': (
        'aiochainscan._facade',
        'get_ether_historical_price_typed',
    ),
    # --- Capabilities facade ---
    'list_feature_matrix': ('aiochainscan._facade', 'list_feature_matrix'),
    'is_feature_supported': ('aiochainscan._facade', 'is_feature_supported'),
    'get_supported_scanners_for_feature': (
        'aiochainscan._facade',
        'get_supported_scanners_for_feature',
    ),
    'get_supported_features_for': ('aiochainscan._facade', 'get_supported_features_for'),
    'get_capabilities_overview': ('aiochainscan._facade', 'get_capabilities_overview'),
}

# ---------------------------------------------------------------------------
# Public API (types, models, adapters - NOT facade functions)
# ---------------------------------------------------------------------------
__all__ = [
    'ChainscanClient',
    'Method',
    'ChainScanConfig',
    'ScannerConfig',
    'config',
    'Address',
    'BlockNumber',
    'TxHash',
    'Page',
    'SmartContract',
    'DecodedEvent',
    'DecodedTransaction',
    'ENSResolver',
    'ProgressCallback',
    'console_progress',
    'tqdm_progress',
    'rich_progress',
    'logging_progress',
    'silent_progress',
    'callback_with_interval',
    'AddressBalanceDTO',
    'BeaconWithdrawalDTO',
    'BlockDTO',
    'DailySeriesDTO',
    'EthPriceDTO',
    'GasOracleDTO',
    'InternalTxDTO',
    'LogEntryDTO',
    'MinedBlockDTO',
    'NormalTxDTO',
    'ProxyTxDTO',
    'TokenTransferDTO',
    'TransactionDTO',
    'TokenBalanceDTO',
    'TransactionDTOv2',
    'InternalTransactionDTOv2',
    'TokenTransferDTOv2',
    'LogEventDTOv2',
    'BlockDTOv2',
    'HttpxClientAdapter',
    'TenacityRetryAdapter',
    'AioLimiterAdapter',
    'UrlBuilderEndpoint',
    'StructlogTelemetry',
    'SimpleRateLimiter',
    'ExponentialBackoffRetry',
    'HttpClient',
    'EndpointBuilder',
    'Cache',
    'RateLimiter',
    'RetryPolicy',
    'Telemetry',
]


# ---------------------------------------------------------------------------
# PEP 562 lazy import machinery
# ---------------------------------------------------------------------------
def __getattr__(name: str) -> Any:
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        value = getattr(module, attr_name)
        globals()[name] = value  # cache for subsequent access
        return value
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def __dir__() -> list[str]:
    return list(__all__) + list(_LAZY_IMPORTS) + ['__version__']
