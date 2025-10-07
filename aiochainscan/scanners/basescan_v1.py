"""
BaseScan API v1 scanner implementation.

BaseScan uses the legacy Etherscan-style API structure
with a different domain (basescan.org instead of etherscan.io).
"""

from . import register_scanner
from ._etherscan_like import EtherscanLikeScanner


@register_scanner
class BaseScanV1(EtherscanLikeScanner):
    """
    BaseScan API v1 implementation.

    Inherits all functionality from the shared Etherscan-like base since BaseScan uses
    the same endpoint layout, just with basescan.org domain.

    Supports Base network and its testnets:
    - main: Base mainnet
    - goerli: Base Goerli testnet
    - sepolia: Base Sepolia testnet
    """

    name = 'basescan'
    version = 'v1'
    supported_networks = {'main', 'goerli', 'sepolia'}

    # All SPECS are inherited from the shared Etherscan-like implementation.
    # Auth settings are also inherited:
    # - auth_mode = "query"
    # - auth_field = "apikey"
    #
    # This means BaseScan automatically supports all 17 methods:
    # - ACCOUNT_BALANCE, ACCOUNT_TRANSACTIONS, ACCOUNT_INTERNAL_TXS
    # - ACCOUNT_ERC20_TRANSFERS, ACCOUNT_ERC721_TRANSFERS, ACCOUNT_ERC1155_TRANSFERS
    # - TX_BY_HASH, TX_RECEIPT_STATUS, BLOCK_BY_NUMBER, BLOCK_REWARD
    # - CONTRACT_ABI, CONTRACT_SOURCE, TOKEN_BALANCE, TOKEN_SUPPLY
    # - GAS_ORACLE, EVENT_LOGS, ETH_SUPPLY, ETH_PRICE, PROXY_ETH_CALL
