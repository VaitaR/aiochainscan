"""The paginated surface, declared once.

Every streaming method (``iter_*``) used to carry its own hand-written body:
``validate_batch_size`` + end-block resolution + a params dict + the
``iter_pages`` cursor loop with an operation noun, ``on_progress`` and
``guarantee_complete`` — five copies of the same plumbing per family, plus a
hand-forwarded twin on :class:`~aiochainscan.core.pool.ChainscanPool` that
once silently dropped ``guarantee_complete``. This module is the single
declaration source that replaces all of it:

- **One row per streaming method** (:class:`StreamSpec` in
  :data:`STREAMING_SPECS`): the public name, the paginated
  :class:`~aiochainscan.domain.method.Method`, the params builder, the
  progress operation noun, and the behavioural flags (ranged, item-level,
  completeness-routed) plus the ``get_all_*`` aggregator the stream feeds.
- **One streaming implementation** (:func:`stream_batches` /
  :func:`stream_items` / :func:`stream_normalized_batches`): validate →
  block-range guard → build params → bind the page fetch → the ONE cursor
  loop from :mod:`aiochainscan.services.pagination`. Public methods on the
  client are thin declarations over these.
- **One derived pool forward** (``ChainscanPool._forward_stream``): the
  pinned-stream semantics — provider pinning, progress stamping,
  ``guarantee_complete`` forwarding, completeness routing — are read from the
  row, never re-coded per method, so the pool surface cannot drift.
- **One shared host protocol** (:class:`SupportsStreaming`): the streaming
  surface every domain mixin needs from its host client, replacing the
  per-mixin protocol re-declarations.
- **One aggregation helper** (:func:`collect_stream`): the single
  ``collect_all`` call site behind every ``get_all_*`` (warning noun
  parameter, threshold defined once in :mod:`aiochainscan.services.constants`).

Adding a streaming method means ONE declaration row plus its public
signature(s) — nothing else. The consistency sweep in
``tests/test_method_consistency.py`` derives its streaming entries from this
registry and fails when a client streaming method is added without a row.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol, TypeVar, cast

from ..constants import MAX_BLOCK_NUMBER
from ..domain.method import Method
from ..domain.models import Address
from ..domain.normalize import (
    normalize_internal_transaction,
    normalize_log,
    normalize_token_transfer,
    normalize_transaction,
)
from ..domain.normalized import InternalTransaction, Log, TokenTransfer, Transaction
from ..services.constants import AGGREGATION_WARNING_THRESHOLD
from ..services.pagination import (
    BoundPageFetch,
    ItemDecode,
    collect_all,
    iter_pages,
    validate_batch_size,
)
from .types import JSONDict

__all__ = [
    'STREAMING_SPECS',
    'STREAMING_SPECS_BY_NAME',
    'SupportsStreaming',
    'StreamSpec',
    'collect_stream',
    'stream_batches',
    'stream_items',
    'stream_normalized_batches',
]

T = TypeVar('T')

type ParamsBuilder = Callable[..., dict[str, Any]]
"""Public streaming kwargs in, ``fetch_page`` params out (public dialect)."""


# ---------------------------------------------------------------------------
# End-block resolution (the two dialects the providers accept)
# ---------------------------------------------------------------------------


def _resolve_end_block_int(to_block: int | str | None) -> int:
    """Address-family end block: unbounded becomes the numeric sentinel."""
    if to_block is None or to_block == 'latest':
        return MAX_BLOCK_NUMBER
    return int(to_block)


def _resolve_end_block_param(to_block: int | str | None) -> int | str:
    """Log-family end block: unbounded stays the wire word ``'latest'``."""
    if to_block is None or to_block == 'latest':
        return 'latest'
    return int(to_block)


# ---------------------------------------------------------------------------
# Params builders — one per request shape, speaking the PUBLIC param dialect
# ---------------------------------------------------------------------------
#
# Scanner ``EndpointSpec.param_map``\\ s translate these public names to wire
# names (or drop params the endpoint never took — only possible for an
# unbounded range, which the block-range guard refuses to narrow silently).
# Every builder accepts the full public kwargs of its method and tolerates
# the ones it does not need (``**_extra``), so the shared implementation can
# hand it the complete call.


def _address_range_params(
    address: str,
    from_block: int = 0,
    to_block: int | str | None = 'latest',
    batch_size: int = 1000,
    **_extra: Any,
) -> dict[str, Any]:
    """Address-scoped history in the ``start_block``/``end_block`` dialect."""
    return {
        'address': address,
        'start_block': from_block,
        'end_block': _resolve_end_block_int(to_block),
        'page': 1,
        'offset': batch_size,
        'sort': 'asc',
    }


def _transaction_item_params(
    address: str,
    abi: list[dict[str, Any]] | None = None,
    from_block: int = 0,
    to_block: int | str | None = 'latest',
    batch_size: int = 1000,
    guarantee_complete: bool = True,
    **_extra: Any,
) -> dict[str, Any]:
    """:meth:`ChainscanClient.iter_transactions` params.

    Keeps the historical rangeless shortcut: a plain cursor walk (no ABI
    decode, unbounded range, completeness not guaranteed) needs fewer params
    — though nothing to split if the provider's result window is hit.
    """
    if (
        abi is None
        and from_block == 0
        and (to_block is None or to_block == 'latest')
        and not guarantee_complete
    ):
        return {'address': address, 'page': 1, 'offset': batch_size}
    return _address_range_params(address, from_block, to_block, batch_size)


def _token_transfer_params(
    address: str,
    from_block: int = 0,
    to_block: int | str | None = 'latest',
    contract_address: str | None = None,
    batch_size: int = 1000,
    **_extra: Any,
) -> dict[str, Any]:
    """Address-scoped ERC-20 history, optionally narrowed to one token."""
    params = _address_range_params(address, from_block, to_block, batch_size)
    if contract_address is not None:
        params['contract_address'] = contract_address
    return params


def _logs_batch_params(
    address: str | None,
    from_block: int = 0,
    to_block: int | str | None = 'latest',
    topic0: str | None = None,
    topic1: str | None = None,
    topic2: str | None = None,
    topic3: str | None = None,
    batch_size: int = 1000,
    **_extra: Any,
) -> dict[str, Any]:
    """:meth:`ChainscanClient.iter_logs_streaming` params (``from_block`` dialect).

    ``to_block`` keeps the ``'latest'`` wire word when unbounded; the address
    and topics are optional filters.
    """
    params: dict[str, Any] = {
        'from_block': from_block,
        'to_block': _resolve_end_block_param(to_block),
        'page': 1,
        'offset': batch_size,
    }
    if address is not None:
        params['address'] = address
    for key, value in (
        ('topic0', topic0),
        ('topic1', topic1),
        ('topic2', topic2),
        ('topic3', topic3),
    ):
        if value is not None:
            params[key] = value
    return params


def _logs_item_params(
    address: str,
    from_block: int = 0,
    to_block: int | str | None = 'latest',
    batch_size: int = 1000,
    topics: list[str] | None = None,
    topic_operators: list[str] | None = None,
    **_extra: Any,
) -> dict[str, Any]:
    """:meth:`ChainscanClient.iter_logs` params: positional topic list +
    pairwise operators, expanded into the individual ``topicN`` /
    ``topicN_N+1_opr`` keys."""
    params: dict[str, Any] = {
        'address': address,
        'from_block': from_block,
        'to_block': _resolve_end_block_param(to_block),
        'page': 1,
        'offset': batch_size,
    }
    if topics:
        for index, topic in enumerate(topics[:4]):
            params[f'topic{index}'] = topic
    if topic_operators:
        for index, operator in enumerate(topic_operators[:3]):
            params[f'topic{index}_{index + 1}_opr'] = operator
    return params


def _holder_params(contract_address: str, batch_size: int = 1000, **_extra: Any) -> dict[str, Any]:
    """Token-holder list params — no block range, EIP-55 contract address."""
    return {
        'contract_address': str(Address(contract_address)),
        'page': 1,
        'offset': batch_size,
    }


# ---------------------------------------------------------------------------
# The declaration: one row per streaming method
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StreamSpec:
    """Declaration of one public streaming method.

    Attributes:
        name: Public method name — identical on ``ChainscanClient`` and
            ``ChainscanPool``.
        method: The paginated :class:`Method` every page fetch executes.
        operation: Operation noun forwarded to progress callbacks.
        build_params: Public kwargs → ``fetch_page`` params (public dialect).
        ranged: The method carries block bounds, so the block-range guard
            applies and the params include a range.
        item_level: The method yields single (optionally decoded) items via
            the flattened path instead of batches; such methods take no
            ``on_progress`` and the pool never stamps ``provider=`` into one.
        completeness_routed: The endpoint has no splittable dimension, so
            ``ChainscanPool`` routes a guaranteed call to a completeness-
            capable member before any request (token holders).
        aggregate: Name of the ``get_all_*`` mixin aggregator this stream
            feeds (declaration metadata driving the consistency sweep).
        normalizer: Per-item mapper onto a domain model, applied per batch by
            :func:`stream_normalized_batches` (the ``iter_*_normalized``
            twins). ``None`` on raw rows — they yield provider dicts.
    """

    name: str
    method: Method
    operation: str
    build_params: ParamsBuilder
    ranged: bool = True
    item_level: bool = False
    completeness_routed: bool = False
    aggregate: str | None = None
    normalizer: Callable[[JSONDict], Any] | None = None


#: The raw (provider-dict) rows. The ``iter_*_normalized`` twins in
#: :data:`STREAMING_SPECS` derive from their same-family siblings here.
_RAW_SPECS: tuple[StreamSpec, ...] = (
    StreamSpec(
        name='iter_transactions',
        method=Method.ACCOUNT_TRANSACTIONS,
        operation='transactions',
        build_params=_transaction_item_params,
        item_level=True,
    ),
    StreamSpec(
        name='iter_transactions_streaming',
        method=Method.ACCOUNT_TRANSACTIONS,
        operation='transactions',
        build_params=_address_range_params,
        aggregate='get_all_transactions',
    ),
    StreamSpec(
        name='iter_internal_transactions_streaming',
        method=Method.ACCOUNT_INTERNAL_TXS,
        operation='internal_transactions',
        build_params=_address_range_params,
        aggregate='get_all_internal_transactions',
    ),
    StreamSpec(
        name='iter_token_transfers_streaming',
        method=Method.ACCOUNT_ERC20_TRANSFERS,
        operation='token_transfers',
        build_params=_token_transfer_params,
        aggregate='get_all_token_transfers',
    ),
    StreamSpec(
        name='iter_logs_streaming',
        method=Method.EVENT_LOGS,
        operation='logs',
        build_params=_logs_batch_params,
        aggregate='get_all_logs',
    ),
    StreamSpec(
        name='iter_logs',
        method=Method.EVENT_LOGS,
        operation='logs',
        build_params=_logs_item_params,
        item_level=True,
    ),
    StreamSpec(
        name='iter_token_holders_streaming',
        method=Method.TOKEN_HOLDERS,
        operation='token_holders',
        build_params=_holder_params,
        ranged=False,
        completeness_routed=True,
        aggregate='get_all_token_holders',
    ),
)

_raw_by_name: dict[str, StreamSpec] = {spec.name: spec for spec in _RAW_SPECS}


def _normalized_twin(
    sibling: StreamSpec,
    *,
    name: str,
    aggregate: str,
    normalizer: Callable[[JSONDict], Any],
) -> StreamSpec:
    """Derive an ``iter_*_normalized`` row from its ``iter_*_streaming`` sibling.

    Everything — the ``Method``, the operation noun, the ``build_params``
    OBJECT (shared by reference, so a future builder edit reaches both rows),
    ``ranged`` and the default flags — comes from the sibling via
    :func:`dataclasses.replace`; only the twin's name, its ``get_all_*``
    aggregator and the per-item normalizer are new facts. Never re-type the
    sibling's literals here: that is the drift this derivation exists for.
    """
    return replace(sibling, name=name, aggregate=aggregate, normalizer=normalizer)


#: The paginated surface. Order is the declaration order of the methods.
STREAMING_SPECS: tuple[StreamSpec, ...] = (
    *_RAW_SPECS,
    _normalized_twin(
        _raw_by_name['iter_transactions_streaming'],
        name='iter_transactions_normalized',
        aggregate='get_all_transactions_normalized',
        normalizer=normalize_transaction,
    ),
    _normalized_twin(
        _raw_by_name['iter_internal_transactions_streaming'],
        name='iter_internal_transactions_normalized',
        aggregate='get_all_internal_transactions_normalized',
        normalizer=normalize_internal_transaction,
    ),
    _normalized_twin(
        _raw_by_name['iter_token_transfers_streaming'],
        name='iter_token_transfers_normalized',
        aggregate='get_all_token_transfers_normalized',
        normalizer=normalize_token_transfer,
    ),
    _normalized_twin(
        _raw_by_name['iter_logs_streaming'],
        name='iter_logs_normalized',
        aggregate='get_all_logs_normalized',
        normalizer=normalize_log,
    ),
)

STREAMING_SPECS_BY_NAME: dict[str, StreamSpec] = {spec.name: spec for spec in STREAMING_SPECS}


# ---------------------------------------------------------------------------
# The ONE streaming implementation
# ---------------------------------------------------------------------------


class _StreamHost(Protocol):
    """The two client seams the shared streaming implementation needs."""

    def _stream_fetch(self, method: Method) -> BoundPageFetch: ...

    def _guard_block_range(
        self,
        method: Method,
        from_block: int,
        to_block: int | str | None,
    ) -> None: ...


def _prepare_stream(
    host: _StreamHost, spec: StreamSpec, kwargs: dict[str, Any]
) -> tuple[BoundPageFetch, dict[str, Any]]:
    """Shared streaming preamble: validate, guard, build params, bind fetch.

    The plumbing every streaming method used to repeat: ``batch_size``
    validation, the block-range guard for ranged methods (a BOUNDED range a
    rangeless provider would silently drop raises
    ``BlockRangeNotSupportedError`` instead), the public-dialect params dict,
    and the single page-fetch binding carrying the provider's result window.
    """
    validate_batch_size(kwargs.get('batch_size', 1000))
    if spec.ranged:
        host._guard_block_range(
            spec.method, kwargs.get('from_block', 0), kwargs.get('to_block', 'latest')
        )
    return host._stream_fetch(spec.method), spec.build_params(**kwargs)


async def stream_batches(
    host: _StreamHost, spec: StreamSpec, **kwargs: Any
) -> AsyncIterator[list[JSONDict]]:
    """THE streaming body: validate → guard → build → the one cursor loop.

    Yields page batches through :func:`aiochainscan.services.pagination.iter_pages`
    (which engages the guaranteed-complete engine when the provider declares
    a result window), with the row's operation noun on progress callbacks.
    Public client methods are thin declarations over this; retries stay at
    page-fetch level inside the Network layer.
    """
    fetch, params = _prepare_stream(host, spec, kwargs)
    async for batch in iter_pages(
        fetch,
        params,
        on_progress=kwargs.get('on_progress'),
        operation=spec.operation,
        guarantee_complete=kwargs.get('guarantee_complete', True),
    ):
        yield batch


async def stream_items(
    host: _StreamHost,
    spec: StreamSpec,
    *,
    decode: ItemDecode | None = None,
    **kwargs: Any,
) -> AsyncIterator[JSONDict]:
    """Item-level twin of :func:`stream_batches`: flattened, lazily decoded.

    Composed over :func:`stream_batches` (item-level streams take no progress
    callback); ``decode`` is applied per item at yield time, so items already
    consumed survive a decode failure on a later item.
    """
    kwargs.pop('on_progress', None)  # item-level streams take no callback
    async for batch in stream_batches(host, spec, **kwargs):
        for item in batch:
            yield decode(item) if decode is not None else item


async def stream_normalized_batches(
    host: _StreamHost, spec: StreamSpec, **kwargs: Any
) -> AsyncIterator[list[Any]]:
    """THE normalized streaming body: :func:`stream_batches` + the row's mapper.

    Composed over :func:`stream_batches` — identical params, block-range
    guard and ``guarantee_complete`` semantics — mapping each raw batch
    through ``spec.normalizer`` as it arrives, never after the raw list is
    collected (memory stays bounded by ``batch_size``). The
    ``iter_*_normalized`` client methods are thin declarations over this;
    the pool forwards kwargs verbatim and never normalizes itself.

    Raises:
        ValueError: If ``spec`` is a raw row (``normalizer is None``) — a
            declaration error, not a runtime condition.
    """
    normalizer = spec.normalizer
    if normalizer is None:
        raise ValueError(
            f'{spec.name} declares no normalizer — stream_normalized_batches '
            f'is for iter_*_normalized rows'
        )
    async for batch in stream_batches(host, spec, **kwargs):
        yield [normalizer(item) for item in batch]


# ---------------------------------------------------------------------------
# The shared host protocol (mixin ``self`` surface)
# ---------------------------------------------------------------------------


class SupportsStreaming(Protocol):
    """The streaming surface every paginated mixin needs from its host.

    One declaration replacing the per-mixin protocol re-declarations in
    ``account.py`` / ``token.py`` / ``logs.py``: both
    :class:`~aiochainscan.core.client.ChainscanClient` and
    :class:`~aiochainscan.core.pool.ChainscanPool` satisfy it structurally.
    The async-generator members are typed ``-> Any`` (mixin call sites only
    iterate them); the ``*_normalized`` twins keep their typed returns.
    """

    def iter_transactions(
        self,
        address: str,
        abi: list[dict[str, Any]] | None = None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        guarantee_complete: bool = True,
    ) -> Any: ...

    def iter_logs(
        self,
        address: str,
        abi: list[dict[str, Any]] | None = None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        topics: list[str] | None = None,
        topic_operators: list[str] | None = None,
        guarantee_complete: bool = True,
    ) -> Any: ...

    def iter_transactions_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: Any = None,
        guarantee_complete: bool = True,
    ) -> Any: ...

    def iter_internal_transactions_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: Any = None,
        guarantee_complete: bool = True,
    ) -> Any: ...

    def iter_token_transfers_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        contract_address: str | None = None,
        batch_size: int = 1000,
        on_progress: Any = None,
        guarantee_complete: bool = True,
    ) -> Any: ...

    def iter_logs_streaming(
        self,
        address: str | None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        topic0: str | None = None,
        topic1: str | None = None,
        topic2: str | None = None,
        topic3: str | None = None,
        batch_size: int = 1000,
        on_progress: Any = None,
        guarantee_complete: bool = True,
    ) -> Any: ...

    def iter_token_holders_streaming(
        self,
        contract_address: str,
        batch_size: int = 1000,
        on_progress: Any = None,
        guarantee_complete: bool = True,
    ) -> Any: ...

    def iter_transactions_normalized(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: Any = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[Transaction]]: ...

    def iter_internal_transactions_normalized(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: Any = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[InternalTransaction]]: ...

    def iter_token_transfers_normalized(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        contract_address: str | None = None,
        batch_size: int = 1000,
        on_progress: Any = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[TokenTransfer]]: ...

    def iter_logs_normalized(
        self,
        address: str | None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        topic0: str | None = None,
        topic1: str | None = None,
        topic2: str | None = None,
        topic3: str | None = None,
        batch_size: int = 1000,
        on_progress: Any = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[Log]]: ...


# ---------------------------------------------------------------------------
# The one get_all_* aggregation helper
# ---------------------------------------------------------------------------


async def collect_stream(
    batches: AsyncIterator[list[T]],
    *,
    stream_name: str,
    noun: str,
    logger: logging.Logger,
) -> list[T]:
    """Materialize one ``iter_*`` stream, warning once at the memory threshold.

    The single ``collect_all`` call site behind every ``get_all_*`` (raw and
    normalized): extends with every batch and logs the historical
    large-aggregation warning exactly once when the accumulated length hits
    ``AGGREGATION_WARNING_THRESHOLD``. The message is built from the
    ``noun``/``stream_name`` parameters so each aggregator declares only
    those two words.

    Args:
        batches: Async iterator of batches (an ``iter_*_streaming`` or
            ``iter_*_normalized`` generator).
        stream_name: Public method name suggested as the constant-memory
            alternative (e.g. ``'iter_transactions_streaming'``).
        noun: Human-readable item noun for the warning (e.g.
            ``'token transfers'``).
        logger: Caller's module logger.

    Returns:
        All items from all batches, in order.
    """
    items = await collect_all(
        cast(AsyncIterator[list[JSONDict]], batches),
        threshold=AGGREGATION_WARNING_THRESHOLD,
        warning=f'Aggregating >100k {noun} in memory. '
        f'Consider using {stream_name}() to avoid OOM.',
        logger=logger,
    )
    return cast(list[T], items)
