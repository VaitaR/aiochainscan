"""
Logical methods enum for unified API operations.
"""

from enum import Enum, auto


class Method(Enum):
    """
    Logical operations supported across different blockchain scanners.

    Each method represents a conceptual operation that can be implemented
    differently by various scanners but provides the same logical result.
    """

    # Account operations
    ACCOUNT_BALANCE = auto()
    ACCOUNT_TRANSACTIONS = auto()
    ACCOUNT_INTERNAL_TXS = auto()
    ACCOUNT_ERC20_TRANSFERS = auto()
    ACCOUNT_ERC721_TRANSFERS = auto()
    ACCOUNT_ERC1155_TRANSFERS = auto()

    # Transaction operations
    TX_BY_HASH = auto()
    TX_RECEIPT_STATUS = auto()
    TX_STATUS_CHECK = auto()

    # Block operations
    BLOCK_BY_NUMBER = auto()
    BLOCK_REWARD = auto()
    BLOCK_COUNTDOWN = auto()
    BLOCK_NUMBER_BY_TIMESTAMP = auto()

    # Contract operations
    CONTRACT_ABI = auto()
    CONTRACT_SOURCE = auto()
    CONTRACT_CREATION = auto()

    # Token operations
    TOKEN_BALANCE = auto()
    TOKEN_SUPPLY = auto()
    TOKEN_INFO = auto()

    # Gas operations
    GAS_ESTIMATE = auto()
    GAS_ORACLE = auto()

    # Event logs
    EVENT_LOGS = auto()

    # Statistics
    ETH_SUPPLY = auto()
    ETH_PRICE = auto()

    # Proxy operations
    PROXY_ETH_CALL = auto()
    PROXY_GET_BALANCE = auto()

    def __str__(self) -> str:
        """Return a human-readable string representation."""
        return self.name.lower().replace('_', ' ').title()
