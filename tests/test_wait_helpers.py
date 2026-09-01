"""Offline tests for the ``wait_for_*`` polling helpers.

The helpers are pure composition over ``client.call`` — every test mocks the
call seam (same pattern as ``test_client_convenience.py``) and asserts the
polling semantics: first-attempt success, pending outcomes that keep polling,
terminal verdicts that are returned (never raised), deadline-bounded timeouts
and loud propagation of hard errors.

Timing strategy: real event-loop clock with tiny ``timeout``/``poll_interval``
values (never monkeypatched ``asyncio.sleep``), so the actual await/sleep
cycle is exercised while each test stays well under a second.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aiochainscan.core.client import ChainscanClient
from aiochainscan.core.method import Method
from aiochainscan.domain.models import TxHash
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientError,
    ChainscanNetworkError,
    ChainscanRateLimitError,
    ChainscanWaitTimeoutError,
)

TEST_TX_HASH = '0x' + 'ab' * 32
TEST_GUID = 'c31a4fbc-dad1-4c1e-a3cf-a66b62b5e00e'

# Explorer answers used across the polling tests.
PENDING_TX_ERROR = ChainscanClientApiError('NOTOK', 'Error! Invalid transaction hash')
PENDING_VERIFY_ERROR = ChainscanClientApiError('NOTOK', 'Pending in queue')
ALREADY_PASS_ERROR = ChainscanClientApiError('NOTOK', 'Error! Block number already pass')
NOT_FOUND_404 = ChainscanClientError('HTTP 404 for https://explorer/api/v2/blocks/200')

MINED_OK = {'isError': '0', 'errDescription': ''}
MINED_REVERT = {'isError': '1', 'errDescription': 'out of gas'}
NODEREAL_MINED = {'status': '1', 'message': 'OK', 'result': '1'}
NODEREAL_PENDING = {'status': '0', 'message': 'Transaction not found', 'result': ''}

COUNTDOWN_REACHED = {
    'CurrentBlock': '200',
    'CountdownBlock': '200',
    'RemainingBlock': '0',
    'EstimateTimeInSec': '0.0',
}
COUNTDOWN_FUTURE = {
    'CurrentBlock': '195',
    'CountdownBlock': '200',
    'RemainingBlock': '5',
    'EstimateTimeInSec': '60.0',
}

# Fast-poll kwargs used by tests that exercise the polling loop.
FAST_POLL = {'timeout': 5.0, 'poll_interval': 0.01}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> ChainscanClient:
    """Create a ChainscanClient with a mocked scanner (no network calls)."""
    with patch('aiochainscan.core.client.get_scanner_class'):
        return ChainscanClient('etherscan', 'v2', 'eth', 'ethereum', 'test_key')


@pytest.fixture
def mock_call(client: ChainscanClient) -> AsyncMock:
    """Patch ``client.call`` so tests never hit the network."""
    m = AsyncMock()
    client.call = m  # type: ignore[assignment]
    return m


@pytest.fixture
def no_countdown_client(client: ChainscanClient) -> ChainscanClient:
    """Scanner without BLOCK_COUNTDOWN support (BlockScout V2 path)."""
    client._scanner.supports_method = Mock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# wait_for_transaction
# ---------------------------------------------------------------------------


class TestWaitForTransaction:
    async def test_final_status_first_attempt(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = MINED_OK

        result = await client.wait_for_transaction(TEST_TX_HASH, **FAST_POLL)

        mock_call.assert_awaited_once_with(
            Method.TX_STATUS_CHECK,
            txhash=str(TxHash(TEST_TX_HASH)),
        )
        assert result == MINED_OK

    async def test_revert_returned_first_attempt(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        """A reverted transaction is a final outcome: returned, not raised."""
        mock_call.return_value = MINED_REVERT

        result = await client.wait_for_transaction(TEST_TX_HASH, **FAST_POLL)

        assert result == MINED_REVERT
        assert mock_call.await_count == 1

    async def test_pending_keeps_polling_until_final(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = [PENDING_TX_ERROR, PENDING_TX_ERROR, MINED_REVERT]

        result = await client.wait_for_transaction(TEST_TX_HASH, **FAST_POLL)

        assert result == MINED_REVERT
        assert mock_call.await_count == 3

    async def test_rate_limit_keeps_polling(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = [ChainscanRateLimitError('Max rate limit reached'), MINED_OK]

        result = await client.wait_for_transaction(TEST_TX_HASH, **FAST_POLL)

        assert result == MINED_OK
        assert mock_call.await_count == 2

    async def test_nodereal_envelope_is_final(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = NODEREAL_MINED

        result = await client.wait_for_transaction(TEST_TX_HASH, **FAST_POLL)

        assert result == NODEREAL_MINED
        assert mock_call.await_count == 1

    async def test_nodereal_pending_envelope_keeps_polling(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = [NODEREAL_PENDING, NODEREAL_MINED]

        result = await client.wait_for_transaction(TEST_TX_HASH, **FAST_POLL)

        assert result == NODEREAL_MINED
        assert mock_call.await_count == 2

    async def test_timeout_raises_with_last_state(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = PENDING_TX_ERROR

        with pytest.raises(ChainscanWaitTimeoutError) as excinfo:
            await client.wait_for_transaction(TEST_TX_HASH, timeout=0.1, poll_interval=0.01)

        exc = excinfo.value
        assert isinstance(exc, TimeoutError)
        assert exc.last_state is PENDING_TX_ERROR
        assert exc.waited >= 0.09
        assert 'transaction' in exc.what
        assert mock_call.await_count >= 2

    async def test_zero_timeout_tries_exactly_once(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = PENDING_TX_ERROR

        with pytest.raises(ChainscanWaitTimeoutError):
            await client.wait_for_transaction(TEST_TX_HASH, timeout=0.0, poll_interval=0.01)

        assert mock_call.await_count == 1

    async def test_sleep_is_capped_by_deadline(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        """A poll_interval larger than the budget must not overshoot the deadline."""
        mock_call.side_effect = PENDING_TX_ERROR

        started = time.perf_counter()
        with pytest.raises(ChainscanWaitTimeoutError):
            await client.wait_for_transaction(TEST_TX_HASH, timeout=0.05, poll_interval=30.0)
        elapsed = time.perf_counter() - started

        assert elapsed < 2.0
        # The capped sleep lands on the deadline, where one last-chance
        # attempt is made before giving up.
        assert mock_call.await_count == 2

    async def test_network_error_propagates(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = ChainscanNetworkError('boom', retryable=True)

        with pytest.raises(ChainscanNetworkError):
            await client.wait_for_transaction(TEST_TX_HASH, **FAST_POLL)

        assert mock_call.await_count == 1

    async def test_invalid_hash_rejected_before_polling(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        with pytest.raises(ValueError, match='TxHash'):
            await client.wait_for_transaction('0xdeadbeef', **FAST_POLL)

        assert mock_call.await_count == 0

    async def test_negative_timeout_rejected(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        with pytest.raises(ValueError, match='timeout'):
            await client.wait_for_transaction(TEST_TX_HASH, timeout=-1.0)

        assert mock_call.await_count == 0


# ---------------------------------------------------------------------------
# wait_for_verification
# ---------------------------------------------------------------------------


class TestWaitForVerification:
    async def test_pass_first_attempt(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = 'Pass - Verified'

        result = await client.wait_for_verification(TEST_GUID, **FAST_POLL)

        mock_call.assert_awaited_once_with(Method.CONTRACT_VERIFY_STATUS, guid=TEST_GUID)
        assert result == 'Pass - Verified'

    async def test_pending_in_queue_keeps_polling(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = [PENDING_VERIFY_ERROR, 'Pass - Verified']

        result = await client.wait_for_verification(TEST_GUID, **FAST_POLL)

        assert result == 'Pass - Verified'
        assert mock_call.await_count == 2

    async def test_fail_verdict_is_returned(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        """A Fail verdict is a final outcome: returned, not raised."""
        mock_call.return_value = 'Fail - Unable to verify'

        result = await client.wait_for_verification(TEST_GUID, **FAST_POLL)

        assert result == 'Fail - Unable to verify'
        assert mock_call.await_count == 1

    async def test_non_string_result_keeps_polling(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = [{'unexpected': 'shape'}, 'Pass - Verified']

        result = await client.wait_for_verification(TEST_GUID, **FAST_POLL)

        assert result == 'Pass - Verified'
        assert mock_call.await_count == 2

    async def test_timeout_while_pending(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = PENDING_VERIFY_ERROR

        with pytest.raises(ChainscanWaitTimeoutError) as excinfo:
            await client.wait_for_verification(TEST_GUID, timeout=0.1, poll_interval=0.01)

        assert excinfo.value.last_state is PENDING_VERIFY_ERROR
        assert 'verification' in excinfo.value.what

    async def test_unknown_guid_propagates(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = ChainscanClientApiError('NOTOK', 'Unknown UID')

        with pytest.raises(ChainscanClientApiError):
            await client.wait_for_verification(TEST_GUID, **FAST_POLL)

        assert mock_call.await_count == 1

    async def test_empty_guid_rejected(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        with pytest.raises(ValueError, match='guid'):
            await client.wait_for_verification('', **FAST_POLL)

        assert mock_call.await_count == 0


# ---------------------------------------------------------------------------
# wait_for_block
# ---------------------------------------------------------------------------


class TestWaitForBlock:
    async def test_reached_snapshot_first_attempt(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.return_value = COUNTDOWN_REACHED

        result = await client.wait_for_block(200, **FAST_POLL)

        mock_call.assert_awaited_once_with(Method.BLOCK_COUNTDOWN, block_number=200)
        assert result == COUNTDOWN_REACHED

    async def test_counts_down_until_reached(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = [COUNTDOWN_FUTURE, COUNTDOWN_FUTURE, COUNTDOWN_REACHED]

        result = await client.wait_for_block(200, **FAST_POLL)

        assert result == COUNTDOWN_REACHED
        assert mock_call.await_count == 3

    async def test_current_block_past_target_is_final(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        snapshot = {**COUNTDOWN_FUTURE, 'CurrentBlock': '201'}
        mock_call.return_value = snapshot

        result = await client.wait_for_block(200, **FAST_POLL)

        assert result == snapshot
        assert mock_call.await_count == 1

    async def test_already_passed_error_synthesizes_snapshot(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        """Etherscan only serves countdowns for future blocks: the documented
        "already pass" error means the target is mined."""
        mock_call.side_effect = ALREADY_PASS_ERROR

        result = await client.wait_for_block(200, **FAST_POLL)

        assert result == {'CountdownBlock': '200', 'RemainingBlock': '0'}
        assert mock_call.await_count == 1

    async def test_other_countdown_api_errors_propagate(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = ChainscanClientApiError('NOTOK', 'Error! Invalid block number')

        with pytest.raises(ChainscanClientApiError):
            await client.wait_for_block(200, **FAST_POLL)

        assert mock_call.await_count == 1

    async def test_countdown_timeout(self, client: ChainscanClient, mock_call: AsyncMock) -> None:
        mock_call.return_value = COUNTDOWN_FUTURE

        with pytest.raises(ChainscanWaitTimeoutError) as excinfo:
            await client.wait_for_block(200, timeout=0.1, poll_interval=0.01)

        assert excinfo.value.last_state == COUNTDOWN_FUTURE
        assert 'block 200' in excinfo.value.what

    async def test_negative_block_rejected(
        self, client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        with pytest.raises(ValueError, match='block_number'):
            await client.wait_for_block(-1, **FAST_POLL)

        assert mock_call.await_count == 0

    # -- BlockScout V2 path (no BLOCK_COUNTDOWN support) -------------------

    async def test_block_appears_after_404(
        self, no_countdown_client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        block = {'height': 200, 'hash': '0x' + 'cd' * 32}
        mock_call.side_effect = [NOT_FOUND_404, block]

        result = await no_countdown_client.wait_for_block(200, **FAST_POLL)

        mock_call.assert_awaited_with(Method.BLOCK_BY_NUMBER, block_number=200)
        assert result == block
        assert mock_call.await_count == 2

    async def test_wrapped_not_found_network_error_keeps_polling(
        self, no_countdown_client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        """BlockScout V2 wraps explorer 404s in a non-retryable network error."""
        wrapped = ChainscanNetworkError(
            'Blockscout V2 unexpected error for https://eth.blockscout.com: HTTP 404',
            retryable=False,
        )
        block = {'height': 200}
        mock_call.side_effect = [wrapped, block]

        result = await no_countdown_client.wait_for_block(200, **FAST_POLL)

        assert result == block
        assert mock_call.await_count == 2

    async def test_retryable_network_error_propagates(
        self, no_countdown_client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = ChainscanNetworkError('boom', retryable=True)

        with pytest.raises(ChainscanNetworkError):
            await no_countdown_client.wait_for_block(200, **FAST_POLL)

        assert mock_call.await_count == 1

    async def test_existence_path_timeout(
        self, no_countdown_client: ChainscanClient, mock_call: AsyncMock
    ) -> None:
        mock_call.side_effect = NOT_FOUND_404

        with pytest.raises(ChainscanWaitTimeoutError) as excinfo:
            await no_countdown_client.wait_for_block(200, timeout=0.1, poll_interval=0.01)

        assert excinfo.value.last_state is NOT_FOUND_404


# ---------------------------------------------------------------------------
# ChainscanWaitTimeoutError
# ---------------------------------------------------------------------------


class TestChainscanWaitTimeoutError:
    def test_is_a_timeout_and_client_error(self) -> None:
        exc = ChainscanWaitTimeoutError(what='block 42', waited=5.0, last_state=None)

        assert isinstance(exc, TimeoutError)
        assert isinstance(exc, ChainscanClientError)

    def test_fields_and_message(self) -> None:
        last_state = {'RemainingBlock': '5'}
        exc = ChainscanWaitTimeoutError(
            what='block 42 to be mined', waited=1.25, last_state=last_state
        )

        assert exc.what == 'block 42 to be mined'
        assert exc.waited == 1.25
        assert exc.last_state == last_state
        text = str(exc)
        assert 'block 42 to be mined' in text
        assert '1.2s' in text
        assert 'RemainingBlock' in text
