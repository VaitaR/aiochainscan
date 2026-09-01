from __future__ import annotations

"""Centralized TTL constants for caching in services.

Conservative defaults; individual services may override via DI if needed.
"""

# Blocks / proxy derived reads
CACHE_TTL_BLOCK_SECONDS: int = 5

# Gas oracle
CACHE_TTL_GAS_SECONDS: int = 5

# Logs queries
CACHE_TTL_LOGS_SECONDS: int = 15

# Token balance
CACHE_TTL_TOKEN_BALANCE_SECONDS: int = 10

# ETH price stats
CACHE_TTL_ETH_PRICE_SECONDS: int = 30

# Chain identity probes (BlockScout eth_chainId) and the Etherscan V2
# chainlist registry (~60 networks, downloaded at most once per window)
CACHE_TTL_CHAIN_INFO_SECONDS: int = 3600
