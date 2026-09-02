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
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method
from aiochainscan.core.pool import (
    ChainscanPool,
    FailureKind,
    classify_failure,
)
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanClientProxyError,
    ChainscanDataError,
    ChainscanInvalidAddressError,
    ChainscanNetworkError,
    ChainscanProviderSwitchWarning,
    ChainscanRateLimitError,
    MethodNotDeclaredError,
    ProviderPoolExhaustedError,
)
from aiochainscan.scanners.blockscout_v1 import BlockScoutV1
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
    return ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'test_key')


def make_blockscout_client() -> ChainscanClient:
    return ChainscanClient('blockscout', 'v2', 'blockscout_eth', 'ethereum', '')


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

    def test_fatal_invalid_address(self) -> None:
        assert classify_failure(ChainscanInvalidAddressError('0x123')) is FailureKind.FATAL

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
    """ChainscanClient shell around a real scanner (no full wiring)."""
    client = ChainscanClient.__new__(ChainscanClient)
    client.scanner_name = scanner.name
    client.scanner_version = scanner.version
    client.network = network
    client._scanner = scanner
    return client


class TestPinnedStreamMethodUndeclared:
    """Drive the REAL streaming path over real scanners.

    ``_pinned_stream`` used to re-select the same METHOD_UNDECLARED provider
    in a tight ``while True`` loop (no cooldown, no capability filter): the
    declaring provider was never reached and the pool spun at 100% CPU.
    """

    @staticmethod
    def _v1_client(network: _ReplayNetwork) -> ChainscanClient:
        # BlockScout v1 does not declare the token-holder methods.
        return _bare_client(
            BlockScoutV1(
                api_key='', network='eth', url_builder=MagicMock(), network_client=network
            ),
            'eth',
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
        holder_page = [{'TokenHolderAddress': HOLDER, 'TokenHolderQuantity': '5'}]
        v1_network = _ReplayNetwork([])  # must never be asked
        etherscan_network = _ReplayNetwork([holder_page])
        pool = ChainscanPool(
            [self._v1_client(v1_network), self._etherscan_client(etherscan_network)]
        )

        batches = [batch async for batch in pool.iter_token_holders_streaming(TOKEN, batch_size=2)]

        assert batches == [[{'address': HOLDER, 'value': '5'}]]
        assert pool.last_provider == 'etherscan/main'
        # The non-declaring provider raised before any HTTP attempt.
        assert v1_network.calls == []
        assert len(etherscan_network.calls) == 1

    async def test_no_provider_declares_terminates(self) -> None:
        """Nobody declares the method → finite exhaustion, not a hang."""
        pool = ChainscanPool([self._v1_client(_ReplayNetwork([]))])

        async def collect() -> list[list[dict[str, Any]]]:
            return [batch async for batch in pool.iter_token_holders_streaming(TOKEN)]

        with pytest.raises(ProviderPoolExhaustedError) as excinfo:
            await asyncio.wait_for(collect(), timeout=5.0)

        attempts = excinfo.value.attempts
        assert len(attempts) == 1
        assert isinstance(attempts[0][1], MethodNotDeclaredError)


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
