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
5. Streaming/paginated client methods drifting away from the ONE public param
   dialect: the params they hand to ``fetch_page`` must be declared by the
   serving scanner's spec ``param_map`` (barring the documented inert page
   controls), and a BOUNDED block range on a rangeless spec must raise
   ``BlockRangeNotSupportedError`` instead of being silently dropped.
6. The streaming surface drifting from its declaration: every client
   ``iter_*`` generator must have a row in ``core.streaming.STREAMING_SPECS``
   (and vice versa), and every pool forward must mirror the client's exact
   signature (the ``guarantee_complete`` drift class).

The sweep is data-driven: a recording client invokes every convenience method
on each mixin, captures the ``(Method, params)`` pairs it hands to ``call()``,
and validates them against each scanner spec family that declares the method.
The streaming entries derive from the declaration source
(``aiochainscan.core.streaming``) — only the per-method unbounded kwargs stay
in this file, guarded bidirectionally against the registry.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from aiochainscan.constants import MAX_BLOCK_NUMBER
from aiochainscan.core.client import ChainscanClient
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
from aiochainscan.core.pool import ChainscanPool
from aiochainscan.core.streaming import STREAMING_SPECS
from aiochainscan.core.url_builder import UrlBuilder
from aiochainscan.domain.method import Method
from aiochainscan.exceptions import BlockRangeNotSupportedError, MethodNotDeclaredError
from aiochainscan.scanners._etherscan_like import EtherscanLikeScanner
from aiochainscan.scanners.base import BLOCK_RANGE_PARAM_KEYS, spec_declares_block_range
from aiochainscan.scanners.blockscout_v1 import BlockScoutV1
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
#
# The five get_all_* DICT aggregators are NOT hand-listed: they join from the
# streaming declaration (spec.aggregate) below, so adding a streaming method
# with its aggregator cannot forget this table. The *_normalized aggregators
# stay hand-listed (they are mixin surface without a registry row).
_HAND_INVOCATIONS: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {
    # Account
    'get_balance': ((CHECKSUM_ADDRESS,), {}),
    'get_transactions': ((CHECKSUM_ADDRESS,), {'start_block': 5, 'end_block': 10}),
    'get_transactions_normalized': ((CHECKSUM_ADDRESS,), {'start_block': 5, 'end_block': 10}),
    'get_token_transfers': ((CHECKSUM_ADDRESS,), {'contract_address': CONTRACT_ADDRESS}),
    'get_token_transfers_normalized': (
        (CHECKSUM_ADDRESS,),
        {'contract_address': CONTRACT_ADDRESS},
    ),
    'get_internal_transactions': ((CHECKSUM_ADDRESS,), {}),
    'get_internal_transactions_normalized': ((CHECKSUM_ADDRESS,), {}),
    'get_token_portfolio': ((CHECKSUM_ADDRESS,), {}),
    'get_erc721_transfers': ((CHECKSUM_ADDRESS,), {'contract_address': CONTRACT_ADDRESS}),
    'get_erc1155_transfers': ((CHECKSUM_ADDRESS,), {'contract_address': CONTRACT_ADDRESS}),
    'get_nft_portfolio': ((CHECKSUM_ADDRESS,), {}),
    'get_all_transactions_normalized': ((CHECKSUM_ADDRESS,), {}),
    'get_all_token_transfers_normalized': ((CHECKSUM_ADDRESS,), {}),
    'get_all_internal_transactions_normalized': ((CHECKSUM_ADDRESS,), {}),
    # Transactions
    'get_transaction': ((TX_HASH,), {}),
    'get_transaction_status': ((TX_HASH,), {}),
    'check_transaction_status': ((TX_HASH,), {}),
    'wait_for_transaction': ((TX_HASH,), {}),
    # Blocks
    'get_block': ((19_500_000,), {}),
    'get_block_normalized': ((19_500_000,), {}),
    'get_block_reward': ((19_500_000,), {}),
    'get_block_countdown': ((30_000_000,), {}),
    'get_block_by_timestamp': ((1_609_459_200,), {}),
    'wait_for_block': ((19_500_000,), {}),
    # Contracts
    'get_contract_abi': ((CONTRACT_ADDRESS,), {}),
    'get_contract_source': ((CONTRACT_ADDRESS,), {}),
    'get_contract_creation': (([CONTRACT_ADDRESS],), {}),
    'get_contract': ((CONTRACT_ADDRESS,), {}),
    'wait_for_verification': (('c31a4fbc-dad1-4c1e-a3cf-a66b62b5e00e',), {}),
    # Token
    'get_token_balance': ((CHECKSUM_ADDRESS, CONTRACT_ADDRESS), {}),
    'get_token_info': ((CONTRACT_ADDRESS,), {}),
    'get_token_supply': ((CONTRACT_ADDRESS,), {}),
    'get_token_holders': ((CONTRACT_ADDRESS,), {'page': 1, 'offset': 100}),
    'get_top_token_holders': ((CONTRACT_ADDRESS,), {'limit': 10}),
    'get_token_holder_count': ((CONTRACT_ADDRESS,), {}),
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
    'get_all_logs_normalized': ((CONTRACT_ADDRESS,), {}),
    'get_logs_normalized': (
        (CONTRACT_ADDRESS,),
        {'from_block': 100, 'to_block': 200, 'topic0': TRANSFER_TOPIC0},
    ),
    # Proxy
    'eth_call': ((CONTRACT_ADDRESS, '0x70a08231'), {}),
    'eth_get_balance': ((CHECKSUM_ADDRESS,), {}),
}

# Positional invocation args per registry-declared aggregator (the unbounded
# sweep call). Guarded bidirectionally against the registry below.
_AGGREGATE_ARGS: dict[str, tuple[Any, ...]] = {
    'get_all_transactions': (CHECKSUM_ADDRESS,),
    'get_all_token_transfers': (CHECKSUM_ADDRESS,),
    'get_all_internal_transactions': (CHECKSUM_ADDRESS,),
    'get_all_logs': (CONTRACT_ADDRESS,),
    'get_all_token_holders': (CONTRACT_ADDRESS,),
}

INVOCATIONS: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {
    **_HAND_INVOCATIONS,
    **{
        aggregate: (_AGGREGATE_ARGS[aggregate], {})
        for aggregate in (spec.aggregate for spec in STREAMING_SPECS)
        if aggregate is not None
    },
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

    def supports_method(self, method: Method) -> bool:
        """Mirror the scanner family declared for this scanner name."""
        return any(
            method in SPEC_FAMILIES[label] for label in SPECS_BY_SCANNER_NAME[self.scanner_name]
        )

    async def call(self, method: Method, **params: Any) -> Any:
        self.calls.append((method, params))
        if method == Method.CONTRACT_ABI:
            return '[]'  # JSON-encoded ABI (SmartContract.from_address contract)
        if method == Method.CONTRACT_SOURCE:
            return {}  # non-proxy source payload
        # Terminal payloads for the wait_for_* helpers so each sweep
        # invocation finishes on its first poll (no sleeps in the sweep).
        if method == Method.TX_STATUS_CHECK:
            return {'isError': '0', 'errDescription': ''}
        if method == Method.CONTRACT_VERIFY_STATUS:
            return 'Pass - Verified'
        if method == Method.BLOCK_COUNTDOWN:
            return {
                'CurrentBlock': '19500000',
                'CountdownBlock': '19500000',
                'RemainingBlock': '0',
                'EstimateTimeInSec': '0',
            }
        if method == Method.BLOCK_BY_NUMBER:
            return {'height': 19_500_000}
        return []  # satisfies list/dict/str post-processing in the mixins

    async def _empty_stream(
        self, *_args: Any, **_kwargs: Any
    ) -> AsyncIterator[list[dict[str, Any]]]:
        yield []

    iter_transactions_streaming = _empty_stream
    iter_token_transfers_streaming = _empty_stream
    iter_internal_transactions_streaming = _empty_stream
    iter_logs_streaming = _empty_stream
    iter_token_holders_streaming = _empty_stream
    # get_all_*_normalized mixin methods call these (defined on ChainscanClient
    # itself, next to the streaming versions above) — stub them the same way.
    iter_transactions_normalized = _empty_stream
    iter_token_transfers_normalized = _empty_stream
    iter_internal_transactions_normalized = _empty_stream
    iter_logs_normalized = _empty_stream


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
                if scanner_name == 'blockscout' and family_label == 'blockscout v2':
                    # BlockScout V2's scanner applies EndpointSpec filtering to
                    # the public params before building its REST query. The
                    # recording client stops at the convenience seam, so only
                    # validate params that survive that filtering here.
                    params = {
                        name: value
                        for name, value in params.items()
                        if _param_is_declared(spec, name)
                    }
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


# ---------------------------------------------------------------------------
# 4b. Declaration coverage: the streaming registry IS the streaming surface
# ---------------------------------------------------------------------------


def test_streaming_registry_declares_every_client_stream() -> None:
    """A client streaming method without a registry row fails here.

    The ``iter_*_normalized`` twins are exempt: they are typed compositions
    over declared streams (they never touch ``fetch_page`` themselves).
    """
    declared = {spec.name for spec in STREAMING_SPECS}
    on_client = {
        name
        for name, member in vars(ChainscanClient).items()
        if inspect.isasyncgenfunction(member) and not name.endswith('_normalized')
    }
    undeclared = on_client - declared
    stale = declared - on_client
    assert not undeclared, (
        f'ChainscanClient streaming method(s) {sorted(undeclared)} have no row in '
        f'aiochainscan.core.streaming.STREAMING_SPECS — declare them there so the '
        f'pool forward and this sweep derive from one source.'
    )
    assert not stale, f'STREAMING_SPECS row(s) {sorted(stale)} match no client method.'


def test_stream_sweep_kwargs_cover_exactly_the_registry() -> None:
    """The kwargs table must track the registry exactly (both directions)."""
    declared = {spec.name for spec in STREAMING_SPECS}
    assert set(_STREAM_SWEEP_KWARGS) == declared, (
        f'_STREAM_SWEEP_KWARGS drifted from STREAMING_SPECS: missing '
        f'{sorted(declared - set(_STREAM_SWEEP_KWARGS))}, stale '
        f'{sorted(set(_STREAM_SWEEP_KWARGS) - declared)}'
    )


def test_aggregate_args_cover_exactly_the_registry_aggregates() -> None:
    """Every declared get_all_* aggregator must have sweep args (and vice versa)."""
    declared = {spec.aggregate for spec in STREAMING_SPECS if spec.aggregate is not None}
    assert set(_AGGREGATE_ARGS) == declared, (
        f'_AGGREGATE_ARGS drifted from the registry aggregates: missing '
        f'{sorted(declared - set(_AGGREGATE_ARGS))}, stale '
        f'{sorted(set(_AGGREGATE_ARGS) - declared)}'
    )


def _normalize_annotation(annotation: str) -> str:
    """Render an annotation string identically for both declaration styles.

    ``client.py`` has real objects (``"<class 'str'>"``) while ``pool.py``
    uses ``from __future__ import annotations`` (``"str"``); strip the
    rendering difference so only the TYPES are compared.
    """
    if annotation.startswith("<class '") and annotation.endswith("'>"):
        annotation = annotation[len("<class '") : -len("'>")]
    return annotation.replace('typing.', '')


def _signature_params(func: Any) -> list[tuple[str, str, str]]:
    """(name, annotation, default) per non-self parameter of a method."""
    return [
        (name, _normalize_annotation(str(param.annotation)), repr(param.default))
        for name, param in inspect.signature(func).parameters.items()
        if name != 'self'
    ]


def test_pool_stream_forwards_mirror_client_signatures() -> None:
    """The pool surface cannot drift: every declared stream forwards the
    client's exact signature — the historical drift being pool
    ``iter_transactions``/``iter_logs`` silently lacking ``guarantee_complete``.
    """
    for spec in STREAMING_SPECS:
        assert callable(
            getattr(ChainscanClient, spec.name, None)
        ), f'{spec.name}: declared in STREAMING_SPECS but missing on ChainscanClient'
        pool_forward = getattr(ChainscanPool, spec.name, None)
        assert callable(pool_forward), (
            f'{spec.name}: declared in STREAMING_SPECS but ChainscanPool does not '
            f'expose a same-named forward'
        )
        client_params = _signature_params(getattr(ChainscanClient, spec.name))
        pool_params = _signature_params(pool_forward)
        assert client_params == pool_params, (
            f"{spec.name}: pool forward signature drifted from the client's\n"
            f'  client: {client_params}\n'
            f'  pool:   {pool_params}'
        )
        assert 'guarantee_complete' in {
            name for name, _annotation, _default in pool_params
        }, f'{spec.name}: pool forward must accept (and forward) guarantee_complete'


# ---------------------------------------------------------------------------
# 5. Streaming dialect: one public param dialect through fetch_page
# ---------------------------------------------------------------------------

#: Page-walking controls the streaming methods always emit. Page/offset
#: scanners declare them; cursor scanners (BlockScout V2, NodeReal transfers)
#: ignore them — an inert drop, unlike a silently dropped block RANGE.
_PAGE_CONTROL_KEYS: frozenset[str] = frozenset({'page', 'offset', 'sort'})

#: The unbounded sentinels the client emits for "no block bound".
_UNBOUNDED_ENDS: frozenset[Any] = frozenset({MAX_BLOCK_NUMBER, 'latest'})

#: Unbounded-phase invocation kwargs per DECLARED streaming method (the
#: bounded phase adds ``from_block=100, to_block=200`` to the same call).
#: Names, Method targets and ranged flags come from the declaration source;
#: only these kwargs live here, guarded bidirectionally against the registry.
_STREAM_SWEEP_KWARGS: dict[str, dict[str, Any]] = {
    'iter_transactions': {'address': CHECKSUM_ADDRESS},
    'iter_transactions_streaming': {'address': CHECKSUM_ADDRESS},
    'iter_internal_transactions_streaming': {'address': CHECKSUM_ADDRESS},
    'iter_token_transfers_streaming': {
        'address': CHECKSUM_ADDRESS,
        'contract_address': CONTRACT_ADDRESS,
    },
    'iter_logs_streaming': {'address': CONTRACT_ADDRESS},
    'iter_logs': {'address': CONTRACT_ADDRESS},
    # Holder lists have no block range: only the unbounded phase applies.
    'iter_token_holders_streaming': {'contract_address': CONTRACT_ADDRESS},
}

#: Every streaming/paginated client method and the Method it paginates,
#: DERIVED from ``core.streaming.STREAMING_SPECS`` (name, Method, ranged).
STREAMING_INVOCATIONS: dict[str, tuple[Method, dict[str, Any], bool]] = {
    spec.name: (spec.method, _STREAM_SWEEP_KWARGS[spec.name], spec.ranged)
    for spec in STREAMING_SPECS
}

#: get_all_* mixin aggregators funnel through iter_*_streaming — one bounded
#: representative each proves the guard covers the funnel, not just streams.
#: DERIVED from the registry (every RANGED row that declares an aggregate;
#: holder lists have no range to bound). The kwargs mirror the stream's.
AGGREGATE_FUNNELS: dict[str, tuple[Method, dict[str, Any]]] = {
    spec.aggregate: (spec.method, _STREAM_SWEEP_KWARGS[spec.name])
    for spec in STREAMING_SPECS
    if spec.aggregate is not None and spec.ranged
}


class _RecordingPage:
    """Real scanner instance whose ``fetch_page`` records params, answers empty."""

    def __init__(self, scanner: Any) -> None:
        self._scanner = scanner
        self.records: list[tuple[Method, dict[str, Any]]] = []

        async def recording_fetch_page(
            method: Method, params: dict[str, Any]
        ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
            self.records.append((method, dict(params)))
            return [], None

        scanner.fetch_page = recording_fetch_page  # type: ignore[method-assign]

    @property
    def specs(self) -> dict[Method, Any]:
        return self._scanner.SPECS

    @property
    def label(self) -> str:
        return f'{self._scanner.name}/{self._scanner.version}'


def _streaming_stub(family_label: str) -> _RecordingPage:
    """A recording page stub over the real scanner class of one family."""
    url_builder = UrlBuilder('test_key', 'eth', 'main')
    scanners: dict[str, Any] = {
        'etherscan-like (etherscan base, blockscout v1)': BlockScoutV1(
            '', 'eth', url_builder, network_client=None
        ),
        'etherscan v2': EtherscanV2('test_key', 'main', url_builder, network_client=None),
        'blockscout v2': BlockScoutV2Scanner(
            '', 'ethereum', UrlBuilder('', 'eth', 'ethereum'), network_client=None
        ),
        'nodereal v1': NodeRealScanner('test_key', 'bsc', url_builder, network_client=None),
    }
    return _RecordingPage(scanners[family_label])


def _streaming_client(stub: _RecordingPage) -> ChainscanClient:
    """A ChainscanClient shell around a recording scanner stub."""
    client = ChainscanClient.__new__(ChainscanClient)
    client.scanner_name = stub._scanner.name
    client.scanner_version = stub._scanner.version
    client.api_kind = 'test'
    client.network = 'main'
    client.api_key = ''
    client._scanner = stub._scanner
    return client


def _is_unbounded_range(params: dict[str, Any]) -> bool:
    """True when every emitted range key carries an unbounded sentinel."""
    ranged = [key for key in params if key in BLOCK_RANGE_PARAM_KEYS]
    if not ranged:
        return True  # no range emitted at all
    start = {params[key] for key in ranged if key in ('start_block', 'from_block')}
    end = {params[key] for key in ranged if key in ('end_block', 'to_block')}
    return start <= {0} and bool(end) and end <= _UNBOUNDED_ENDS


def _undeclared_emitted_keys(spec: Any, params: dict[str, Any]) -> list[str]:
    """Emitted keys the spec neither declares nor may inertly ignore.

    Inert exemptions (documented scanner behavior, never a silent data bug):
    - ``page``/``offset``/``sort`` page controls — cursor scanners ignore
      them (see ``iter_token_holders_streaming`` in AGENTS.md).
    - Range keys — tolerated ONLY when the values are the unbounded
      sentinels; a bounded range on a rangeless spec must never reach the
      wire (the guard raises instead, which the bounded sweep phase proves).
    """
    undeclared = [
        key
        for key in params
        if not _param_is_declared(spec, key) and key not in _PAGE_CONTROL_KEYS
    ]
    if _is_unbounded_range(params):
        undeclared = [key for key in undeclared if key not in BLOCK_RANGE_PARAM_KEYS]
    return undeclared


@pytest.mark.parametrize('family_label', sorted(SPEC_FAMILIES))
async def test_streaming_methods_emit_declared_public_params(family_label: str) -> None:
    """fetch_page params must be declared by the serving spec (one dialect).

    The regression net for the BlockScout V2 silent-drop bug: the client used
    to hand-build Etherscan WIRE names, which a spec-filtering scanner drops
    without notice — including block bounds. Everything now flows in public
    names that ``param_map`` either translates or (documentedly, inertly)
    ignores.
    """
    stub = _streaming_stub(family_label)
    client = _streaming_client(stub)
    specs = stub.specs

    for name, (method, kwargs, _ranged) in sorted(STREAMING_INVOCATIONS.items()):
        if method not in specs:
            continue  # family does not declare the method (its own error covers it)
        stub.records.clear()
        agen = getattr(client, name)(**kwargs)
        async for _batch in agen:
            pass
        assert stub.records, f'{name}() never reached fetch_page on {stub.label}'
        served_method, params = stub.records[0]
        assert served_method is method
        undeclared = _undeclared_emitted_keys(specs[method], params)
        assert not undeclared, (
            f'{stub.label} {name}() emits parameter(s) {undeclared} that its {method.name} '
            f'spec does not declare and may not inertly ignore. Emitted: {sorted(params)}; '
            f'declared param_map keys: {sorted(specs[method].param_map)}; '
            f'path placeholders: {specs[method].path}'
        )


@pytest.mark.parametrize('family_label', sorted(SPEC_FAMILIES))
async def test_bounded_range_on_rangeless_spec_raises_honestly(family_label: str) -> None:
    """A bounded range a spec cannot carry must raise, not silently drop.

    Bounded means ``from_block > 0`` or a concrete ``to_block``. Families
    whose spec declares range params serve the call and carry the bounds in
    the public dialect; the others must raise
    ``BlockRangeNotSupportedError`` naming the provider.
    """
    stub = _streaming_stub(family_label)
    client = _streaming_client(stub)
    specs = stub.specs

    for name, (method, kwargs, ranged) in sorted(STREAMING_INVOCATIONS.items()):
        if method not in specs or not ranged:
            continue
        spec_supports_range = any(key in specs[method].param_map for key in BLOCK_RANGE_PARAM_KEYS)
        bounded_kwargs = {**kwargs, 'from_block': 100, 'to_block': 200}
        agen = getattr(client, name)(**bounded_kwargs)
        if spec_supports_range:
            async for _batch in agen:
                pass
            # The range actually reached fetch_page in the public dialect.
            served = stub.records[-1][1]
            assert served.get('from_block', served.get('start_block')) == 100
            continue
        with pytest.raises(BlockRangeNotSupportedError) as excinfo:
            async for _batch in agen:
                pass
        assert stub.label in str(
            excinfo.value
        ), f'{name}() bounded-range error must name the provider ({stub.label})'
        assert 'from_block=100' in str(excinfo.value)


@pytest.mark.parametrize('family_label', sorted(SPEC_FAMILIES))
async def test_get_all_aggregators_inherit_the_range_guard(family_label: str) -> None:
    """get_all_* funnels through iter_*_streaming, so the guard covers it too."""
    stub = _streaming_stub(family_label)
    client = _streaming_client(stub)
    specs = stub.specs

    for name, (method, kwargs) in sorted(AGGREGATE_FUNNELS.items()):
        if method not in specs:
            continue
        spec_supports_range = any(key in specs[method].param_map for key in BLOCK_RANGE_PARAM_KEYS)
        coro = getattr(client, name)(**kwargs, from_block=100, to_block=200)
        if spec_supports_range:
            await coro
            continue
        with pytest.raises(BlockRangeNotSupportedError):
            await coro


@pytest.mark.asyncio
async def test_unbounded_stream_on_rangeless_scanner_still_works() -> None:
    """End to end: BlockScout V2 serves an unbounded stream, wire untouched.

    The guard must only refuse BOUNDED ranges. An unbounded call goes
    through the real scanner over a fake Network: the uniform public params
    the client now emits are filtered by the spec exactly as before, and the
    endpoint sees just the path address.
    """

    class FakeNetwork:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def request(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            return {'items': [{'hash': '0x1'}], 'next_page_params': None}

    net = FakeNetwork()
    scanner = BlockScoutV2Scanner(
        api_key='',
        network='ethereum',
        url_builder=UrlBuilder('', 'eth', 'ethereum'),
        network_client=net,  # type: ignore[arg-type]
    )
    client = ChainscanClient.__new__(ChainscanClient)
    client.scanner_name = scanner.name
    client.scanner_version = scanner.version
    client.api_kind = 'test'
    client.network = 'ethereum'
    client.api_key = ''
    client._scanner = scanner

    batches = [batch async for batch in client.iter_transactions_streaming('0xabc')]

    assert batches == [[{'hash': '0x1'}]]
    assert len(net.calls) == 1
    # The spec filtered every inert page control/range key: the wire request
    # is path-only, byte-identical to the pre-dialect-unification behaviour.
    assert net.calls[0]['params'] is None
    assert net.calls[0]['url'].endswith('/api/v2/addresses/0xabc/transactions')


# ============================================================================
# Direct (single-page) convenience methods × REAL scanner specs: a bounded
# block range is either transmitted or refused — never silently dropped.
#
# The streaming sweeps above cover ``iter_*`` / ``get_all_*``; the mixins'
# single-page methods reach the scanner through ``ChainscanClient.call`` /
# ``fetch_page``, so this sweep drives the REAL adapters over a fake Network
# and derives its expectation from each spec's own ``param_map``
# (``spec_declares_block_range``), never from a hand-maintained table.
# ============================================================================


class _DirectNet:
    """Minimal Network stand-in: records requests, replays canned responses."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def get(self, **kwargs: Any) -> Any:
        return await self.request(method='GET', **kwargs)

    async def post(self, **kwargs: Any) -> Any:
        return await self.request(method='POST', **kwargs)


def _direct_client_shell(scanner: Any) -> ChainscanClient:
    """A ChainscanClient shell around a real scanner + fake Network."""
    client = ChainscanClient.__new__(ChainscanClient)
    client.scanner_name = scanner.name
    client.scanner_version = scanner.version
    client.api_kind = 'test'
    client.network = 'main'
    client.api_key = ''
    client._scanner = scanner
    return client


_ETHERSCAN_ENVELOPE: dict[str, Any] = {'status': '1', 'message': 'OK', 'result': []}

# family label -> (scanner factory over a _DirectNet, one bounded-call response
# script, wire-level "the bounds were transmitted" predicate)
_DIRECT_FAMILIES: dict[str, Any] = {
    'etherscan/v2': {
        'make': lambda net: EtherscanV2(
            api_key='test_key',
            network='main',
            url_builder=MagicMock(),
            network_client=net,  # type: ignore[arg-type]
        ),
        'responses': lambda: [_ETHERSCAN_ENVELOPE],
        'bounds_transmitted': lambda net: net.calls[0]['params'].get('startblock') == 100
        and net.calls[0]['params'].get('endblock') == 200,
    },
    'blockscout/v1': {
        'make': lambda net: BlockScoutV1(
            api_key='',
            network='eth',
            url_builder=MagicMock(),
            network_client=net,  # type: ignore[arg-type]
        ),
        'responses': lambda: [_ETHERSCAN_ENVELOPE],
        'bounds_transmitted': lambda net: net.calls[0]['params'].get('startblock') == 100
        and net.calls[0]['params'].get('endblock') == 200,
    },
    'blockscout/v2': {
        'make': lambda net: BlockScoutV2Scanner(
            api_key='',
            network='ethereum',
            url_builder=UrlBuilder('', 'eth', 'ethereum'),
            network_client=net,  # type: ignore[arg-type]
        ),
        'responses': lambda: [{'items': [], 'next_page_params': None}],
        'bounds_transmitted': lambda net: False,  # rangeless: must refuse, never serve
    },
    'nodereal/v1': {
        'make': lambda net: NodeRealScanner(
            api_key='test_key',
            network='bsc',
            url_builder=MagicMock(),
            network_client=net,  # type: ignore[arg-type]
        ),
        # eth_blockNumber tip probe, then nr_getTransactionByAddress.
        'responses': lambda: ['0x1000', {'pageKey': '', 'transfers': []}],
        # The JSON-RPC filter must carry BOTH bounds (hex of 100/200); a
        # predicate matching only fromBlock would pass with toBlock dropped.
        'bounds_transmitted': lambda net: any(
            filter_.get('fromBlock') == '0x64' and filter_.get('toBlock') == '0xc8'
            for call in net.calls
            for filter_ in call.get('json_data', {}).get('params', [])
            if isinstance(filter_, dict)
        ),
    },
}

_DIRECT_RANGED_METHODS: tuple[tuple[str, Method], ...] = (
    ('get_transactions', Method.ACCOUNT_TRANSACTIONS),
    ('get_internal_transactions', Method.ACCOUNT_INTERNAL_TXS),
    ('get_token_transfers', Method.ACCOUNT_ERC20_TRANSFERS),
)


@pytest.mark.parametrize('family_label', sorted(_DIRECT_FAMILIES))
@pytest.mark.parametrize(
    ['method_name', 'method'], [list(pair) for pair in _DIRECT_RANGED_METHODS]
)
async def test_direct_paginated_bounded_range_served_or_refused(
    family_label: str, method_name: str, method: Method
) -> None:
    """Bounded single-page call: transmitted, not-declared, or honest refusal.

    A spec that declares block-range params must serve the call with the
    bounds on the wire; a spec that declares the method but no range params
    must raise ``BlockRangeNotSupportedError`` naming the provider; a spec
    that does not declare the method keeps the scanner's own
    ``MethodNotDeclaredError``. The silent drop (params filtered to ``None``
    while the caller asked for a narrower range) is the regression this pins.
    """
    family = _DIRECT_FAMILIES[family_label]
    net = _DirectNet(family['responses']())
    scanner = family['make'](net)
    client = _direct_client_shell(scanner)

    spec = scanner.SPECS.get(method)
    call = getattr(client, method_name)(CHECKSUM_ADDRESS, start_block=100, end_block=200)

    if spec is None:
        with pytest.raises(MethodNotDeclaredError):
            await call
        assert not net.calls, 'an undeclared method must not reach the wire'
    elif spec_declares_block_range(spec):
        await call
        assert net.calls, 'a range-capable spec must serve the bounded call'
        assert family['bounds_transmitted'](net), (
            f'{family_label} {method_name}() served the call but the bounded '
            f'range never reached the wire: {net.calls[0]}'
        )
    else:
        with pytest.raises(BlockRangeNotSupportedError) as excinfo:
            await call
        assert family_label in str(excinfo.value) or scanner.name in str(
            excinfo.value
        ), 'the refusal must name the provider'
        assert not net.calls, 'a refused call must not reach the wire'


@pytest.mark.parametrize('family_label', sorted(_DIRECT_FAMILIES))
async def test_direct_paginated_unbounded_range_never_guarded(family_label: str) -> None:
    """Unbounded defaults keep flowing exactly as before the guard."""
    family = _DIRECT_FAMILIES[family_label]
    net = _DirectNet(family['responses']())
    scanner = family['make'](net)
    client = _direct_client_shell(scanner)

    if Method.ACCOUNT_TRANSACTIONS not in scanner.SPECS:  # pragma: no cover - all declare it
        pytest.skip('family does not declare ACCOUNT_TRANSACTIONS')
    await client.get_transactions(CHECKSUM_ADDRESS)
    assert net.calls, 'unbounded default call must reach the wire unguarded'
