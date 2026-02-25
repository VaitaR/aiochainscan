"""Adapters: concrete implementations of ports."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .aiohttp_client import AiohttpClient as AiohttpClientType
else:
    AiohttpClientType = Any

try:
    from .aiohttp_client import AiohttpClient
except ImportError:
    AiohttpClient = None  # type: ignore[misc, assignment]

from .aiolimiter_adapter import AioLimiterAdapter
from .httpx_client import HttpxClientAdapter
from .retry_exponential import ExponentialBackoffRetry
from .simple_rate_limiter import SimpleRateLimiter
from .tenacity_retry import TenacityRetryAdapter

__all__ = [
    'AiohttpClient',
    'AioLimiterAdapter',
    'ExponentialBackoffRetry',
    'HttpxClientAdapter',
    'SimpleRateLimiter',
    'TenacityRetryAdapter',
]
