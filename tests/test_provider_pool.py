"""Offline tests for the multi-provider failover pool (``ChainscanPool``).

The pool composes real :class:`~aiochainscan.core.client.ChainscanClient`
instances (constructed offline, real SPECS — no HTTP is ever issued) and the
tests drive the failover engine through the public seams: per-client ``call``
is replaced by ``AsyncMock`` and per-client streaming methods by stub async
generators. A fake monotonic ``clock`` makes cooldown/half-open transitions
deterministic without sleeping.

Covered semantics (mirrors the P0.1 backlog item):

- error classification: every FailureKind category, fatal passthrough;
- sticky routing (memory) — successful provider keeps serving;
- cooldown honouring ``ChainscanRateLimitError.retry_after`` (including
  ``retry_after`` above the default) and skipping cooling providers without
  a single HTTP attempt;
- half-open recovery after cooldown expiry (trial request, success returns
  the provider to rotation, failure re-enters cooldown);
- ``ProviderPoolExhaustedError`` with the ordered ``(provider, exception)``
  attempts, including the all-in-cooldown fast-fail with stored errors;
- missing-method routing (SPECS undeclared → next provider, not ValueError);
- pagination binding: provider pinned for a whole pagination call, failover
  only on the first page;
- transparency: ``last_provider``, ``provider`` field in progress callbacks,
  ``ProviderSwitchWarning`` on failure-driven switches.
"""

from __future__ import annotations

import asyncio
import inspect
import warnings
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from aiochainscan.chain_registry import ScannerTarget, resolve_scanner_target
from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.pool import (
    ChainscanPool,
    FailureKind,
    classify_failure,
)
from aiochainscan.core.streaming import STREAMING_SPECS
from aiochainscan.core.url_builder import UrlBuilder
from aiochainscan.domain.method import Method
from aiochainscan.domain.normalized import (
    InternalTransaction,
    Log,
    TokenTransfer,
    Transaction,
)
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanDataError,
    ChainscanNetworkError,
    ChainscanProviderSwitchWarning,
    ChainscanRateLimitError,
    CompletenessUnavailableError,
    MethodNotDeclaredError,
    ProviderPoolExhaustedError,
)
from aiochainscan.network import Network
from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner
from aiochainscan.scanners.etherscan_v2 import EtherscanV2

ADDR = '0x742d35Cc6634C0532925a3b8D9Fa7a3D91aC0b6f'
TOKEN = '0xDaC17f958D2ee523A2206208994597c13d831EC7'
HOLDER = '0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed'


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class FakeClock:
    """Deterministic monotonic clock for cooldown tests."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_etherscan_client() -> ChainscanClient:
    return ChainscanClient(resolve_scanner_target('etherscan', 'ethereum', api_key='test_key'))


def make_blockscout_client() -> ChainscanClient:
    return ChainscanClient(resolve_scanner_target('blockscout_v2', 'ethereum'))


def stub_client(client: ChainscanClient, result: Any = 'ok') -> AsyncMock:
    """Replace ``client.call`` with an AsyncMock returning ``result``."""
    mock = AsyncMock(return_value=result)
    client.call = mock  # type: ignore[assignment]
    return mock


def stream_stub(*pages: Any) -> Any:
    """Build an ``iter_*_streaming`` replacement yielding given pages.

    A page that is an exception instance is raised at that point of the
    stream, so tests can fail a provider before/after the first page.
    Mirrors ``services.pagination.iter_pages``: ``on_progress`` (when given)
    is invoked once per non-empty page with ``fetched``/``total_expected``/
    ``current_page``/``operation`` keyword arguments.
    """

    async def gen(
        *_args: Any, on_progress: Any = None, **_kwargs: Any
    ) -> AsyncIterator[list[dict[str, Any]]]:
        fetched = 0
        for page_number, page in enumerate(pages, start=1):
            if isinstance(page, BaseException):
                raise page
            fetched += len(page)
            if on_progress is not None and page:
                await on_progress(
                    fetched=fetched,
                    total_expected=None,
                    current_page=page_number,
                    operation='fetch',
                )
            yield page

    return gen


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def etherscan() -> ChainscanClient:
    return make_etherscan_client()


@pytest.fixture
def blockscout() -> ChainscanClient:
    return make_blockscout_client()


@pytest.fixture
def pool(
    etherscan: ChainscanClient, blockscout: ChainscanClient, clock: FakeClock
) -> ChainscanPool:
    """Two-provider pool: etherscan (priority 1) → blockscout (priority 2)."""
    return ChainscanPool(
        [etherscan, blockscout],
        rate_limit_cooldown=30.0,
        transient_cooldown=10.0,
        auth_cooldown=600.0,
        plan_cooldown=3600.0,
        clock=clock,
    )


def rate_limit(retry_after: int = 5) -> ChainscanRateLimitError:
    return ChainscanRateLimitError('NOTOK', 'Max rate limit reached', retry_after=retry_after)


# ---------------------------------------------------------------------------
# Failure classification — one test per category
# ---------------------------------------------------------------------------


class TestClassifyFailure:
    def test_rate_limit(self) -> None:
        assert classify_failure(ChainscanRateLimitError('NOTOK', 'Max rate limit reached')) is (
            FailureKind.RATE_LIMIT
        )

    def test_rate_limit_http_429(self) -> None:
        assert classify_failure(ChainscanRateLimitError('HTTP 429', 'Too Many Requests')) is (
            FailureKind.RATE_LIMIT
        )

    def test_transient_network_error(self) -> None:
        assert classify_failure(ChainscanNetworkError('HTTP 503 for api')) is FailureKind.TRANSIENT

    def test_transient_httpx_timeout(self) -> None:
        assert classify_failure(httpx.ReadTimeout('timed out')) is FailureKind.TRANSIENT

    def test_transient_httpx_network_error(self) -> None:
        assert classify_failure(httpx.ConnectError('connection refused')) is FailureKind.TRANSIENT

    def test_transient_httpx_protocol_error(self) -> None:
        assert classify_failure(httpx.RemoteProtocolError('GOAWAY')) is FailureKind.TRANSIENT

    def test_auth_invalid_api_key(self) -> None:
        exc = ChainscanClientApiError('NOTOK', 'Invalid API Key')
        assert classify_failure(exc) is FailureKind.AUTH

    def test_auth_missing_api_key(self) -> None:
        exc = ChainscanClientApiError('NOTOK', 'Missing/Invalid API Key')
        assert classify_failure(exc) is FailureKind.AUTH

    def test_plan_restricted_free_chain(self) -> None:
        exc = ChainscanClientApiError('NOTOK', 'Free API Access is not supported for this chain')
        assert classify_failure(exc) is FailureKind.PLAN_RESTRICTED

    def test_plan_restricted_pro_endpoint(self) -> None:
        exc = ChainscanClientApiError('NOTOK', 'you are trying to access an API Pro endpoint')
        assert classify_failure(exc) is FailureKind.PLAN_RESTRICTED

    def test_method_undeclared(self) -> None:
        assert classify_failure(MethodNotDeclaredError('Method X not supported by scan v1')) is (
            FailureKind.METHOD_UNDECLARED
        )

    def test_fatal_value_error(self) -> None:
        assert classify_failure(ValueError('bad argument')) is FailureKind.FATAL

    def test_carried_kind_wins_without_text_match(self) -> None:
        """A raise-site kind classifies even when the message matches NO
        Etherscan pattern — impossible before failures carried their kind."""
        exc = ChainscanClientApiError(
            'WeirdScanner quota exhausted', 'see provider docs', failure_kind=FailureKind.AUTH
        )
        assert classify_failure(exc) is FailureKind.AUTH

    def test_carried_kind_on_third_party_exception(self) -> None:
        """Any exception (not just ours) that carries a failure_kind
        classifies by lookup — the seam for scanner-specific failures."""

        class ThirdPartyAuthError(Exception):
            failure_kind = FailureKind.AUTH

        assert classify_failure(ThirdPartyAuthError('provider said no')) is FailureKind.AUTH

        class WeirdScannerError(ChainscanClientError):
            failure_kind = FailureKind.PLAN_RESTRICTED

        assert classify_failure(WeirdScannerError('plan too small')) is (
            FailureKind.PLAN_RESTRICTED
        )

    def test_carried_kind_can_widen_a_typed_default(self) -> None:
        """An explicit kind overrides what the type alone would say: a
        rate-limit-shaped exception raised as TRANSIENT routes transient."""
        exc = ChainscanRateLimitError(
            'NOTOK', 'Max rate limit reached', failure_kind=FailureKind.TRANSIENT
        )
        assert classify_failure(exc) is FailureKind.TRANSIENT

    def test_kindless_api_error_still_classified_from_text(self) -> None:
        """Fallback: an API error constructed WITHOUT a kind (third-party
        scanner) classifies from the Etherscan-style texts as before."""
        assert classify_failure(ChainscanClientApiError('NOTOK', 'Invalid API Key')) is (
            FailureKind.AUTH
        )
        assert (
            classify_failure(
                ChainscanClientApiError('NOTOK', 'Free API is not supported for this chain')
            )
            is FailureKind.PLAN_RESTRICTED
        )

    def test_fatal_not_found_api_error(self) -> None:
        exc = ChainscanClientApiError('NOTOK', 'No transactions found')
        assert classify_failure(exc) is FailureKind.FATAL

    def test_fatal_data_error(self) -> None:
        assert classify_failure(ChainscanDataError('missing field')) is FailureKind.FATAL

    def test_fatal_proxy_error(self) -> None:
        assert classify_failure(ChainscanClientProxyError(-32000, 'missing value')) is (
            FailureKind.FATAL
        )

    def test_fatal_client_error(self) -> None:
        assert classify_failure(ChainscanClientError('HTTP 404 for url')) is FailureKind.FATAL


# ---------------------------------------------------------------------------
# Routing: sticky + priority + missing-method
# ---------------------------------------------------------------------------


class TestRouting:
    async def test_first_call_goes_to_priority_one(self, pool: ChainscanPool) -> None:
        c1, c2 = stub_client(pool._providers[0].client), stub_client(pool._providers[1].client)
        result = await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        assert result == 'ok'
        assert c1.await_count == 1
        assert c2.await_count == 0

    async def test_sticky_provider_serves_subsequent_calls(self, pool: ChainscanPool) -> None:
        c1, c2 = stub_client(pool._providers[0].client), stub_client(pool._providers[1].client)
        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        assert c1.await_count == 3
        assert c2.await_count == 0

    async def test_last_provider_property(self, pool: ChainscanPool) -> None:
        stub_client(pool._providers[0].client)
        stub_client(pool._providers[1].client)
        assert pool.last_provider is None
        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        assert pool.last_provider == 'etherscan/ethereum'

    async def test_labels_in_priority_order(self, pool: ChainscanPool) -> None:
        assert pool.providers == ('etherscan/ethereum', 'blockscout/ethereum')

    async def test_missing_method_routes_to_declaring_provider(
        self, etherscan: ChainscanClient, blockscout: ChainscanClient, clock: FakeClock
    ) -> None:
        """blockscout_v2 does not declare GAS_ORACLE — etherscan must answer."""
        pool = ChainscanPool([blockscout, etherscan], clock=clock)
        c_bs, c_eth = stub_client(blockscout), stub_client(etherscan, {'SafeGasPrice': '7'})
        result = await pool.call(Method.GAS_ORACLE)
        assert result == {'SafeGasPrice': '7'}
        assert c_bs.await_count == 0  # capability routing: never invoked
        assert c_eth.await_count == 1
        assert pool.last_provider == 'etherscan/ethereum'

    async def test_missing_method_everywhere_raises_value_error(self, pool: ChainscanPool) -> None:
        # Neither etherscan v2 nor blockscout v2 is a valid single target for
        # every method; CONTRACT_VERIFY is declared by etherscan only. Build a
        # pool where nobody declares the method: blockscout_v2 twice.
        bs1, bs2 = make_blockscout_client(), make_blockscout_client()
        pool_bs = ChainscanPool([bs1, bs2], clock=FakeClock())
        stub_client(bs1)
        stub_client(bs2)
        with pytest.raises(ValueError, match='not supported'):
            await pool_bs.call(Method.GAS_ORACLE)

    async def test_supports_method_is_union(self, pool: ChainscanPool) -> None:
        assert pool.supports_method(Method.GAS_ORACLE)  # etherscan declares it
        assert pool.supports_method(Method.ACCOUNT_BALANCE)


# ---------------------------------------------------------------------------
# Failover + warnings + cooldown
# ---------------------------------------------------------------------------


class TestFailoverAndCooldown:
    async def test_rate_limit_switches_with_warning(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=5)
        stub_client(pool._providers[1].client, 'rescued')

        with pytest.warns(ChainscanProviderSwitchWarning, match='etherscan/ethereum'):
            result = await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        assert result == 'rescued'
        assert pool.last_provider == 'blockscout/ethereum'

    async def test_warning_message_format(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=30)
        stub_client(pool._providers[1].client)

        with pytest.warns(ChainscanProviderSwitchWarning) as records:
            await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        message = str(records[0].message)
        assert 'etherscan/ethereum' in message
        assert 'blockscout/ethereum' in message
        assert 'rate limit' in message
        assert 'cooldown 30' in message

    async def test_cooldown_uses_retry_after_when_larger_than_default(
        self, pool: ChainscanPool, clock: FakeClock
    ) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=120)
        stub_client(pool._providers[1].client)

        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        states = pool.provider_states()
        remaining = states['etherscan/ethereum']['cooldown_remaining']
        assert remaining > 100  # retry_after (120) wins over the 30s default

    async def test_cooldown_uses_default_when_retry_after_smaller(
        self, pool: ChainscanPool, clock: FakeClock
    ) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=5)
        stub_client(pool._providers[1].client)

        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        remaining = pool.provider_states()['etherscan/ethereum']['cooldown_remaining']
        assert 25 < remaining <= 30  # default (30) wins over retry_after (5)

    async def test_cooldown_skips_provider_without_attempt(
        self, pool: ChainscanPool, clock: FakeClock
    ) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=60)
        c2 = stub_client(pool._providers[1].client)

        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)  # p1 fails, p2 answers
        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)  # p1 cooling → p2 again

        assert c1.await_count == 1  # no retry against the cooling provider
        assert c2.await_count == 2

    async def test_transient_failure_cooldown(self, pool: ChainscanPool, clock: FakeClock) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = ChainscanNetworkError('HTTP 503 for api')
        stub_client(pool._providers[1].client)

        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        remaining = pool.provider_states()['etherscan/ethereum']['cooldown_remaining']
        assert 5 < remaining <= 10  # transient cooldown default

    async def test_auth_failure_long_cooldown(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = ChainscanClientApiError('NOTOK', 'Invalid API Key')
        stub_client(pool._providers[1].client)

        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        remaining = pool.provider_states()['etherscan/ethereum']['cooldown_remaining']
        assert remaining > 599  # auth cooldown (600s) — key will not heal itself

    async def test_http_401_from_the_wire_fails_over_with_auth_cooldown(
        self, pool: ChainscanPool
    ) -> None:
        """HTTP 401/403 → AUTH, proven wire-to-pool: the exception produced
        by the real Network raise site (NodeReal answers an invalid path key
        with HTTP 401 + JSON-RPC ``Unauthorized``) fails over and applies the
        auth cooldown — where the pre-change FATAL passthrough raised instead."""
        network = Network(UrlBuilder('test_key', 'eth', 'main'))
        try:
            response = httpx.Response(
                401,
                request=httpx.Request('GET', 'https://bsc-mainnet.nodereal.io/v1/secret'),
                text='{"error":{"code":-32000,"message":"Unauthorized"}}',
            )
            with pytest.raises(ChainscanClientError) as exc_info:
                network._handle_response(response)
        finally:
            await network.close()

        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = exc_info.value
        stub_client(pool._providers[1].client, 'rescued')

        result = await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        assert result == 'rescued'  # failed over instead of raising
        remaining = pool.provider_states()['etherscan/ethereum']['cooldown_remaining']
        assert remaining > 599  # auth cooldown — the refusing provider is skipped

    async def test_plan_restriction_cooldown(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = ChainscanClientApiError(
            'NOTOK', 'Free API Access is not supported for this chain'
        )
        stub_client(pool._providers[1].client)

        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        remaining = pool.provider_states()['etherscan/ethereum']['cooldown_remaining']
        assert remaining > 3599  # plan cooldown (3600s)

    async def test_missing_method_never_cools_provider(self, pool: ChainscanPool) -> None:
        """A provider without the method stays healthy for its other methods."""
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = MethodNotDeclaredError('Method GAS_ORACLE not supported')
        # blockscout_v2 does not declare GAS_ORACLE either; pretend it does
        # so the exception path (not the silent pre-check) routes to it.
        pool._providers[1].client.supports_method = Mock(return_value=True)  # type: ignore[assignment]
        stub_client(pool._providers[1].client, {'SafeGasPrice': '7'})

        result = await pool.call(Method.GAS_ORACLE)
        assert result == {'SafeGasPrice': '7'}
        states = pool.provider_states()
        assert states['etherscan/ethereum']['cooldown_remaining'] == 0
        assert states['etherscan/ethereum']['available'] is True

    async def test_half_open_trial_success_returns_provider_to_rotation(
        self, pool: ChainscanPool, clock: FakeClock
    ) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=5)  # → 30s cooldown
        c2 = stub_client(pool._providers[1].client)

        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)  # switch to p2
        clock.advance(31)  # p1 cooldown expired → eligible as trial (half-open)

        c2.side_effect = rate_limit(retry_after=5)  # sticky p2 fails → walk priority
        c1.side_effect = None  # p1 trial succeeds

        result = await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        assert result == 'ok'
        assert c1.await_count == 2  # trial request went to p1
        assert pool.last_provider == 'etherscan/ethereum'  # back in rotation

    async def test_half_open_trial_failure_re_enters_cooldown(
        self, pool: ChainscanPool, clock: FakeClock
    ) -> None:
        c1 = stub_client(pool._providers[0].client)
        c2 = stub_client(pool._providers[1].client)

        c1.side_effect = rate_limit(retry_after=5)
        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)  # p1 cools, p2 answers

        clock.advance(31)
        c2.side_effect = rate_limit(retry_after=5)  # p2 fails too
        c1.side_effect = rate_limit(retry_after=5)  # p1 trial fails → cooldown again

        with pytest.raises(ProviderPoolExhaustedError):
            await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        remaining = pool.provider_states()['etherscan/ethereum']['cooldown_remaining']
        assert remaining > 25  # trial failure re-entered cooldown

    async def test_sticky_survives_cooldown_expiry_of_higher_priority(
        self, pool: ChainscanPool, clock: FakeClock
    ) -> None:
        """Sticky keeps serving even after the higher-priority provider recovers."""
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=5)
        c2 = stub_client(pool._providers[1].client)

        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        clock.advance(60)  # p1 fully recovered — but p2 is sticky and healthy
        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        assert c2.await_count == 2
        assert c1.await_count == 1  # no yo-yo back while sticky is healthy

    async def test_reset_cooldowns(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=60)
        stub_client(pool._providers[1].client)
        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        pool.reset_cooldowns()
        states = pool.provider_states()
        assert all(s['cooldown_remaining'] == 0 for s in states.values())


# ---------------------------------------------------------------------------
# Pool exhaustion
# ---------------------------------------------------------------------------


class TestPoolExhausted:
    async def test_all_providers_failing_raises_with_attempts(self, pool: ChainscanPool) -> None:
        exc1, exc2 = rate_limit(retry_after=5), rate_limit(retry_after=7)
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = exc1
        c2 = stub_client(pool._providers[1].client)
        c2.side_effect = exc2

        with pytest.raises(ProviderPoolExhaustedError) as excinfo:
            await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        error = excinfo.value
        assert [label for label, _ in error.attempts] == [
            'etherscan/ethereum',
            'blockscout/ethereum',
        ]
        assert error.attempts[0][1] is exc1
        assert error.attempts[1][1] is exc2
        assert 'etherscan/ethereum' in str(error)
        assert 'blockscout/ethereum' in str(error)

    async def test_all_in_cooldown_fast_fails_without_attempts(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=60)
        c2 = stub_client(pool._providers[1].client)
        c2.side_effect = rate_limit(retry_after=60)

        with pytest.raises(ProviderPoolExhaustedError):
            await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        assert c1.await_count == 1
        assert c2.await_count == 1

        # Both cooling now: the next call must not touch any provider and must
        # carry the stored cooldown errors in its attempts.
        with pytest.raises(ProviderPoolExhaustedError) as excinfo:
            await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        assert c1.await_count == 1  # unchanged — no HTTP attempt
        assert c2.await_count == 1
        assert len(excinfo.value.attempts) == 2
        assert all(isinstance(exc, ChainscanRateLimitError) for _, exc in excinfo.value.attempts)


# ---------------------------------------------------------------------------
# Fatal errors — immediate propagation
# ---------------------------------------------------------------------------


class TestFatalPassthrough:
    async def test_value_error_propagates_immediately(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = ValueError('startblock must be an integer')
        c2 = stub_client(pool._providers[1].client)

        with pytest.raises(ValueError, match='startblock'):
            await pool.call(Method.ACCOUNT_TRANSACTIONS, address=ADDR)
        assert c2.await_count == 0  # fatal: no fallback attempt
        assert pool.provider_states()['etherscan/ethereum']['available'] is True

    async def test_not_found_api_error_is_fatal(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = ChainscanClientApiError('NOTOK', 'No transactions found')
        c2 = stub_client(pool._providers[1].client)

        with pytest.raises(ChainscanClientApiError):
            await pool.call(Method.ACCOUNT_TRANSACTIONS, address=ADDR)
        assert c2.await_count == 0

    async def test_data_error_is_fatal(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = ChainscanDataError('malformed payload')
        c2 = stub_client(pool._providers[1].client)

        with pytest.raises(ChainscanDataError):
            await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        assert c2.await_count == 0


# ---------------------------------------------------------------------------
# Convenience-method delegation through the mixins
# ---------------------------------------------------------------------------


class TestConvenienceDelegation:
    async def test_get_balance_fails_over(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=5)
        c2 = stub_client(pool._providers[1].client, '1000000000000000000')

        balance = await pool.get_balance(ADDR)

        assert balance == '1000000000000000000'
        assert c2.await_count == 1
        assert c2.await_args == c2.call_args
        called_method = c2.call_args.args[0]
        assert called_method is Method.ACCOUNT_BALANCE

    async def test_get_transaction_not_found_propagates(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = ChainscanClientApiError('NOTOK', 'invalid hash')
        stub_client(pool._providers[1].client)

        with pytest.raises(ChainscanClientApiError):
            await pool.get_transaction('0x' + 'ab' * 32)


# ---------------------------------------------------------------------------
# Pagination binding
# ---------------------------------------------------------------------------


class TestPaginationBinding:
    async def test_stream_is_pinned_to_one_provider(
        self, pool: ChainscanPool, etherscan: ChainscanClient, blockscout: ChainscanClient
    ) -> None:
        """Pages flow from one provider; a mid-pagination failure propagates."""
        etherscan.iter_transactions_streaming = stream_stub(  # type: ignore[assignment]
            [{'hash': '0x1'}],
            rate_limit(retry_after=5),  # fails AFTER the first page → propagate
        )
        blockscout.iter_transactions_streaming = stream_stub(  # type: ignore[assignment]
            [{'hash': '0xB1'}],
        )

        batches: list[list[dict[str, Any]]] = []
        with pytest.raises(ChainscanRateLimitError):
            async for batch in pool.iter_transactions_streaming(ADDR):
                batches.append(batch)

        assert batches == [[{'hash': '0x1'}]]  # first page survived
        # blockscout was never asked: switching mid-pagination is forbidden;
        # but etherscan still enters cooldown so the NEXT call routes around it
        states = pool.provider_states()
        assert states['etherscan/ethereum']['available'] is False
        assert states['etherscan/ethereum']['last_error'] is not None

    async def test_first_page_failure_fails_over_to_next_provider(
        self, pool: ChainscanPool, etherscan: ChainscanClient, blockscout: ChainscanClient
    ) -> None:
        etherscan.iter_transactions_streaming = stream_stub(  # type: ignore[assignment]
            rate_limit(retry_after=5),  # fails on the FIRST page → allowed to switch
        )
        blockscout.iter_transactions_streaming = stream_stub(  # type: ignore[assignment]
            [{'hash': '0xB1'}],
            [{'hash': '0xB2'}],
        )

        batches = [b async for b in pool.iter_transactions_streaming(ADDR)]

        assert batches == [[{'hash': '0xB1'}], [{'hash': '0xB2'}]]
        assert pool.last_provider == 'blockscout/ethereum'

    async def test_empty_stream_from_first_provider_is_final(
        self, pool: ChainscanPool, etherscan: ChainscanClient, blockscout: ChainscanClient
    ) -> None:
        """A clean empty answer is a success, not a failure — no failover."""
        etherscan.iter_transactions_streaming = stream_stub()  # type: ignore[assignment]
        blockscout.iter_transactions_streaming = stream_stub(  # type: ignore[assignment]
            [{'hash': '0xB1'}],
        )

        batches = [b async for b in pool.iter_transactions_streaming(ADDR)]

        assert batches == []
        assert pool.last_provider == 'etherscan/ethereum'

    async def test_get_all_aggregates_pinned_stream(self, pool: ChainscanPool) -> None:
        etherscan, blockscout = (p.client for p in pool._providers)
        etherscan.iter_transactions_streaming = stream_stub(  # type: ignore[assignment]
            [{'hash': '0x1'}],
            [{'hash': '0x2'}],
        )
        blockscout.iter_transactions_streaming = stream_stub(  # type: ignore[assignment]
            [{'hash': '0xB1'}],
        )

        txs = await pool.get_all_transactions(ADDR)

        assert txs == [{'hash': '0x1'}, {'hash': '0x2'}]

    async def test_fetch_page_fails_over_per_call(self, pool: ChainscanPool) -> None:
        p1, p2 = pool._providers
        p1.client.fetch_page = AsyncMock(side_effect=rate_limit(retry_after=5))  # type: ignore[assignment]
        p2.client.fetch_page = AsyncMock(return_value=([{'hash': '0xB1'}], None))  # type: ignore[assignment]

        items, cursor = await pool.fetch_page(Method.ACCOUNT_TRANSACTIONS, {'address': ADDR})

        assert items == [{'hash': '0xB1'}]
        assert cursor is None


# ---------------------------------------------------------------------------
# Regression: the get_all_*_normalized aggregators must work through the pool
# ---------------------------------------------------------------------------


#: One raw page carrying every key the four ``domain.normalize`` mappers read;
#: a single shape exercises transactions, internal transactions, token
#: transfers and logs alike (the mappers are alias-tolerant per family).
_NORMALIZED_RAW_PAGE: list[dict[str, Any]] = [
    {
        'hash': '0x' + 'ab' * 32,
        'transactionHash': '0x' + 'ab' * 32,
        'blockNumber': '1',
        'from': '0x0000000000000000000000000000000000000001',
        'to': '0x0000000000000000000000000000000000000002',
        'value': '5',
        'timeStamp': '1700000000',
        'topics': [],
        'data': '0x',
    }
]


class TestNormalizedAggregatorsOnPool:
    """The four ``get_all_*_normalized`` aggregators must work on the pool.

    Regression (deepening brief C1): the pool composes the same mixins as
    ``ChainscanClient``, so the aggregators existed — but the
    ``iter_*_normalized`` generators they call were defined on the client
    only and never forwarded, so every aggregator crashed with
    ``AttributeError: 'ChainscanPool' object has no attribute
    'iter_transactions_normalized'``. The single member is a real (offline)
    client over a replayed page, so the items it returns are genuinely
    normalized domain models, not stub passthrough.
    """

    @pytest.mark.parametrize(
        ['aggregator', 'model'],
        [
            ('get_all_transactions_normalized', Transaction),
            ('get_all_internal_transactions_normalized', InternalTransaction),
            ('get_all_token_transfers_normalized', TokenTransfer),
            ('get_all_logs_normalized', Log),
        ],
    )
    async def test_aggregator_returns_normalized_items(self, aggregator: str, model: Any) -> None:
        member = _bare_client(
            EtherscanV2(
                api_key='test_key',
                network='main',
                url_builder=MagicMock(),
                # One replayed payload = ONE PAGE (the items list, the shape
                # Network hands the scanner post-unwrap — see the
                # ``_ReplayNetwork`` replay of ``log_page`` below). Replaying
                # the items as separate payloads would hand pagination a bare
                # dict, which ``coerce_response_items`` reads as no data.
                network_client=_ReplayNetwork([[dict(item) for item in _NORMALIZED_RAW_PAGE]]),
            ),
            'main',
        )
        pool = ChainscanPool([member])

        items = await getattr(pool, aggregator)(ADDR)

        assert len(items) == 1
        assert isinstance(items[0], model)
        assert pool.last_provider == 'etherscan/main'


# ---------------------------------------------------------------------------
# Regression: METHOD_UNDECLARED must fail over, never livelock
# ---------------------------------------------------------------------------


class _ReplayNetwork:
    """Minimal Network stand-in replaying post-unwrap payloads."""

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


def _bare_client(scanner: Any, network: str) -> ChainscanClient:
    """ChainscanClient wired to a real scanner via the constructor seam (no full wiring).

    The scanner already carries its own ``_ReplayNetwork``; the client's own
    ``_network`` is an unused placeholder — no test here touches it.
    """
    target = ScannerTarget(
        scanner_name=scanner.name,
        scanner_version=scanner.version,
        network=network,
        api_kind='eth',
        api_key='',
        chain_id=None,
        url_network=network,
        scanner_network=network,
    )
    return ChainscanClient(target, scanner=scanner, network=_ReplayNetwork([]))


class TestPinnedStreamMethodUndeclared:
    """Drive the REAL streaming path over real scanners.

    ``_pinned_stream`` used to re-select the same METHOD_UNDECLARED provider
    in a tight ``while True`` loop (no cooldown, no capability filter): the
    declaring provider was never reached and the pool spun at 100% CPU.
    """

    @staticmethod
    def _v2_client(network: _ReplayNetwork) -> ChainscanClient:
        # BlockScout V2 is the one streaming-capable scanner that declares no
        # EVENT_LOGS spec: its address-scoped logs endpoint carries neither a
        # topic nor a block-range filter, so the method stays undeclared.
        return _bare_client(
            BlockScoutV2Scanner(
                api_key='', network='ethereum', url_builder=MagicMock(), network_client=network
            ),
            'ethereum',
        )

    @staticmethod
    def _etherscan_client(network: _ReplayNetwork) -> ChainscanClient:
        return _bare_client(
            EtherscanV2(
                api_key='test_key',
                network='main',
                url_builder=MagicMock(),
                network_client=network,
            ),
            'main',
        )

    async def test_stream_fails_over_to_declaring_provider(self) -> None:
        """``guarantee_complete=False`` isolates this from completeness routing.

        Both pool members are result-window-capped for event logs (V2 does not
        even declare the method), so under the default
        ``guarantee_complete=True`` this scenario hits the completeness
        pre-check (see ``TestCompletenessRouting``) and raises before any
        request — that is the intended behaviour. This test keeps exercising
        its original, unrelated regression: METHOD_UNDECLARED must fail over
        instead of spinning on the same provider.
        """
        log_page = [{'address': TOKEN, 'topics': [], 'data': '0x', 'blockNumber': '0x1'}]
        v2_network = _ReplayNetwork([])  # must never be asked
        etherscan_network = _ReplayNetwork([log_page])
        pool = ChainscanPool(
            [self._v2_client(v2_network), self._etherscan_client(etherscan_network)]
        )

        batches = [
            batch
            async for batch in pool.iter_logs_streaming(
                TOKEN, batch_size=2, guarantee_complete=False
            )
        ]

        assert batches == [log_page]
        assert pool.last_provider == 'etherscan/main'
        # The non-declaring provider raised before any HTTP attempt.
        assert v2_network.calls == []
        assert len(etherscan_network.calls) == 1

    async def test_no_provider_declares_terminates(self) -> None:
        """Nobody declares the method → finite exhaustion, not a hang."""
        pool = ChainscanPool([self._v2_client(_ReplayNetwork([]))])

        async def collect() -> list[list[dict[str, Any]]]:
            return [batch async for batch in pool.iter_logs_streaming(TOKEN)]

        with pytest.raises(ProviderPoolExhaustedError) as excinfo:
            await asyncio.wait_for(collect(), timeout=5.0)

        attempts = excinfo.value.attempts
        assert len(attempts) == 1
        assert isinstance(attempts[0][1], MethodNotDeclaredError)


# ---------------------------------------------------------------------------
# Completeness-aware routing: decide BEFORE any request, never react after
# ---------------------------------------------------------------------------


class TestCompletenessRouting:
    """``guarantee_complete=True`` on a rangeless-and-capped endpoint (token
    holders) must route to a completeness-capable member (``Scanner.
    result_window is None``) BEFORE issuing any request, instead of starting
    on a capped provider and only finding out at the end of pagination.

    ``pool`` fixture: etherscan (priority 1, ``result_window=10_000``) then
    blockscout (priority 2, ``result_window=None``).
    """

    async def test_routes_to_completeness_capable_provider_with_zero_requests_on_capped_one(
        self, pool: ChainscanPool
    ) -> None:
        etherscan, blockscout = (p.client for p in pool._providers)
        eth_calls = {'n': 0}

        def eth_stream(*_a: Any, **_kw: Any) -> AsyncIterator[list[dict[str, Any]]]:
            eth_calls['n'] += 1  # pragma: no cover - must never run
            return stream_stub([{'address': HOLDER, 'value': '999'}])()

        etherscan.iter_token_holders_streaming = eth_stream  # type: ignore[assignment]
        blockscout.iter_token_holders_streaming = stream_stub(  # type: ignore[assignment]
            [{'address': HOLDER, 'value': '5'}]
        )

        with pytest.warns(ChainscanProviderSwitchWarning):
            batches = [batch async for batch in pool.iter_token_holders_streaming(TOKEN)]

        assert batches == [[{'address': HOLDER, 'value': '5'}]]
        assert eth_calls['n'] == 0, 'capped provider must receive zero requests'
        assert pool.last_provider == 'blockscout/ethereum'

    async def test_no_capable_provider_raises_immediately_with_zero_requests(
        self, etherscan: ChainscanClient, clock: FakeClock
    ) -> None:
        """Single capped provider (etherscan) and no alternative in the pool."""
        pool = ChainscanPool([etherscan], clock=clock)
        eth_calls = {'n': 0}

        def eth_stream(*_a: Any, **_kw: Any) -> AsyncIterator[list[dict[str, Any]]]:
            eth_calls['n'] += 1  # pragma: no cover - must never run
            return stream_stub([{'address': HOLDER, 'value': '5'}])()

        etherscan.iter_token_holders_streaming = eth_stream  # type: ignore[assignment]

        async def collect() -> list[list[dict[str, Any]]]:
            return [batch async for batch in pool.iter_token_holders_streaming(TOKEN)]

        with pytest.raises(CompletenessUnavailableError) as excinfo:
            await asyncio.wait_for(collect(), timeout=5.0)

        assert eth_calls['n'] == 0, 'no request should be issued before the raise'
        assert excinfo.value.method == Method.TOKEN_HOLDERS.name
        assert excinfo.value.alternatives == ()
        assert pool.last_provider is None

    async def test_capable_provider_in_cooldown_is_not_selected(
        self, pool: ChainscanPool, clock: FakeClock
    ) -> None:
        """blockscout (completeness-capable) is cooling → must not be used,

        and the pool must not fall back to the capped etherscan either: it
        raises immediately instead, exactly as with no alternative at all.
        """
        etherscan, blockscout = (p.client for p in pool._providers)
        eth_calls = {'n': 0}
        bs_calls = {'n': 0}

        def eth_stream(*_a: Any, **_kw: Any) -> AsyncIterator[list[dict[str, Any]]]:
            eth_calls['n'] += 1  # pragma: no cover - must never run
            return stream_stub([{'address': HOLDER, 'value': '5'}])()

        def bs_stream(*_a: Any, **_kw: Any) -> AsyncIterator[list[dict[str, Any]]]:
            bs_calls['n'] += 1  # pragma: no cover - cooling, must never run
            return stream_stub([{'address': HOLDER, 'value': '5'}])()

        etherscan.iter_token_holders_streaming = eth_stream  # type: ignore[assignment]
        blockscout.iter_token_holders_streaming = bs_stream  # type: ignore[assignment]

        # Put blockscout into cooldown directly (no request needed to test this).
        pool._providers[1].enter_cooldown(
            clock.now + 3600.0, ValueError('cooling'), FailureKind.TRANSIENT
        )

        async def collect() -> list[list[dict[str, Any]]]:
            return [batch async for batch in pool.iter_token_holders_streaming(TOKEN)]

        with pytest.raises(CompletenessUnavailableError) as excinfo:
            await asyncio.wait_for(collect(), timeout=5.0)

        assert eth_calls['n'] == 0
        assert bs_calls['n'] == 0
        # The cooling capable provider is still named as a real remedy.
        assert excinfo.value.alternatives == ('blockscout/ethereum',)

    async def test_per_method_window_keeps_blockscout_v1_eligible(
        self, etherscan: ChainscanClient, clock: FakeClock
    ) -> None:
        """The documented holders remedy config must actually route to V1.

        BlockScout V1 caps its account endpoints at 10_000 and still serves
        the holder list to exhaustion (``RESULT_WINDOW_OVERRIDES``). Reading
        the scanner-wide window instead made the pool declare it incapable
        and raise ``CompletenessUnavailableError`` before a single request —
        for the very configuration the docs name as the remedy.
        """
        blockscout_v1 = ChainscanClient(resolve_scanner_target('blockscout', 'ethereum'))
        pool = ChainscanPool([etherscan, blockscout_v1], clock=clock)
        blockscout_v1.iter_token_holders_streaming = stream_stub(  # type: ignore[assignment]
            [{'address': HOLDER, 'value': '5'}]
        )

        with pytest.warns(ChainscanProviderSwitchWarning):
            batches = [batch async for batch in pool.iter_token_holders_streaming(TOKEN)]

        assert batches == [[{'address': HOLDER, 'value': '5'}]]
        assert pool.last_provider == 'blockscout/ethereum'

    async def test_guarantee_complete_false_is_unaffected(self, pool: ChainscanPool) -> None:
        """With ``guarantee_complete=False`` the capped priority-1 provider serves as before."""
        etherscan, blockscout = (p.client for p in pool._providers)
        etherscan.iter_token_holders_streaming = stream_stub(  # type: ignore[assignment]
            [{'address': HOLDER, 'value': '5'}]
        )
        blockscout.iter_token_holders_streaming = stream_stub()  # type: ignore[assignment]

        batches = [
            batch
            async for batch in pool.iter_token_holders_streaming(TOKEN, guarantee_complete=False)
        ]

        assert batches == [[{'address': HOLDER, 'value': '5'}]]
        assert pool.last_provider == 'etherscan/ethereum'


# ---------------------------------------------------------------------------
# Transparency: progress callbacks + observability
# ---------------------------------------------------------------------------


class TestTransparency:
    async def test_progress_callback_receives_provider(self, pool: ChainscanPool) -> None:
        etherscan, blockscout = (p.client for p in pool._providers)
        etherscan.iter_transactions_streaming = stream_stub(  # type: ignore[assignment]
            [{'hash': '0x1'}],
            [{'hash': '0x2'}],
        )
        blockscout.iter_transactions_streaming = stream_stub()  # type: ignore[assignment]

        events: list[dict[str, Any]] = []

        async def progress(**kwargs: Any) -> None:
            events.append(kwargs)

        await pool.get_all_transactions(ADDR, on_progress=progress)

        assert events, 'progress callback must fire'
        assert all(e.get('provider') == 'etherscan/ethereum' for e in events)

    async def test_progress_callback_without_provider_kwarg_still_works(
        self, pool: ChainscanPool
    ) -> None:
        """Callbacks with a strict signature are called unmodified."""
        etherscan, _blockscout = (p.client for p in pool._providers)
        etherscan.iter_transactions_streaming = stream_stub(  # type: ignore[assignment]
            [{'hash': '0x1'}],
        )

        events: list[dict[str, Any]] = []

        async def progress(
            fetched: int,
            total_expected: int | None,
            current_page: int | None = None,
            operation: str = 'fetch',
        ) -> None:
            events.append({'fetched': fetched})

        txs = await pool.get_all_transactions(ADDR, on_progress=progress)  # type: ignore[arg-type]

        assert txs == [{'hash': '0x1'}]
        assert events == [{'fetched': 1}]


# ---------------------------------------------------------------------------
# Declared forwarding surface: every accepted param actually reaches the member
# ---------------------------------------------------------------------------


class TestStreamForwardSurface:
    """The pool's one-line stream forwards must forward EVERYTHING they accept.

    Companion to ``test_method_consistency``'s signature-mirror guard (which
    pins WHAT the pool accepts): this drives the real forwarding path — every
    parameter of every declared stream reaches the member client verbatim,
    ``guarantee_complete`` included (the historical drift: the pool's
    ``iter_transactions``/``iter_logs`` accepted neither, and a hand-copied
    body could silently drop a param again).
    """

    @staticmethod
    def _sentinel(name: str, param: inspect.Parameter) -> Any:
        """A distinctive value for one signature parameter (member is stubbed)."""
        if name == 'on_progress':

            async def accepts_anything(**_kwargs: Any) -> None:
                return None

            return accepts_anything
        if isinstance(param.default, bool):
            return not param.default  # False for default-True guarantee_complete
        if isinstance(param.default, int):
            return param.default + 1  # never the default itself
        return f'<sentinel:{name}>'  # str / None / list defaults

    async def test_every_declared_stream_forwards_all_params(self) -> None:
        for spec in STREAMING_SPECS:
            member = make_etherscan_client()
            forwarded: dict[str, Any] = {}
            setattr(member, spec.name, self._recorder(forwarded))
            pool = ChainscanPool([member])

            sentinels = {
                name: self._sentinel(name, param)
                for name, param in inspect.signature(
                    getattr(ChainscanPool, spec.name)
                ).parameters.items()
                if name != 'self'
            }
            assert sentinels, f'{spec.name}: no parameters found to forward'

            batches = [b async for b in getattr(pool, spec.name)(**sentinels)]

            assert batches == [[{'ok': True}]], f'{spec.name}: stream did not flow'
            for name, value in sentinels.items():
                if name == 'on_progress':
                    # Batch streams stamp provider= by wrapping the callback;
                    # item-level streams have no callback parameter at all.
                    assert 'on_progress' in forwarded, f'{spec.name} dropped on_progress'
                    assert (
                        forwarded['on_progress'] is not value
                    ), f'{spec.name} forwarded the callback unwrapped (no provider stamp)'
                else:
                    assert forwarded.get(name) == value, (
                        f'{spec.name} accepted {name}={value!r} but forwarded '
                        f'{name}={forwarded.get(name)!r} — pool forward drift'
                    )
            await pool.close()

    @staticmethod
    def _recorder(target: dict[str, Any]) -> Any:
        """Member-client stand-in capturing the kwargs it was called with."""

        async def recorder(**kwargs: Any) -> AsyncIterator[list[dict[str, Any]]]:
            target.update(kwargs)
            yield [{'ok': True}]

        return recorder

    def test_provider_states_snapshot(self, pool: ChainscanPool) -> None:
        states = pool.provider_states()
        assert set(states) == {'etherscan/ethereum', 'blockscout/ethereum'}
        for state in states.values():
            assert state['available'] is True
            assert state['cooldown_remaining'] == 0
            assert state['sticky'] is False
            assert state['last_error'] is None

    async def test_provider_states_reflect_sticky_and_cooldown(self, pool: ChainscanPool) -> None:
        c1 = stub_client(pool._providers[0].client)
        c1.side_effect = rate_limit(retry_after=60)
        stub_client(pool._providers[1].client)
        await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        states = pool.provider_states()
        assert states['etherscan/ethereum']['available'] is False
        assert states['etherscan/ethereum']['last_error'] is not None
        assert states['blockscout/ethereum']['sticky'] is True


# ---------------------------------------------------------------------------
# Construction, lifecycle, factories
# ---------------------------------------------------------------------------


class TestConstructionAndLifecycle:
    def test_requires_at_least_one_client(self) -> None:
        with pytest.raises(ValueError, match='at least one'):
            ChainscanPool([])

    def test_rejects_non_client_objects(self) -> None:
        with pytest.raises(TypeError, match='ChainscanClient'):
            ChainscanPool(['etherscan'])  # type: ignore[list-item]

    def test_from_config_builds_pool_in_priority_order(
        self, etherscan: ChainscanClient, blockscout: ChainscanClient
    ) -> None:
        with (
            patch.object(ChainscanClient, 'from_config') as factory,
        ):
            factory.side_effect = [etherscan, blockscout]
            pool = ChainscanPool.from_config(
                [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]
            )
        assert pool.providers == ('etherscan/ethereum', 'blockscout/ethereum')
        assert factory.call_count == 2

    def test_from_config_skips_unconstructible_provider_with_warning(
        self, blockscout: ChainscanClient
    ) -> None:
        def fake_from_config(scanner: str, network: str, **_kw: Any) -> ChainscanClient:
            if scanner == 'etherscan':
                raise ValueError('ETHERSCAN_KEY is not configured')
            return blockscout

        with (
            patch.object(ChainscanClient, 'from_config', side_effect=fake_from_config),
            pytest.warns(ChainscanProviderSwitchWarning, match='etherscan'),
        ):
            pool = ChainscanPool.from_config(
                [('etherscan', 'ethereum'), ('blockscout', 'ethereum')]
            )

        assert pool.providers == ('blockscout/ethereum',)

    def test_from_config_raises_when_all_providers_unconstructible(self) -> None:
        def fake_from_config(scanner: str, _network: str, **_kw: Any) -> ChainscanClient:
            raise ValueError(f'{scanner} unusable')

        with (
            patch.object(ChainscanClient, 'from_config', side_effect=fake_from_config),
            pytest.raises(ValueError, match='etherscan unusable'),
        ):
            ChainscanPool.from_config([('etherscan', 'ethereum'), ('blockscout', 'ethereum')])

    async def test_close_closes_all_clients(self, pool: ChainscanPool) -> None:
        closes = [AsyncMock() for _ in pool._providers]
        for provider, close in zip(pool._providers, closes, strict=True):
            provider.client.close = close  # type: ignore[method-assign]
        await pool.close()
        for close in closes:
            close.assert_awaited_once()

    async def test_async_context_manager_closes(self, pool: ChainscanPool) -> None:
        provider_closes = [AsyncMock() for _ in pool._providers]
        for provider, close in zip(pool._providers, provider_closes, strict=True):
            provider.client.close = close  # type: ignore[method-assign]
        async with pool:
            stub_client(pool._providers[0].client)
            await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)
        for close in provider_closes:
            close.assert_awaited_once()

    def test_active_client_attributes_delegate(
        self, pool: ChainscanPool, etherscan: ChainscanClient
    ) -> None:
        assert pool.scanner_name == 'etherscan'
        assert pool.scanner_version == 'v2'
        assert pool.chain_id == 1
        assert pool.currency == 'ETH'


# ---------------------------------------------------------------------------
# Label uniqueness and capability-routing silence
# ---------------------------------------------------------------------------


class TestProviderLabels:
    """One label per member — the pool's whole transparency surface.

    ``blockscout`` v1 and v2 on the same chain (the documented V1→V2 failover
    pair) share ``blockscout/ethereum``: with duplicate labels
    ``provider_states()`` collapsed two members into one row and
    ``ProviderPoolExhaustedError.attempts`` dropped the second failure,
    reporting "All 1 providers failed" after two real attempts.
    """

    def test_colliding_members_get_distinct_labels(self, clock: FakeClock) -> None:
        v1 = ChainscanClient(resolve_scanner_target('blockscout', 'ethereum'))
        v2 = ChainscanClient(resolve_scanner_target('blockscout_v2', 'ethereum'))

        pool = ChainscanPool([v1, v2], clock=clock)

        assert pool.providers == ('blockscout v1/ethereum', 'blockscout v2/ethereum')
        assert len(pool.provider_states()) == 2

    def test_distinct_members_keep_the_documented_format(self, pool: ChainscanPool) -> None:
        assert pool.providers == ('etherscan/ethereum', 'blockscout/ethereum')

    async def test_every_member_failure_reaches_attempts(self, clock: FakeClock) -> None:
        v1 = ChainscanClient(resolve_scanner_target('blockscout', 'ethereum'))
        v2 = ChainscanClient(resolve_scanner_target('blockscout_v2', 'ethereum'))
        pool = ChainscanPool([v1, v2], clock=clock)
        v1.call = AsyncMock(side_effect=rate_limit())  # type: ignore[assignment]
        v2.call = AsyncMock(side_effect=rate_limit())  # type: ignore[assignment]

        with (
            pytest.warns(ChainscanProviderSwitchWarning),
            pytest.raises(ProviderPoolExhaustedError) as excinfo,
        ):
            await pool.call(Method.ACCOUNT_BALANCE, address=ADDR)

        assert [label for label, _ in excinfo.value.attempts] == [
            'blockscout v1/ethereum',
            'blockscout v2/ethereum',
        ]


class TestCapabilityRoutingIsSilent:
    """Routing past a provider that never declared the method is not a switch.

    The skipped provider was never asked, so the only reason the warning could
    give ("provider selection changed") describes nothing that happened — and
    the exception's own docstring promises capability routing is silent.
    """

    async def test_skipping_an_undeclaring_provider_emits_no_warning(
        self, clock: FakeClock
    ) -> None:
        blockscout = make_blockscout_client()  # no GAS_ORACLE in SPECS
        etherscan = make_etherscan_client()
        pool = ChainscanPool([blockscout, etherscan], clock=clock)
        bs_call = stub_client(blockscout)
        stub_client(etherscan, {'SafeGasPrice': '10'})

        with warnings.catch_warnings():
            warnings.simplefilter('error', ChainscanProviderSwitchWarning)
            result = await pool.call(Method.GAS_ORACLE)

        assert result == {'SafeGasPrice': '10'}
        assert bs_call.await_count == 0
        assert pool.last_provider == 'etherscan/ethereum'

    async def test_a_real_failure_before_the_skip_still_warns(self, clock: FakeClock) -> None:
        """``pending`` wins: a genuine failure earlier in the walk is reported."""
        etherscan = make_etherscan_client()
        blockscout = make_blockscout_client()
        second_etherscan = make_etherscan_client()
        pool = ChainscanPool([etherscan, blockscout, second_etherscan], clock=clock)
        stub_client(etherscan).side_effect = rate_limit()
        stub_client(blockscout)  # undeclared method — never called
        stub_client(second_etherscan, {'SafeGasPrice': '10'})

        with pytest.warns(ChainscanProviderSwitchWarning, match='rate limit'):
            assert await pool.call(Method.GAS_ORACLE) == {'SafeGasPrice': '10'}
