from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiochainscan.client import Client


class ChainFeatures(Enum):
    """Enum for blockchain scanner feature capabilities."""

    # Token features
    ERC20_TRANSFERS = 'erc20_transfers'
    TOKEN_SUPPLY_BY_BLOCK = 'token_supply_by_block'
    TOKEN_BALANCE_BY_BLOCK = 'token_balance_by_block'

    # Account features
    ACCOUNT_BALANCE_HISTORY = 'account_balance_history'

    # Advanced features
    CONTRACT_SOURCE = 'contract_source'
    INTERNAL_TRANSACTIONS = 'internal_transactions'


# Scanner feature capabilities mapping
SCANNER_FEATURES = {
    'eth': {
        ChainFeatures.ERC20_TRANSFERS,
        ChainFeatures.TOKEN_SUPPLY_BY_BLOCK,
        ChainFeatures.TOKEN_BALANCE_BY_BLOCK,
        ChainFeatures.ACCOUNT_BALANCE_HISTORY,
        ChainFeatures.CONTRACT_SOURCE,
        ChainFeatures.INTERNAL_TRANSACTIONS,
    },
    'bsc': {
        ChainFeatures.ERC20_TRANSFERS,
        ChainFeatures.TOKEN_SUPPLY_BY_BLOCK,
        ChainFeatures.TOKEN_BALANCE_BY_BLOCK,
        ChainFeatures.CONTRACT_SOURCE,
        ChainFeatures.INTERNAL_TRANSACTIONS,
    },
    'polygon': {
        ChainFeatures.ERC20_TRANSFERS,
        ChainFeatures.TOKEN_SUPPLY_BY_BLOCK,
        ChainFeatures.TOKEN_BALANCE_BY_BLOCK,
        ChainFeatures.CONTRACT_SOURCE,
        ChainFeatures.INTERNAL_TRANSACTIONS,
    },
    'arbitrum': {
        ChainFeatures.ERC20_TRANSFERS,
        ChainFeatures.TOKEN_SUPPLY_BY_BLOCK,
        ChainFeatures.TOKEN_BALANCE_BY_BLOCK,
        ChainFeatures.CONTRACT_SOURCE,
        ChainFeatures.INTERNAL_TRANSACTIONS,
    },
    'optimism': {
        ChainFeatures.ERC20_TRANSFERS,
        ChainFeatures.CONTRACT_SOURCE,
        ChainFeatures.INTERNAL_TRANSACTIONS,
    },
    'fantom': {
        ChainFeatures.ERC20_TRANSFERS,
        ChainFeatures.CONTRACT_SOURCE,
        ChainFeatures.INTERNAL_TRANSACTIONS,
    },
    'gnosis': {
        ChainFeatures.ERC20_TRANSFERS,
        ChainFeatures.CONTRACT_SOURCE,
        ChainFeatures.INTERNAL_TRANSACTIONS,
    },
    'base': {
        ChainFeatures.ERC20_TRANSFERS,
        ChainFeatures.CONTRACT_SOURCE,
        ChainFeatures.INTERNAL_TRANSACTIONS,
    },
    'linea': {
        ChainFeatures.ERC20_TRANSFERS,
        ChainFeatures.CONTRACT_SOURCE,
    },
    'blast': {
        ChainFeatures.ERC20_TRANSFERS,
        ChainFeatures.CONTRACT_SOURCE,
    },
    'xlayer': {
        ChainFeatures.ERC20_TRANSFERS,
    },
    'flare': {
        ChainFeatures.ERC20_TRANSFERS,
    },
    'wemix': {
        ChainFeatures.ERC20_TRANSFERS,
    },
    'chiliz': {
        ChainFeatures.ERC20_TRANSFERS,
    },
    'mode': {
        ChainFeatures.ERC20_TRANSFERS,
    },
}


def check_feature_support(client: 'Client', feature: ChainFeatures) -> bool:
    """Check if a feature is supported by the current scanner."""
    scanner_id = client._url_builder._api_kind
    scanner_features = SCANNER_FEATURES.get(scanner_id, set())
    return feature in scanner_features


def require_feature_support(client: 'Client', feature: ChainFeatures) -> None:
    """Raise FeatureNotSupportedError if the feature is not supported by the current scanner."""
    if not check_feature_support(client, feature):
        from aiochainscan.config import config_manager
        from aiochainscan.exceptions import FeatureNotSupportedError

        scanner_id = client._url_builder._api_kind
        scanner_config = config_manager.get_scanner_config(scanner_id)
        raise FeatureNotSupportedError(feature.value, scanner_config.name)


def check_value(value: str, values: tuple[str, ...]) -> str:
    if value and value.lower() not in values:
        raise ValueError(f'Invalid value {value!r}, only {values} are supported.')
    return value


def check_hex(number: str | int) -> str:
    if isinstance(number, int):
        return hex(number)
    try:
        int(number, 16)
    except ValueError as e:
        raise ValueError(f'Invalid hex parameter {number!r}: {e}') from e
    else:
        return number


def check_tag(tag: str | int) -> str:
    _tags = (
        'earliest',  # the earliest/genesis block
        'latest',  # the latest mined block
        'pending',  # for the pending state/transactions
    )

    if tag in _tags:
        return tag
    return check_hex(tag)


def check_sort_direction(sort: str) -> str:
    _sort_orders = (
        'asc',  # ascending order
        'desc',  # descending order
    )
    return check_value(sort, _sort_orders)


def check_blocktype(blocktype: str) -> str:
    _block_types = (
        'blocks',  # full blocks only
        'uncles',  # uncle blocks only
    )
    return check_value(blocktype, _block_types)


def check_closest_value(closest_value: str) -> str:
    _closest_values = (
        'before',  # ascending order
        'after',  # descending order
    )

    return check_value(closest_value, _closest_values)


def check_client_type(client_type: str) -> str:
    _client_types = (
        'geth',
        'parity',
    )

    return check_value(client_type, _client_types)


def check_sync_mode(sync_mode: str) -> str:
    _sync_modes = (
        'default',
        'archive',
    )

    return check_value(sync_mode, _sync_modes)


def check_token_standard(token_standard: str) -> str:
    _token_standards = (
        'erc20',
        'erc721',
        'erc1155',
    )

    return check_value(token_standard, _token_standards)


def get_daily_stats_params(action: str, start_date: date, end_date: date, sort: str) -> dict:
    return {
        'module': 'stats',
        'action': action,
        'startdate': start_date.isoformat(),
        'enddate': end_date.isoformat(),
        'sort': check_sort_direction(sort),
    }
