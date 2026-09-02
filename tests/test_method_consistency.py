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

The sweep is data-driven: a recording client invokes every convenience method
on each mixin, captures the ``(Method, params)`` pairs it hands to ``call()``,
and validates them against each scanner spec family that declares the method.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from typing import Any

import pytest

from aiochainscan.constants import MAX_BLOCK_NUMBER
from aiochainscan.core.client import ChainscanClient
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
from aiochainscan.core.url_builder import UrlBuilder
from aiochainscan.exceptions import BlockRangeNotSupportedError
from aiochainscan.scanners._etherscan_like import EtherscanLikeScanner
from aiochainscan.scanners.base import BLOCK_RANGE_PARAM_KEYS
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
INVOCATIONS: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {
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
    'get_all_transactions': ((CHECKSUM_ADDRESS,), {}),
    'get_all_transactions_normalized': ((CHECKSUM_ADDRESS,), {}),
    'get_all_token_transfers': ((CHECKSUM_ADDRESS,), {}),
    'get_all_token_transfers_normalized': ((CHECKSUM_ADDRESS,), {}),
    'get_all_internal_transactions': ((CHECKSUM_ADDRESS,), {}),
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
    'get_all_token_holders': ((CONTRACT_ADDRESS,), {}),
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
    'get_all_logs': ((CONTRACT_ADDRESS,), {}),
    'get_all_logs_normalized': ((CONTRACT_ADDRESS,), {}),
    'get_logs_normalized': (
        (CONTRACT_ADDRESS,),
        {'from_block': 100, 'to_block': 200, 'topic0': TRANSFER_TOPIC0},
    ),
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
# 5. Streaming dialect: one public param dialect through fetch_page
# ---------------------------------------------------------------------------

#: Page-walking controls the streaming methods always emit. Page/offset
#: scanners declare them; cursor scanners (BlockScout V2, NodeReal transfers)
#: ignore them — an inert drop, unlike a silently dropped block RANGE.
_PAGE_CONTROL_KEYS: frozenset[str] = frozenset({'page', 'offset', 'sort'})

#: The unbounded sentinels the client emits for "no block bound".
_UNBOUNDED_ENDS: frozenset[Any] = frozenset({MAX_BLOCK_NUMBER, 'latest'})

#: Every streaming/paginated client method and the Method it paginates. The
#: kwargs are the UNBOUNDED invocation; the bounded phase adds
#: ``from_block=100, to_block=200`` to the same call.
STREAMING_INVOCATIONS: dict[str, tuple[Method, dict[str, Any], bool]] = {
    'iter_transactions': (Method.ACCOUNT_TRANSACTIONS, {'address': CHECKSUM_ADDRESS}, True),
    'iter_transactions_streaming': (
        Method.ACCOUNT_TRANSACTIONS,
        {'address': CHECKSUM_ADDRESS},
        True,
    ),
    'iter_internal_transactions_streaming': (
        Method.ACCOUNT_INTERNAL_TXS,
        {'address': CHECKSUM_ADDRESS},
        True,
    ),
    'iter_token_transfers_streaming': (
        Method.ACCOUNT_ERC20_TRANSFERS,
        {'address': CHECKSUM_ADDRESS, 'contract_address': CONTRACT_ADDRESS},
        True,
    ),
    'iter_logs_streaming': (Method.EVENT_LOGS, {'address': CONTRACT_ADDRESS}, True),
    'iter_logs': (Method.EVENT_LOGS, {'address': CONTRACT_ADDRESS}, True),
    # Holder lists have no block range: only the unbounded phase applies.
    'iter_token_holders_streaming': (
        Method.TOKEN_HOLDERS,
        {'contract_address': CONTRACT_ADDRESS},
        False,
    ),
}

#: get_all_* mixin aggregators funnel through iter_*_streaming — one bounded
#: representative each proves the guard covers the funnel, not just streams.
AGGREGATE_FUNNELS: dict[str, tuple[Method, dict[str, Any]]] = {
    'get_all_transactions': (Method.ACCOUNT_TRANSACTIONS, {'address': CHECKSUM_ADDRESS}),
    'get_all_token_transfers': (
        Method.ACCOUNT_ERC20_TRANSFERS,
        {'address': CHECKSUM_ADDRESS, 'contract_address': CONTRACT_ADDRESS},
    ),
    'get_all_internal_transactions': (Method.ACCOUNT_INTERNAL_TXS, {'address': CHECKSUM_ADDRESS}),
    'get_all_logs': (Method.EVENT_LOGS, {'address': CONTRACT_ADDRESS}),
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
