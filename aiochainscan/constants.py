"""Centralized constants for aiochainscan.

This module defines named constants for magic numbers used throughout the codebase.
Constants improve code readability and maintainability by documenting the purpose
of specific values and making them easy to change globally.

Categories:
- API_*: API pagination and request limits
- RATE_*: Rate limiting configuration
- CACHE_*: Cache size and TTL defaults
- NETWORK_*: Network transport defaults
- ETH_*: Ethereum-specific constants
- BATCH_*: Batch processing sizes
"""

from __future__ import annotations

# =============================================================================
# API PAGINATION LIMITS
# =============================================================================

#: Maximum items per page for Etherscan-family APIs (page * offset <= 10,000)
API_MAX_OFFSET_ETHERSCAN: int = 10_000

#: Largest ``offset`` Etherscan v2 actually serves in one page. It does NOT
#: reject a bigger one: ``offset=10000`` answers 1000 items with ``status=1``,
#: which reads as "the data ended" to any partial-page stop condition. Verified
#: live 2026-09-02 on ``api.etherscan.io/v2`` (txlist and logs alike).
API_MAX_PAGE_SIZE_ETHERSCAN: int = 1_000

#: Hard per-request log limit of the Etherscan-compatible ``logs/getLogs``
#: endpoint. BlockScout V1 enforces it while ignoring page/offset entirely, so
#: it is that endpoint's whole result window (see
#: ``BlockScoutV1.RESULT_WINDOW_OVERRIDES``).
API_MAX_OFFSET_LOGS: int = 1_000

#: Default chunk size for block range chunking (large contract queries)
API_CHUNK_SIZE_BLOCKS: int = 100_000

# =============================================================================
# RATE LIMITING
# =============================================================================

#: Default requests per second for rate limiting
RATE_DEFAULT_RPS: float = 5.0

#: Time period for rate limiting (seconds)
RATE_TIME_PERIOD: float = 1.0

#: Default burst size for rate limiting.
#: Set to 1.0 to prevent burst requests that trigger WAF/DDoS detection.
#: API gateways (Cloudflare protecting Etherscan/BlockScout) interpret
#: HTTP/2 multiplexed burst requests as Layer 7 DDoS attacks.
RATE_DEFAULT_BURST: float = 1.0

# =============================================================================
# RETRY CONFIGURATION
# =============================================================================

#: Maximum retry attempts for failed requests
RETRY_MAX_ATTEMPTS: int = 5

#: Minimum wait time between retries (seconds)
RETRY_MIN_WAIT: float = 1.0

#: Maximum wait time between retries (seconds)
RETRY_MAX_WAIT: float = 30.0

# =============================================================================
# CACHE CONFIGURATION
# =============================================================================

#: Default maximum size for in-memory cache (LRU entries)
CACHE_DEFAULT_MAX_SIZE: int = 10_000

# =============================================================================
# NETWORK TRANSPORT
# =============================================================================

#: Default request timeout (seconds)
NETWORK_DEFAULT_TIMEOUT: float = 10.0

#: Default maximum connections in connection pool
NETWORK_MAX_CONNECTIONS: int = 10

#: Maximum response body size buffered and parsed by the transport
NETWORK_MAX_RESPONSE_BYTES: int = 64 * 1024 * 1024

#: Maximum size of response/error excerpts retained in exception messages
NETWORK_ERROR_EXCERPT_BYTES: int = 4_096

# =============================================================================
# BATCH PROCESSING
# =============================================================================

#: Default batch size for streaming iteration
BATCH_DEFAULT_SIZE: int = 1_000

#: Maximum concurrent chunks for parallel fetching
BATCH_MAX_CONCURRENT_CHUNKS: int = 3

#: Default concurrent requests for fast mode
BATCH_DEFAULT_CONCURRENCY: int = 8

# =============================================================================
# ETHEREUM-SPECIFIC
# =============================================================================

#: Standard decimals for ETH and most ERC-20 tokens
ETH_DECIMALS: int = 18

#: Standard byte length of Ethereum address (without 0x prefix)
ETH_ADDRESS_BYTES: int = 20

#: Standard byte length of Ethereum hash (without 0x prefix)
ETH_HASH_BYTES: int = 32

#: Standard byte length of padded ABI word
ETH_WORD_BYTES: int = 32

#: Maximum reasonable string length for ENS names (sanity check)
ENS_MAX_NAME_LENGTH: int = 1_000

# =============================================================================
# BLOCK NUMBER SENTINEL
# =============================================================================

#: Sentinel "latest" block number used when the real latest block cannot be
#: resolved.  Must be larger than any block number that will ever exist on any
#: EVM chain.  2**63-1 is the maximum signed 64-bit integer and comfortably
#: exceeds any realistic block height.
MAX_BLOCK_NUMBER: int = 2**63 - 1
