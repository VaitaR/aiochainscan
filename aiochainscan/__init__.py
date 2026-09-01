"""aiochainscan public API (modern client only)."""

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method
from aiochainscan.domain.contract import DecodedEvent, DecodedTransaction, SmartContract
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
    ChainscanWaitTimeoutError,
    PaginationDataLossError,
)
from aiochainscan.scanners import list_scanners, register_scanner

__version__ = '0.6.0'

__all__ = [
    'ChainscanClient',
    'ChainscanClientApiError',
    'ChainscanClientError',
    'ChainscanNetworkError',
    'ChainscanRateLimitError',
    'ChainscanWaitTimeoutError',
    'DecodedEvent',
    'DecodedTransaction',
    'Method',
    'PaginationDataLossError',
    'SmartContract',
    'list_scanners',
    'register_scanner',
]
