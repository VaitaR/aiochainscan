"""Multi-provider failover pool with memory (P0.1).

:class:`ChainscanPool` composes several :class:`~aiochainscan.core.client.ChainscanClient`
instances — one per ``(provider, network)`` — into a single client that
routes every operation to the best available provider. It sits *above* the
scanner layer and never touches the ``ChainscanClient`` contract: each
member client keeps its own ``Network`` (transport, tenacity retry, rate
limiter), and the pool only decides *who* serves a call.

Design highlights (deliberately better than the blockparty reference):

- **Failure classification, not blanket catches.** Every provider error is
  classified by :func:`classify_failure` into a :class:`FailureKind`; only
  fallback-eligible kinds move to the next provider, fatal ones (bad
  arguments, "not found", data-contract violations) propagate immediately.
- **Retry boundary respected.** Transport-level retries stay inside each
  client's ``Network`` (tenacity). The pool reacts only to the exception
  that survived those retries — it never duplicates retry logic.
- **Memory.** The last successful provider is *sticky* (no yo-yo routing),
  and a provider that failed fallback-eligibly enters a cooldown sized by
  failure class. Cooldowns honour ``ChainscanRateLimitError.retry_after``:
  the cooldown is ``max(retry_after, class default)``. During cooldown the
  provider is skipped without a single HTTP attempt; after it expires the
  provider is eligible again as a half-open trial (one probe request — a
  failure re-enters cooldown, a success restores it to rotation).
- **Pagination binding.** A pagination call (``iter_*`` / ``iter_*_streaming``
  / ``get_all_*``) is pinned to ONE provider for its whole lifetime —
  switching mid-pagination would corrupt opaque cursors. Failover happens
  only on the first page (cursor state is still empty, so a restart on the
  next provider is consistent); after the first page an error propagates,
  but a fallback-eligible one still puts the provider into cooldown so
  subsequent calls route around it.

State (sticky route, cooldowns) lives in the pool object only — there is no
global or process-wide mutation. All pool state is plain attributes mutated
from the event loop; no locking is required under asyncio cooperative
scheduling.
"""

from __future__ import annotations

import inspect
import re
import time
import warnings
from collections.abc import AsyncIterator, Callable, Sequence
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar, cast

import httpx

from ..exceptions import (
    ChainscanClientApiError,
    ChainscanNetworkError,
    ChainscanProviderSwitchWarning,
    ChainscanRateLimitError,
    CompletenessUnavailableError,
    MethodNotDeclaredError,
    ProviderPoolExhaustedError,
)
from .client import ChainscanClient
from .method import Method
from .mixins import (
    AccountMixin,
    BlockMixin,
    ChainMixin,
    ContractMixin,
    ENSMixin,
    LogsMixin,
    ProxyMixin,
    StatsMixin,
    TokenMixin,
    TransactionMixin,
)
from .types import JSONDict

if TYPE_CHECKING:
    from ..ports.progress import ProgressCallback
    from ..services.ens_resolver import ENSResolver

T = TypeVar('T')

# A pool entry for ``ChainscanPool.from_config``: ``(scanner, network)`` or
# ``(scanner, network, api_key)`` when the provider needs an explicit key.
ProviderEntry = tuple[str, str] | tuple[str, str, str]


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------


class FailureKind(Enum):
    """What a provider failure means for pool routing."""

    RATE_LIMIT = 'rate_limit'
    """Provider is throttling us — cooldown honours ``retry_after``."""

    TRANSIENT = 'transient'
    """Network/5xx trouble that survived the client's transport retries."""

    AUTH = 'auth'
    """Missing or invalid API key — will not heal itself, long cooldown."""

    PLAN_RESTRICTED = 'plan_restricted'
    """The current API plan does not serve the chain/endpoint (e.g. Etherscan
    V2 free tier answering ``Free API Access is not supported for this chain``)."""

    METHOD_UNDECLARED = 'method_undeclared'
    """The provider never declared this method in its SPECS — capability
    routing, not a failure: no cooldown, no warning, just next provider."""

    FATAL = 'fatal'
    """Caller's problem (bad arguments, not-found, data contract) — switching
    providers cannot help; propagate immediately."""


# Etherscan-style API error texts (message+result) that mean "bad credential".
_AUTH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'invalid api[- ]key', re.IGNORECASE),
    re.compile(r'missing[ /]+api[- ]key', re.IGNORECASE),
    re.compile(r'api[- ]key.{0,24}(invalid|missing|required)', re.IGNORECASE),
    re.compile(r'no api[- ]key', re.IGNORECASE),
)

# Error texts meaning "the plan does not cover this chain/endpoint".
_PLAN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'free api', re.IGNORECASE),
    re.compile(r'upgrade (?:your )?api plan', re.IGNORECASE),
    re.compile(r'api pro endpoint', re.IGNORECASE),
    re.compile(r'not supported for this chain', re.IGNORECASE),
)


def classify_failure(exc: BaseException) -> FailureKind:
    """Classify an exception that escaped a provider client.

    The classifier sees only exceptions that survived the client's transport
    retries (tenacity gives up and re-raises). Order matters: the most
    specific exception families are checked first.

    Args:
        exc: Exception raised by a provider client.

    Returns:
        The :class:`FailureKind` steering pool routing (see the enum docs).
    """
    if isinstance(exc, ChainscanRateLimitError):
        return FailureKind.RATE_LIMIT
    if isinstance(exc, MethodNotDeclaredError):
        return FailureKind.METHOD_UNDECLARED
    if isinstance(exc, ChainscanNetworkError):
        # 5xx / connection resets that tenacity already retried.
        return FailureKind.TRANSIENT
    if isinstance(exc, httpx.TransportError):
        # Raw transport errors (timeouts, protocol errors) that exhausted
        # the retry policy inside the client's Network.
        return FailureKind.TRANSIENT
    if isinstance(exc, ChainscanClientApiError):
        text = f'{exc.message or ""} {exc.result or ""}'
        if any(pattern.search(text) for pattern in _AUTH_PATTERNS):
            return FailureKind.AUTH
        if any(pattern.search(text) for pattern in _PLAN_PATTERNS):
            return FailureKind.PLAN_RESTRICTED
        return FailureKind.FATAL
    # Everything else — argument errors (ValueError/TypeError), not-found
    # API answers, data-contract violations, proxy errors — is the caller's
    # problem: another provider would answer the same way.
    return FailureKind.FATAL


_FAILURE_DESCRIPTIONS: dict[FailureKind, str] = {
    FailureKind.RATE_LIMIT: 'rate limit',
    FailureKind.TRANSIENT: 'network error',
    FailureKind.AUTH: 'auth error (missing or invalid API key)',
    FailureKind.PLAN_RESTRICTED: 'plan restriction (chain/endpoint not on the current plan)',
    FailureKind.METHOD_UNDECLARED: 'method not declared',
    FailureKind.FATAL: 'fatal error',
}


def _failure_description(kind: FailureKind) -> str:
    return _FAILURE_DESCRIPTIONS[kind]


# ---------------------------------------------------------------------------
# Per-provider state
# ---------------------------------------------------------------------------


class _ProviderState:
    """Mutable routing state of one pool member (no global state anywhere)."""

    __slots__ = ('client', 'cooldown_until', 'label', 'last_error', 'last_failure')

    def __init__(self, label: str, client: ChainscanClient) -> None:
        self.label = label
        self.client = client
        self.cooldown_until = 0.0
        self.last_error: Exception | None = None
        self.last_failure: FailureKind | None = None

    def in_cooldown(self, now: float) -> bool:
        return now < self.cooldown_until

    def cooldown_remaining(self, now: float) -> float:
        return max(0.0, self.cooldown_until - now)

    def enter_cooldown(self, until: float, error: Exception, kind: FailureKind) -> None:
        self.cooldown_until = until
        self.last_error = error
        self.last_failure = kind

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f'_ProviderState({self.label!r}, cooldown_until={self.cooldown_until:.1f})'


def _record_attempt(attempts: list[tuple[str, Exception]], label: str, error: Exception) -> None:
    """Append ``(label, error)`` keeping at most one entry per provider."""
    if all(existing != label for existing, _ in attempts):
        attempts.append((label, error))


def _serves_completely(state: _ProviderState, method: Method) -> bool:
    """True if this member declares ``method`` with no result window.

    ``Scanner.result_window is None`` means the provider paginates by an
    exhaustible server cursor (BlockScout V2, NodeReal) — nothing can
    overflow it, so it can serve ``method`` completely regardless of dataset
    size. A capped provider (``result_window`` is an int) can still succeed
    for a dataset under its cap, but cannot GUARANTEE it, which is exactly
    what ``guarantee_complete=True`` promises.
    """
    return state.client.supports_method(method) and state.client._scanner.result_window is None


def _inject_provider_progress(label: str, callback: ProgressCallback) -> ProgressCallback:
    """Wrap a progress callback so it also receives ``provider=<label>``.

    Provider responses are never mutated — the "who answered" stamp is
    exposed via ``last_provider`` and this progress field only. Callbacks
    with a strict signature (no ``**kwargs`` and no ``provider`` parameter)
    are returned unchanged so injection can never break a user callback.
    """
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):  # pragma: no cover - exotic callables
        return callback
    accepts = any(
        name == 'provider' or param.kind is inspect.Parameter.VAR_KEYWORD
        for name, param in signature.parameters.items()
    )
    if not accepts:
        return callback

    async def wrapped(**kwargs: Any) -> None:
        # The protocol signature has no ``provider`` parameter; the wrapper
        # is only installed for callbacks that explicitly accept it.
        await cast(Any, callback)(**{**kwargs, 'provider': label})

    return cast('ProgressCallback', wrapped)


# ---------------------------------------------------------------------------
# The pool
# ---------------------------------------------------------------------------


class ChainscanPool(
    AccountMixin,
    ContractMixin,
    BlockMixin,
    TransactionMixin,
    LogsMixin,
    TokenMixin,
    StatsMixin,
    ProxyMixin,
    ENSMixin,
    ChainMixin,
):
    """Failover client over a prioritised list of :class:`ChainscanClient` s.

    The pool exposes the full ``ChainscanClient`` surface (it is built from
    the very same domain mixins): single-shot convenience methods funnel
    into :meth:`call`, which routes with failover; pagination methods
    (``iter_*``, ``get_all_*``) pin to one provider per call. Member clients
    are constructed independently (each keeps its own Network transport,
    retry policy and rate limiter) — DI works exactly like everywhere else
    in the project.

    Routing policy:

    - **Priority order.** ``clients[0]`` is preferred; later entries are
      failover targets.
    - **Sticky.** The provider that answered last keeps serving while it is
      healthy — including after higher-priority providers leave cooldown
      (no yo-yo). It is reconsidered only when it fails.
    - **Cooldown / circuit breaker.** A fallback-eligible failure parks the
      provider for a class-specific window: rate limit →
      ``max(retry_after, rate_limit_cooldown)``; transient → 10s; auth →
      600s; plan restriction → 3600s. Cooling providers are skipped without
      any HTTP attempt. After expiry the provider is half-open: the next
      request is a trial (success → back in rotation, failure → cooldown
      again).
    - **Exhaustion.** When every provider failed (or is cooling),
      :class:`ProviderPoolExhaustedError` carries the ordered
      ``(provider, exception)`` attempts; cooling providers contribute the
      error that cooled them.

    Example:
        ```python
        from aiochainscan import ChainscanPool

        async with ChainscanPool.from_config(
            [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]
        ) as pool:
            balance = await pool.get_balance('0x...')   # etherscan while healthy
            # etherscan hits its daily cap → pool cools it (retry_after-aware),
            # warns, and blockscout answers:
            txs = await pool.get_transactions('0x...')
            pool.last_provider                        # 'blockscout/ethereum'
        ```
    """

    def __init__(
        self,
        clients: Sequence[ChainscanClient],
        *,
        rate_limit_cooldown: float = 30.0,
        transient_cooldown: float = 10.0,
        auth_cooldown: float = 600.0,
        plan_cooldown: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Assemble the pool from already-constructed clients.

        Args:
            clients: Clients in priority order (index 0 preferred). All must
                serve the same chain — the pool never verifies that, it is
                the caller's configuration decision.
            rate_limit_cooldown: Minimum cooldown for rate limits; the
                effective window is ``max(retry_after, this)`` seconds.
            transient_cooldown: Cooldown for network/5xx failures that
                already exhausted the transport retries (default 10s).
            auth_cooldown: Cooldown for missing/invalid API key answers
                (default 600s — credentials do not heal themselves).
            plan_cooldown: Cooldown for plan restrictions such as Etherscan
                V2 "Free API access is not supported for this chain"
                (default 3600s).
            clock: Monotonic clock used for cooldown bookkeeping
                (injectable for tests; defaults to ``time.monotonic``).

        Raises:
            ValueError: If ``clients`` is empty.
            TypeError: If a member is not a ``ChainscanClient``.
        """
        members = list(clients)
        if not members:
            raise ValueError('ChainscanPool requires at least one client')
        for client in members:
            if not isinstance(client, ChainscanClient):
                raise TypeError(
                    f'ChainscanPool members must be ChainscanClient instances, '
                    f'got {type(client).__name__}'
                )
        self._providers = [
            _ProviderState(label=f'{client.scanner_name}/{client.network}', client=client)
            for client in members
        ]
        self._clock = clock
        self._rate_limit_cooldown = float(rate_limit_cooldown)
        self._transient_cooldown = float(transient_cooldown)
        self._auth_cooldown = float(auth_cooldown)
        self._plan_cooldown = float(plan_cooldown)
        # Sticky = provider of the last success; route = label currently
        # served (initialised to the priority-1 provider so the very first
        # failover is reported as a switch).
        self._sticky: _ProviderState | None = None
        self._route = self._providers[0].label
        self._last_provider_label: str | None = None
        self._pool_ens_resolver: ENSResolver | None = None

    # -- construction -------------------------------------------------------

    @classmethod
    def from_config(
        cls, providers: Sequence[ProviderEntry], **client_kwargs: Any
    ) -> ChainscanPool:
        """Build a pool from ``(scanner, network)`` pairs in priority order.

        Each entry is resolved through :meth:`ChainscanClient.from_config`
        (registry + config-manager key resolution, custom base URLs and all
        other kwargs supported). A provider that cannot even be constructed
        (e.g. its API key is not configured) is *excluded with a warning*
        instead of poisoning the whole pool — the remaining providers must
        stay usable, that is the point of a pool. If no provider can be
        constructed at all, the first construction error is re-raised.

        Args:
            providers: ``(scanner, network)`` or ``(scanner, network, api_key)``
                entries in priority order.
            **client_kwargs: Forwarded to every ``ChainscanClient.from_config``
                call (``timeout``, ``proxy``, ``rate_limiter``,
                ``retry_policy``, ``expected_chain_id``, ``allow_http``, ...).

        Returns:
            Assembled pool (default cooldown windows; tune them via the
            constructor when needed).

        Example:
            ```python
            pool = ChainscanPool.from_config(
                [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]
            )
            ```
        """
        if not providers:
            raise ValueError('providers must contain at least one (scanner, network) entry')
        clients: list[ChainscanClient] = []
        errors: list[tuple[str, Exception]] = []
        for entry in providers:
            scanner, network = entry[0], entry[1]
            label = f'{scanner}/{network}'
            kwargs = dict(client_kwargs)
            if len(entry) > 2:
                kwargs['api_key'] = entry[2]
            try:
                clients.append(ChainscanClient.from_config(scanner, network, **kwargs))
            except Exception as exc:
                errors.append((label, exc))
                warnings.warn(
                    f'provider {label} is unavailable and was excluded from the pool: {exc}',
                    ChainscanProviderSwitchWarning,
                    stacklevel=2,
                )
        if not clients:
            raise errors[0][1]
        return cls(clients)

    # -- routing engine ------------------------------------------------------

    def _candidates(self) -> list[_ProviderState]:
        """Sticky provider first, then everyone else in priority order."""
        if self._sticky is not None:
            return [
                self._sticky,
                *(state for state in self._providers if state is not self._sticky),
            ]
        return list(self._providers)

    def _cooldown_for(self, kind: FailureKind, exc: Exception) -> float:
        if kind is FailureKind.RATE_LIMIT:
            retry_after = getattr(exc, 'retry_after', 0)
            try:
                advertised = float(retry_after)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                advertised = 0.0
            return max(advertised, self._rate_limit_cooldown)
        if kind is FailureKind.TRANSIENT:
            return self._transient_cooldown
        if kind is FailureKind.AUTH:
            return self._auth_cooldown
        if kind is FailureKind.PLAN_RESTRICTED:
            return self._plan_cooldown
        return 0.0  # METHOD_UNDECLARED / FATAL never cool a provider

    def _maybe_warn_switch(self, to_label: str, pending: tuple[str, float] | None) -> None:
        """Warn exactly once per route transition (failure-driven switches only).

        Capability routing (method not declared) never warns: it is
        deterministic, not exceptional.
        """
        if to_label == self._route:
            return
        from_label = self._route
        now = self._clock()
        if pending is not None:
            reason = f'{pending[0]} (cooldown {pending[1]:.0f}s)'
        else:
            route_state = next(
                (state for state in self._providers if state.label == from_label), None
            )
            if route_state is not None and route_state.in_cooldown(now):
                description = _failure_description(
                    route_state.last_failure or FailureKind.TRANSIENT
                )
                remaining = route_state.cooldown_remaining(now)
                reason = f'{description} (cooldown {remaining:.0f}s remaining)'
            else:
                reason = 'provider selection changed'
        self._route = to_label
        warnings.warn(
            f'switched from {from_label} to {to_label}: {reason}',
            ChainscanProviderSwitchWarning,
            stacklevel=3,
        )

    def _mark_success(self, state: _ProviderState) -> None:
        self._sticky = state
        self._route = state.label
        self._last_provider_label = state.label

    async def _execute(
        self,
        operation: str,
        invoke: Callable[[ChainscanClient], Any],
        method: Method | None = None,
    ) -> Any:
        """Run ``invoke`` with failover across providers (single request)."""
        attempts: list[tuple[str, Exception]] = []
        pending: tuple[str, float] | None = None
        for state in self._candidates():
            if method is not None and not state.client.supports_method(method):
                continue  # capability routing — silent
            now = self._clock()
            if state.in_cooldown(now):
                # Skip without any HTTP attempt; keep the error that cooled
                # the provider for the exhaustion report.
                if state.last_error is not None:
                    _record_attempt(attempts, state.label, state.last_error)
                continue
            self._maybe_warn_switch(state.label, pending)
            pending = None
            try:
                result = await invoke(state.client)
            except Exception as exc:
                kind = classify_failure(exc)
                if kind is FailureKind.FATAL:
                    raise
                _record_attempt(attempts, state.label, exc)
                if kind is FailureKind.METHOD_UNDECLARED:
                    continue  # no cooldown, no warning — capability gap
                cooldown = self._cooldown_for(kind, exc)
                state.enter_cooldown(self._clock() + cooldown, exc, kind)
                pending = (_failure_description(kind), cooldown)
                continue
            self._mark_success(state)
            return result
        if attempts:
            raise ProviderPoolExhaustedError(operation, attempts)
        raise ValueError(
            f'Method {method} not supported by any provider in the pool '
            f'({", ".join(state.label for state in self._providers)})'
        )

    def _pinned_stream(
        self,
        operation: str,
        factory: Callable[[_ProviderState], AsyncIterator[T]],
        *,
        candidates: list[_ProviderState] | None = None,
    ) -> AsyncIterator[T]:
        """Bind a pagination call to ONE provider with first-page failover.

        Policy: the provider is chosen when the generator starts. If the
        FIRST page fails fallback-eligibly, pagination restarts from scratch
        on the next provider (cursor state is still empty, so the restart is
        consistent). Once a page has been produced the stream is pinned:
        mid-pagination errors propagate to the caller (switching would
        corrupt opaque cursors), but fallback-eligible ones still put the
        provider into cooldown so later calls route around it.

        Each provider gets at most ONE first-page attempt per call
        (for-semantics, mirroring :meth:`_execute`): a provider that cannot
        serve the operation — including METHOD_UNDECLARED, which deliberately
        never enters cooldown — is excluded from THIS operation for good
        instead of being re-selected in a tight loop.

        Args:
            candidates: Pre-filtered/ordered provider list for THIS call,
                overriding :meth:`_candidates`. Used by completeness-aware
                routing (see :meth:`_guaranteed_pinned_stream`) to exclude,
                before any request, providers that cannot honour
                ``guarantee_complete`` — they never appear here, so they
                never receive a request and never enter ``attempts``.
        """

        async def _generate() -> AsyncIterator[T]:
            attempts: list[tuple[str, Exception]] = []
            pending: tuple[str, float] | None = None
            for state in candidates if candidates is not None else self._candidates():
                if state.in_cooldown(self._clock()):
                    # Skip without any HTTP attempt; keep the error that
                    # cooled the provider for the exhaustion report.
                    if state.last_error is not None:
                        _record_attempt(attempts, state.label, state.last_error)
                    continue
                self._maybe_warn_switch(state.label, pending)
                pending = None
                stream = factory(state)
                try:
                    first = await stream.__anext__()
                except StopAsyncIteration:
                    # A clean empty answer is a success — never a failover.
                    self._mark_success(state)
                    return
                except Exception as exc:
                    kind = classify_failure(exc)
                    if kind is FailureKind.FATAL:
                        raise
                    _record_attempt(attempts, state.label, exc)
                    if kind is FailureKind.METHOD_UNDECLARED:
                        continue
                    cooldown = self._cooldown_for(kind, exc)
                    state.enter_cooldown(self._clock() + cooldown, exc, kind)
                    pending = (_failure_description(kind), cooldown)
                    continue
                self._mark_success(state)
                yield first
                try:
                    async for item in stream:
                        yield item
                except Exception as exc:
                    # Pinned continuation: propagate, but remember the
                    # failure so the NEXT call does not repeat it.
                    kind = classify_failure(exc)
                    if kind not in (FailureKind.FATAL, FailureKind.METHOD_UNDECLARED):
                        state.enter_cooldown(
                            self._clock() + self._cooldown_for(kind, exc), exc, kind
                        )
                    raise
                return
            raise ProviderPoolExhaustedError(operation, attempts)

        return _generate()

    def _guaranteed_pinned_stream(
        self,
        operation: str,
        method: Method,
        factory: Callable[[_ProviderState], AsyncIterator[T]],
    ) -> AsyncIterator[T]:
        """Pin to a completeness-capable provider, deciding before any request.

        For an endpoint with no splittable dimension (token holders being the
        real case), a provider with a result window (``Scanner.result_window``
        is an int) cannot GUARANTEE completeness — Track C's
        ``CompletenessUnavailableError`` already detects the overflow, but
        only at the END of pagination, after the whole capped window was
        fetched and discarded. Reacting there means doubling the request
        budget on a rate-limited free API and, worse, would require
        restarting pagination on a different provider mid-stream — exactly
        what the pinning invariant forbids (cursors are provider-specific).

        So this decides BEFORE spending a single request: prefer a member
        that declares ``method`` with ``result_window is None`` (runs to
        exhaustion on an opaque cursor, nothing to overflow). Respects
        cooldowns — a completeness-capable member that is currently cooling
        is treated as unavailable, never as a fallback target, because
        falling back to a capped member would defeat the whole point.

        If NO pool member declares ``method`` at all, this defers entirely to
        :meth:`_pinned_stream` with the normal candidate order, so the
        existing METHOD_UNDECLARED capability routing (and its
        ``ProviderPoolExhaustedError`` on total exhaustion) is unaffected —
        that failure has nothing to do with completeness.
        """
        if not any(state.client.supports_method(method) for state in self._providers):
            return self._pinned_stream(operation, factory)

        now = self._clock()
        capable = [
            state
            for state in self._candidates()
            if not state.in_cooldown(now) and _serves_completely(state, method)
        ]
        if capable:
            return self._pinned_stream(operation, factory, candidates=capable)

        considered = tuple(state.label for state in self._providers)
        alternatives = tuple(
            state.label for state in self._providers if _serves_completely(state, method)
        )
        declaring = next(
            (
                state
                for state in self._candidates()
                if not state.in_cooldown(now) and state.client.supports_method(method)
            ),
            None,
        )
        window = declaring.client._scanner.result_window if declaring is not None else None
        provider_desc = (
            f'{declaring.label} (pool considered: {", ".join(considered)})'
            if declaring is not None
            else f'no available pool member declares it (considered: {", ".join(considered)})'
        )

        async def _raise() -> AsyncIterator[T]:
            raise CompletenessUnavailableError(
                method=method.name,
                provider=provider_desc,
                items_fetched=0,
                api_limit=window if isinstance(window, int) else 0,
                alternatives=alternatives,
                confirmed=False,
            )
            yield  # pragma: no cover - unreachable; keeps this an async generator

        return _raise()

    # -- public API: request routing ----------------------------------------

    async def call(self, method: Method, **params: Any) -> Any:
        """Execute a logical method with provider failover.

        Providers that do not declare ``method`` in their SPECS are routed
        around silently (fallback-eligible); if NO provider declares it, a
        ``ValueError`` is raised — mirroring the single-client contract.

        Raises:
            ValueError: If no provider in the pool declares ``method``.
            ProviderPoolExhaustedError: If every provider failed or is in
                cooldown; the ``attempts`` attribute carries the ordered
                ``(provider, exception)`` pairs.
        """
        return await self._execute(
            str(method),
            lambda client: client.call(method, **params),
            method=method,
        )

    async def fetch_page(
        self, method: Method, params: dict[str, Any]
    ) -> tuple[list[JSONDict], dict[str, Any] | None]:
        """Fetch one page with per-call failover (the MCP cursor seam).

        Each call is an independent request, so failover is safe per call —
        but opaque cursors are provider-specific: callers driving their own
        cursor loops should prefer the pool's ``iter_*`` methods, which pin
        a provider for the whole pagination.
        """
        result: tuple[list[JSONDict], dict[str, Any] | None] = await self._execute(
            f'fetch_page:{method}',
            lambda client: client.fetch_page(method, params),
            method=method,
        )
        return result

    def supports_method(self, method: Method) -> bool:
        """True if at least one pool provider declares ``method`` (union)."""
        return any(state.client.supports_method(method) for state in self._providers)

    def get_supported_methods(self) -> list[Method]:
        """Union of the methods declared by the pool providers, enum order."""
        return [method for method in Method if self.supports_method(method)]

    # -- public API: pagination (provider-pinned) ----------------------------

    def iter_transactions(
        self,
        address: str,
        abi: list[dict[str, Any]] | None = None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream transactions one by one, pinned to one provider per call."""

        def factory(state: _ProviderState) -> AsyncIterator[dict[str, Any]]:
            return state.client.iter_transactions(
                address=address,
                abi=abi,
                from_block=from_block,
                to_block=to_block,
                batch_size=batch_size,
            )

        return self._pinned_stream('iter_transactions', factory)

    def iter_logs(
        self,
        address: str,
        abi: list[dict[str, Any]] | None = None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        topics: list[str] | None = None,
        topic_operators: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream event logs one by one, pinned to one provider per call."""

        def factory(state: _ProviderState) -> AsyncIterator[dict[str, Any]]:
            return state.client.iter_logs(
                address=address,
                abi=abi,
                from_block=from_block,
                to_block=to_block,
                batch_size=batch_size,
                topics=topics,
                topic_operators=topic_operators,
            )

        return self._pinned_stream('iter_logs', factory)

    def iter_transactions_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Stream transaction batches, pinned to one provider per call.

        Failover happens only if the very first page fails; afterwards the
        stream is bound to its provider (see ``_pinned_stream``). Progress
        callbacks that accept it additionally receive ``provider=<label>``.
        """

        def factory(state: _ProviderState) -> AsyncIterator[list[dict[str, Any]]]:
            progress = (
                _inject_provider_progress(state.label, on_progress)
                if on_progress is not None
                else None
            )
            return state.client.iter_transactions_streaming(
                address=address,
                from_block=from_block,
                to_block=to_block,
                batch_size=batch_size,
                on_progress=progress,
                guarantee_complete=guarantee_complete,
            )

        return self._pinned_stream('iter_transactions_streaming', factory)

    def iter_internal_transactions_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Stream internal-transaction batches, pinned per call."""

        def factory(state: _ProviderState) -> AsyncIterator[list[dict[str, Any]]]:
            progress = (
                _inject_provider_progress(state.label, on_progress)
                if on_progress is not None
                else None
            )
            return state.client.iter_internal_transactions_streaming(
                address=address,
                from_block=from_block,
                to_block=to_block,
                batch_size=batch_size,
                on_progress=progress,
                guarantee_complete=guarantee_complete,
            )

        return self._pinned_stream('iter_internal_transactions_streaming', factory)

    def iter_token_transfers_streaming(
        self,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        contract_address: str | None = None,
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Stream ERC-20 transfer batches, pinned per call."""

        def factory(state: _ProviderState) -> AsyncIterator[list[dict[str, Any]]]:
            progress = (
                _inject_provider_progress(state.label, on_progress)
                if on_progress is not None
                else None
            )
            return state.client.iter_token_transfers_streaming(
                address=address,
                from_block=from_block,
                to_block=to_block,
                contract_address=contract_address,
                batch_size=batch_size,
                on_progress=progress,
                guarantee_complete=guarantee_complete,
            )

        return self._pinned_stream('iter_token_transfers_streaming', factory)

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
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Stream event-log batches, pinned per call."""

        def factory(state: _ProviderState) -> AsyncIterator[list[dict[str, Any]]]:
            progress = (
                _inject_provider_progress(state.label, on_progress)
                if on_progress is not None
                else None
            )
            return state.client.iter_logs_streaming(
                address=address,
                from_block=from_block,
                to_block=to_block,
                topic0=topic0,
                topic1=topic1,
                topic2=topic2,
                topic3=topic3,
                batch_size=batch_size,
                on_progress=progress,
                guarantee_complete=guarantee_complete,
            )

        return self._pinned_stream('iter_logs_streaming', factory)

    def iter_token_holders_streaming(
        self,
        contract_address: str,
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Stream token-holder batches, pinned per call.

        Token holders have no block range to split, so when
        ``guarantee_complete`` is ``True`` (default) the pool routes to a
        member that can serve the method completely (``Scanner.result_window
        is None``) BEFORE issuing any request, rather than starting on a
        capped provider and finding out only at the end of pagination — see
        :meth:`_guaranteed_pinned_stream`. ``guarantee_complete=False``
        restores the plain pinned-stream behaviour verbatim.
        """

        def factory(state: _ProviderState) -> AsyncIterator[list[dict[str, Any]]]:
            progress = (
                _inject_provider_progress(state.label, on_progress)
                if on_progress is not None
                else None
            )
            return state.client.iter_token_holders_streaming(
                contract_address=contract_address,
                batch_size=batch_size,
                on_progress=progress,
                guarantee_complete=guarantee_complete,
            )

        if guarantee_complete:
            return self._guaranteed_pinned_stream(
                'iter_token_holders_streaming', Method.TOKEN_HOLDERS, factory
            )
        return self._pinned_stream('iter_token_holders_streaming', factory)

    # -- public API: DataFrame helpers ---------------------------------------

    async def get_transactions_df(self, address: str) -> Any:
        """All transactions as a Polars DataFrame (pinned streaming, extra ``data``)."""
        from ..services.analytics import transactions_to_dataframe

        return await transactions_to_dataframe(self.iter_transactions(address))

    async def get_token_portfolio_df(self, address: str) -> Any:
        """Token portfolio as a Polars DataFrame (extra ``data``)."""
        from ..services.analytics import token_portfolio_to_dataframe
        from ..services.pagination import normalize_items

        tokens = await self.call(Method.ACCOUNT_TOKEN_PORTFOLIO, address=address)
        items = normalize_items(tokens)
        return await token_portfolio_to_dataframe(items)

    # -- transparency / observability ----------------------------------------

    @property
    def last_provider(self) -> str | None:
        """Label of the provider that answered the last successful call.

        Labels look like ``'etherscan/ethereum'``. ``None`` until the first
        success. Provider response payloads are deliberately never mutated;
        this attribute (plus the ``provider`` progress field) is the "who
        answered" stamp.
        """
        return self._last_provider_label

    @property
    def providers(self) -> tuple[str, ...]:
        """Provider labels in priority order."""
        return tuple(state.label for state in self._providers)

    def provider_states(self) -> dict[str, dict[str, Any]]:
        """Snapshot of the routing state per provider (observability).

        Returns a dict keyed by provider label; each value carries
        ``available`` (not cooling), ``cooldown_remaining`` seconds,
        ``sticky`` and the ``last_error`` that caused the cooldown.
        """
        now = self._clock()
        return {
            state.label: {
                'available': not state.in_cooldown(now),
                'cooldown_remaining': state.cooldown_remaining(now),
                'sticky': self._sticky is state,
                'last_error': state.last_error,
            }
            for state in self._providers
        }

    def reset_cooldowns(self) -> None:
        """Clear every cooldown (operational escape hatch, e.g. after fixing keys)."""
        for state in self._providers:
            state.cooldown_until = 0.0

    # -- delegation of the active provider's identity ------------------------

    @property
    def _active_client(self) -> ChainscanClient:
        """Client of the sticky provider (priority-1 before the first success)."""
        if self._sticky is not None:
            return self._sticky.client
        return self._providers[0].client

    @property
    def scanner_name(self) -> str:
        """Scanner name of the active provider (sticky, else priority-1)."""
        return self._active_client.scanner_name

    @scanner_name.setter
    def scanner_name(self, value: str) -> None:
        self._active_client.scanner_name = value

    @property
    def scanner_version(self) -> str:
        """Scanner version of the active provider."""
        return self._active_client.scanner_version

    @scanner_version.setter
    def scanner_version(self, value: str) -> None:
        self._active_client.scanner_version = value

    @property
    def chain_id(self) -> int | None:
        """Chain id of the active provider."""
        return self._active_client.chain_id

    @chain_id.setter
    def chain_id(self, value: int | None) -> None:
        self._active_client.chain_id = value

    @property
    def _expected_chain_id(self) -> int | None:
        """Expected-chain id of the active provider (chain validation wiring)."""
        return self._active_client._expected_chain_id

    @_expected_chain_id.setter
    def _expected_chain_id(self, value: int | None) -> None:
        self._active_client._expected_chain_id = value

    @property
    def currency(self) -> str:
        """Currency symbol of the active provider."""
        return self._active_client.currency

    @property
    def scanner_info(self) -> str:
        """Human-readable summary of the pool."""
        return f'ChainscanPool({", ".join(self.providers)})'

    @property
    def _scanner(self) -> Any:
        """Scanner of the active provider (mixin seam: ENS wiring, chain info)."""
        return self._active_client._scanner

    @_scanner.setter
    def _scanner(self, value: Any) -> None:
        self._active_client._scanner = value

    @property
    def _network(self) -> Any:
        """Network transport of the active provider (mixin seam: chain info)."""
        return self._active_client._network

    @_network.setter
    def _network(self, value: Any) -> None:
        self._active_client._network = value

    @property
    def _ens_resolver(self) -> ENSResolver | None:
        """Lazy ENS resolver storage (mixin seam — see :class:`ENSMixin`)."""
        return self._pool_ens_resolver

    @_ens_resolver.setter
    def _ens_resolver(self, value: ENSResolver | None) -> None:
        self._pool_ens_resolver = value

    # -- class-level introspection (delegate to the client) -------------------

    @classmethod
    def get_available_scanners(cls) -> dict[tuple[str, str], type[Any]]:
        """All registered scanner implementations (see ``ChainscanClient``)."""
        return ChainscanClient.get_available_scanners()

    @classmethod
    def list_scanner_capabilities(cls) -> dict[str, dict[str, Any]]:
        """Capabilities of all scanners (see ``ChainscanClient``)."""
        return ChainscanClient.list_scanner_capabilities()

    # -- lifecycle ------------------------------------------------------------

    async def close(self) -> None:
        """Close every member client (each closes its own Network)."""
        for state in self._providers:
            await state.client.close()

    async def __aenter__(self) -> ChainscanPool:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    def __str__(self) -> str:
        return f'ChainscanPool({", ".join(self.providers)})'

    def __repr__(self) -> str:
        return f'ChainscanPool(providers={list(self.providers)!r})'
