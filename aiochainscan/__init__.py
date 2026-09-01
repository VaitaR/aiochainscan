"""aiochainscan public API (modern client only)."""

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method
from aiochainscan.core.pool import ChainscanPool, FailureKind, classify_failure
from aiochainscan.domain.contract import DecodedEvent, DecodedTransaction, SmartContract
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanDataError,
    ChainscanNetworkError,
    ChainscanProviderSwitchWarning,
    ChainscanRateLimitError,
    ChainscanWaitTimeoutError,
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
    'ChainscanDataError',
    'ChainscanClientApiError',
    'ChainscanClientError',
    'ChainscanNetworkError',
    'ChainscanPool',
    'ChainscanProviderSwitchWarning',
    'ChainscanRateLimitError',
    'ChainscanWaitTimeoutError',
    'DecodedEvent',
    'DecodedTransaction',
    'FailureKind',
    'Method',
    'MethodNotDeclaredError',
    'PaginationDataLossError',
    'ProviderPoolExhaustedError',
    'SmartContract',
    'classify_failure',
    'list_scanners',
    'register_scanner',
]
