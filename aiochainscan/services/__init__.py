"""Application services (use-cases)."""

from .account import get_address_balance
from .block import get_block_by_number, get_block_countdown
from .gas import get_gas_estimate, get_gas_oracle
from .stats import (
    get_eth2_supply,
    get_eth_price,
    get_eth_supply,
    get_total_nodes_count,
)
from .token import (
    get_address_token_balance,
    get_address_token_nft_balance,
    get_address_token_nft_inventory,
    get_token_balance,
    get_token_balance_history,
    get_token_holder_list,
    get_token_info,
    get_token_total_supply,
    get_token_total_supply_by_block,
)
from .transaction import (
    get_contract_execution_status,
    get_transaction_by_hash,
    get_tx_receipt_status,
)
from .unified_fetch import fetch_all

__all__ = [
    'get_address_balance',
    'get_block_by_number',
    'get_block_countdown',
    'get_transaction_by_hash',
    'get_tx_receipt_status',
    'get_contract_execution_status',
    'get_token_balance',
    'get_token_total_supply',
    'get_token_total_supply_by_block',
    'get_token_balance_history',
    'get_token_holder_list',
    'get_token_info',
    'get_address_token_balance',
    'get_address_token_nft_balance',
    'get_address_token_nft_inventory',
    'get_gas_oracle',
    'get_gas_estimate',
    'get_eth_price',
    'get_eth_supply',
    'get_eth2_supply',
    'get_total_nodes_count',
    'fetch_all',
]
