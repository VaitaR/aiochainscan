"""aiochainscan public API (modern client only)."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

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
    AbiTypeNotSupportedError,
    BlockRangeNotSupportedError,
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanDataError,
    ChainscanNetworkError,
    ChainscanProviderSwitchWarning,
    ChainscanRateLimitError,
    ChainscanResultWindowExceededError,
    ChainscanWaitTimeoutError,
    CompletenessUnavailableError,
    MethodNotDeclaredError,
    PaginationDataLossError,
    ProviderPoolExhaustedError,
    PureAbiDecodeWarning,
)
from aiochainscan.scanners import list_scanners, register_scanner
from aiochainscan.services.chain_info import ChainInfo

# Single source of truth is the distribution metadata (pyproject `version`);
# the literal is the fallback for a source tree that was never installed.
try:
    __version__ = _dist_version('aiochainscan')
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = '1.0.5'

__all__ = [
    'AbiTypeNotSupportedError',
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
    'ChainscanResultWindowExceededError',
    'ChainscanWaitTimeoutError',
    'CompletenessUnavailableError',
    'DecodedEvent',
    'DecodedTransaction',
    'FailureKind',
    'Method',
    'MethodNotDeclaredError',
    'PaginationDataLossError',
    'ProviderPoolExhaustedError',
    'PureAbiDecodeWarning',
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
