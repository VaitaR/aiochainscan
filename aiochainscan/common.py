from datetime import date


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
