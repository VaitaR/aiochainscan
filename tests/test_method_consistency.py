"""Method ↔ convenience-mixin ↔ scanner-SPECS consistency guards.

This module walks the whole ``Method`` → mixin → ``EndpointSpec`` mapping so
mapping rot fails in CI instead of at a user's call site. It guards against:

1. ``SPECS`` keys that are not valid ``Method`` values.
2. Convenience methods whose ``Method`` target is declared by no scanner
   (the "orphan Method" class of bug).
3. Convenience methods passing parameter names that the target spec does not
   declare (the ``get_block`` ``blockno``-vs-``tag`` class of bug): every
   parameter a convenience method passes to ``call()`` must be either a key of
   the declaring spec's ``param_map`` or a path placeholder in the declaring
   spec's ``path``.
4. ``EtherscanV2`` silently drifting out of sync with the shared
   Etherscan-like spec surface.

The sweep is data-driven: a recording client invokes every convenience method
on each mixin, captures the ``(Method, params)`` pairs it hands to ``call()``,
and validates them against each scanner spec family that declares the method.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from typing import Any

import pytest

from aiochainscan.core.method import Method
from aiochainscan.core.mixins import (
    AccountMixin,
    BlockMixin,
    ContractMixin,
    LogsMixin,
    ProxyMixin,
    StatsMixin,
    TokenMixin,
    TransactionMixin,
)
from aiochainscan.scanners._etherscan_like import EtherscanLikeScanner
from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner
from aiochainscan.scanners.etherscan_v2 import EtherscanV2
from aiochainscan.scanners.nodereal import NodeRealScanner

CHECKSUM_ADDRESS = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
CONTRACT_ADDRESS = '0xdAC17F958D2ee523a2206208994597C13D831ec7'
TX_HASH = '0x' + 'ab' * 32
TRANSFER_TOPIC0 = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

# Distinct scanner spec families under test. BlockScout V1 shares the
# Etherscan-like SPECS object, so it is covered by the same dict.
SPEC_FAMILIES: dict[str, dict[Method, Any]] = {
    'etherscan-like (etherscan base, blockscout v1)': EtherscanLikeScanner.SPECS,
    'etherscan v2': EtherscanV2.SPECS,
    'blockscout v2': BlockScoutV2Scanner.SPECS,
    'nodereal v1': NodeRealScanner.SPECS,
}

# Scanner name (as set on ChainscanClient) -> spec families exercised with it.
SPECS_BY_SCANNER_NAME: dict[str, list[str]] = {
    'etherscan': ['etherscan-like (etherscan base, blockscout v1)', 'etherscan v2'],
    'blockscout': ['blockscout v2'],
    'nodereal': ['nodereal v1'],
}

# Every convenience method that reaches scanner specs directly via ``call()``.
# get_all_* aggregations are included to prove they stay callable; their
# params flow through the iter_*_streaming paths, not ``call()``.
INVOCATIONS: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {
    # Account
    'get_balance': ((CHECKSUM_ADDRESS,), {}),
    'get_transactions': ((CHECKSUM_ADDRESS,), {'start_block': 5, 'end_block': 10}),
    'get_token_transfers': ((CHECKSUM_ADDRESS,), {'contract_address': CONTRACT_ADDRESS}),
    'get_internal_transactions': ((CHECKSUM_ADDRESS,), {}),
    'get_token_portfolio': ((CHECKSUM_ADDRESS,), {}),
    'get_erc721_transfers': ((CHECKSUM_ADDRESS,), {'contract_address': CONTRACT_ADDRESS}),
    'get_erc1155_transfers': ((CHECKSUM_ADDRESS,), {'contract_address': CONTRACT_ADDRESS}),
    'get_nft_portfolio': ((CHECKSUM_ADDRESS,), {}),
    'get_all_transactions': ((CHECKSUM_ADDRESS,), {}),
    'get_all_token_transfers': ((CHECKSUM_ADDRESS,), {}),
    'get_all_internal_transactions': ((CHECKSUM_ADDRESS,), {}),
    # Transactions
    'get_transaction': ((TX_HASH,), {}),
    'get_transaction_status': ((TX_HASH,), {}),
    'check_transaction_status': ((TX_HASH,), {}),
    # Blocks
    'get_block': ((19_500_000,), {}),
    'get_block_reward': ((19_500_000,), {}),
    'get_block_countdown': ((30_000_000,), {}),
    'get_block_by_timestamp': ((1_609_459_200,), {}),
    # Contracts
    'get_contract_abi': ((CONTRACT_ADDRESS,), {}),
    'get_contract_source': ((CONTRACT_ADDRESS,), {}),
    'get_contract_creation': (([CONTRACT_ADDRESS],), {}),
    'get_contract': ((CONTRACT_ADDRESS,), {}),
    # Token
    'get_token_balance': ((CHECKSUM_ADDRESS, CONTRACT_ADDRESS), {}),
    'get_token_info': ((CONTRACT_ADDRESS,), {}),
    'get_token_supply': ((CONTRACT_ADDRESS,), {}),
    # Stats
    'get_eth_price': ((), {}),
    'get_gas_oracle': ((), {}),
    'get_gas_estimate': ((2_000_000_000,), {}),
    'get_eth_supply': ((), {}),
    # Logs
    'get_logs': (
        (CONTRACT_ADDRESS,),
        {'from_block': 100, 'to_block': 200, 'topic0': TRANSFER_TOPIC0},
    ),
    'get_all_logs': ((CONTRACT_ADDRESS,), {}),
    # Proxy
    'eth_call': ((CONTRACT_ADDRESS, '0x70a08231'), {}),
    'eth_get_balance': ((CHECKSUM_ADDRESS,), {}),
}

# Mixins whose public async methods must all appear in INVOCATIONS.
MIXINS: tuple[type, ...] = (
    AccountMixin,
    TransactionMixin,
    BlockMixin,
    ContractMixin,
    TokenMixin,
    StatsMixin,
    LogsMixin,
    ProxyMixin,
)


class _RecordingClient(
    AccountMixin,
    TransactionMixin,
    BlockMixin,
    ContractMixin,
    TokenMixin,
    StatsMixin,
    LogsMixin,
    ProxyMixin,
):
    """Mixin composition with a recording ``call()``; never touches network."""

    def __init__(self, scanner_name: str) -> None:
        self.scanner_name = scanner_name
        self.calls: list[tuple[Method, dict[str, Any]]] = []

    async def call(self, method: Method, **params: Any) -> Any:
        self.calls.append((method, params))
        if method == Method.CONTRACT_ABI:
            return '[]'  # JSON-encoded ABI (SmartContract.from_address contract)
        if method == Method.CONTRACT_SOURCE:
            return {}  # non-proxy source payload
        return []  # satisfies list/dict/str post-processing in the mixins

    async def _empty_stream(
        self, *_args: Any, **_kwargs: Any
    ) -> AsyncIterator[list[dict[str, Any]]]:
        yield []

    iter_transactions_streaming = _empty_stream
    iter_token_transfers_streaming = _empty_stream
    iter_internal_transactions_streaming = _empty_stream
    iter_logs_streaming = _empty_stream


def _public_convenience_methods(mixin: type) -> list[str]:
    return [
        name
        for name, member in inspect.getmembers(mixin, inspect.isfunction)
        if not name.startswith('_')
    ]


def _param_is_declared(spec: Any, param_name: str) -> bool:
    """A param is declared when it is a param_map key or a path placeholder."""
    return param_name in spec.param_map or f'{{{param_name}}}' in spec.path


# ---------------------------------------------------------------------------
# 1. Structural: SPECS keys are valid Method values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('family_label', sorted(SPEC_FAMILIES))
def test_spec_keys_are_method_values(family_label: str) -> None:
    specs = SPEC_FAMILIES[family_label]
    for key in specs:
        assert isinstance(key, Method), f'{family_label}: SPECS key {key!r} is not a Method value'


def test_etherscan_v2_inherits_full_base_spec_surface() -> None:
    """EtherscanV2 must inherit every Etherscan-like spec (plus EVENT_LOGS)."""
    missing = set(EtherscanLikeScanner.SPECS) - set(EtherscanV2.SPECS)
    assert not missing, (
        'EtherscanV2.SPECS is missing methods declared by the shared '
        f'Etherscan-like surface: {sorted(m.name for m in missing)}'
    )


# ---------------------------------------------------------------------------
# 2. No orphan Methods: every convenience call targets a declared spec
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('scanner_name', sorted(SPECS_BY_SCANNER_NAME))
async def test_convenience_methods_target_declared_specs(scanner_name: str) -> None:
    """Every convenience-method call must target a Method some scanner declares."""
    client = _RecordingClient(scanner_name)
    for name, (args, kwargs) in sorted(INVOCATIONS.items()):
        client.calls.clear()
        await getattr(client, name)(*args, **kwargs)
        for method, _params in client.calls:
            declared_by = [label for label, specs in SPEC_FAMILIES.items() if method in specs]
            assert declared_by, (
                f'{name}() -> {method.name} is an orphan Method: no scanner declares a spec '
                f'for it (scanner_name={scanner_name!r})'
            )


# ---------------------------------------------------------------------------
# 3. Param honesty: passed params must be declared by the declaring specs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('scanner_name', sorted(SPECS_BY_SCANNER_NAME))
async def test_convenience_params_are_declared_by_specs(scanner_name: str) -> None:
    """Params passed to call() must be param_map keys or path placeholders.

    This is the regression net for the ``get_block`` bug: it passed
    ``blockno=`` where the BLOCK_BY_NUMBER spec maps ``block_number`` ->
    ``tag``, so Etherscan received an unmapped ``blockno`` query param.
    """
    client = _RecordingClient(scanner_name)
    for name, (args, kwargs) in sorted(INVOCATIONS.items()):
        client.calls.clear()
        await getattr(client, name)(*args, **kwargs)
        for method, params in client.calls:
            for family_label in SPECS_BY_SCANNER_NAME[scanner_name]:
                specs = SPEC_FAMILIES[family_label]
                if method not in specs:
                    continue  # only scanners that declare the method are checked
                spec = specs[method]
                undeclared = [p for p in params if not _param_is_declared(spec, p)]
                assert not undeclared, (
                    f'{name}() passes parameter(s) {undeclared} that the {method.name} spec '
                    f'for {family_label} does not declare. Declared param_map keys: '
                    f'{sorted(spec.param_map)}; path placeholders: {spec.path}'
                )


# ---------------------------------------------------------------------------
# 4. Coverage completeness: the sweep table must cover every mixin method
# ---------------------------------------------------------------------------


def test_invocation_table_covers_all_mixin_methods() -> None:
    """New convenience methods must join the sweep (add them to INVOCATIONS)."""
    for mixin in MIXINS:
        for name in _public_convenience_methods(mixin):
            assert name in INVOCATIONS, (
                f'{mixin.__name__}.{name} is not covered by the consistency sweep; '
                f'add it to INVOCATIONS in {__file__}'
            )


def test_invocation_table_has_no_stale_entries() -> None:
    """Every sweep entry must correspond to a real mixin method."""
    known = {name for mixin in MIXINS for name in _public_convenience_methods(mixin)}
    for name in INVOCATIONS:
        assert name in known, f'INVOCATIONS entry {name!r} matches no mixin convenience method'
