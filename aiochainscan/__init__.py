"""aiochainscan public API (modern client only)."""

from aiochainscan.convert import (
    format_ether,
    hex_to_int,
    hex_to_str,
    to_datetime,
    to_decimal_amount,
    to_iso,
    wei_to_ether,
)
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.pool import ChainscanPool, FailureKind, classify_failure
from aiochainscan.domain.contract import DecodedEvent, DecodedTransaction, SmartContract
from aiochainscan.domain.method import Method
from aiochainscan.exceptions import (
    BlockRangeNotSupportedError,
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanDataError,
    ChainscanNetworkError,
    ChainscanProviderSwitchWarning,
    ChainscanRateLimitError,
    ChainscanWaitTimeoutError,
    CompletenessUnavailableError,
    MethodNotDeclaredError,
    PaginationDataLossError,
    ProviderPoolExhaustedError,
)
from aiochainscan.scanners import list_scanners, register_scanner
from aiochainscan.services.chain_info import ChainInfo

__version__ = '0.6.0'

__all__ = [
    'ChainInfo',
    'ChainscanClient',
    'BlockRangeNotSupportedError',
    'ChainscanDataError',
    'ChainscanClientApiError',
    'ChainscanClientError',
    'ChainscanNetworkError',
    'ChainscanPool',
    'ChainscanProviderSwitchWarning',
    'ChainscanRateLimitError',
    'ChainscanWaitTimeoutError',
    'CompletenessUnavailableError',
    'DecodedEvent',
    'DecodedTransaction',
    'FailureKind',
    'Method',
    'MethodNotDeclaredError',
    'PaginationDataLossError',
    'ProviderPoolExhaustedError',
    'SmartContract',
    'classify_failure',
    'format_ether',
    'hex_to_int',
    'hex_to_str',
    'list_scanners',
    'register_scanner',
    'to_datetime',
    'to_decimal_amount',
    'to_iso',
    'wei_to_ether',
]
