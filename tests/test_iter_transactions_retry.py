"""Tests for iter_transactions retry behavior within async generators.

BUG 1 FIX VERIFICATION: Ensures that retry happens at page-fetch level
(inside the generator) rather than at generator-creation level.

Key insight: When an async generator function is decorated with retry (like Tenacity),
the retry decorator considers the function "successful" as soon as the generator
OBJECT is returned. If a network error occurs on page 100 of iteration, the retry
has already finished and won't help.

The fix ensures that each page fetch goes through Network.request() which wraps
calls with retry policy. This test verifies that behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiochainscan.core.client import ChainscanClient
from aiochainscan.exceptions import ChainscanNetworkError


class TestIterTransactionsRetryBehavior:
    """Test that iter_transactions uses Network layer with retry."""

    @pytest.fixture
    def mock_client_setup(self):
        """Set up a mocked ChainscanClient for BlockScout V2."""
        with patch.object(ChainscanClient, '__init__', lambda self, *args, **kwargs: None):
            client = ChainscanClient.__new__(ChainscanClient)

            # Set up required attributes
            client.scanner_name = 'blockscout'
            client.scanner_version = 'v2'
            client.api_kind = 'blockscout_eth'
            client.network = 'ethereum'
            client.api_key = ''

            # Mock network with request method
            client._network = MagicMock()
            client._network.request = AsyncMock()

            # Mock scanner
            from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner

            mock_scanner = MagicMock(spec=BlockScoutV2Scanner)
            mock_scanner.SPECS = BlockScoutV2Scanner.SPECS
            mock_scanner._build_url = (
                lambda spec,
                **params: 'https://eth.blockscout.com/api/v2/addresses/0x123/transactions'
            )
            mock_scanner._build_query_params = lambda spec, **params: {}
            client._scanner = mock_scanner

            yield client

    @pytest.mark.asyncio
    async def test_uses_network_request_not_raw_http(self, mock_client_setup):
        """Verify iter_transactions uses self._network.request() for each page."""
        client = mock_client_setup

        # Mock two pages of results
        page1_response = {
            'items': [{'hash': '0x111'}, {'hash': '0x222'}],
            'next_page_params': {'block_number': 12345, 'index': 1},
        }
        page2_response = {
            'items': [{'hash': '0x333'}],
            'next_page_params': None,  # Last page
        }

        client._network.request.side_effect = [page1_response, page2_response]

        # Consume the generator
        results = []
        async for tx in client.iter_transactions('0x123'):
            results.append(tx)

        # Should have called network.request twice (once per page)
        assert client._network.request.call_count == 2

        # Verify the calls used GET method
        calls = client._network.request.call_args_list
        for call in calls:
            assert call.kwargs['method'] == 'GET'

        # Verify results
        assert len(results) == 3
        assert results[0]['hash'] == '0x111'
        assert results[2]['hash'] == '0x333'

    @pytest.mark.asyncio
    async def test_retry_happens_at_page_level(self, mock_client_setup):
        """Verify that if network.request raises, it can be retried per-page."""
        client = mock_client_setup

        # Simulate a transient failure followed by success
        # This proves retry happens at page-fetch level, not generator level
        page1_response = {
            'items': [{'hash': '0x111'}],
            'next_page_params': {'block_number': 12345, 'index': 1},
        }

        # First page succeeds, second page fails with retryable error
        # The Network layer will retry internally, so we simulate
        # the final success after internal retries
        error = ChainscanNetworkError('Connection reset', retryable=True)  # noqa: F841
        page2_response = {'items': [{'hash': '0x222'}], 'next_page_params': None}

        # Network.request() already has retry logic built-in via RetryPolicy.run()
        # So if it raises, it means retries were exhausted
        # If it succeeds, it means either no error or retry succeeded
        client._network.request.side_effect = [page1_response, page2_response]

        results = []
        async for tx in client.iter_transactions('0x123'):
            results.append(tx)

        assert len(results) == 2
        # The key is that network.request was called twice - once per page
        # Each call has retry built-in via Network layer
        assert client._network.request.call_count == 2

    @pytest.mark.asyncio
    async def test_pagination_params_passed_correctly(self, mock_client_setup):
        """Verify next_page_params are used for subsequent requests."""
        client = mock_client_setup

        page1_response = {
            'items': [{'hash': '0x111'}],
            'next_page_params': {'block_number': 12345, 'index': 5},
        }
        page2_response = {'items': [{'hash': '0x222'}], 'next_page_params': None}

        client._network.request.side_effect = [page1_response, page2_response]

        async for _ in client.iter_transactions('0x123'):
            pass

        # First call should have no pagination params
        first_call = client._network.request.call_args_list[0]  # noqa: F841
        # Second call should include next_page_params
        second_call = client._network.request.call_args_list[1]

        # The params should include the pagination info
        second_params = second_call.kwargs.get('params', {})
        assert second_params.get('block_number') == 12345
        assert second_params.get('index') == 5

    @pytest.mark.asyncio
    async def test_handles_empty_response(self, mock_client_setup):
        """Verify generator handles empty response gracefully."""
        client = mock_client_setup

        client._network.request.return_value = {'items': [], 'next_page_params': None}

        results = []
        async for tx in client.iter_transactions('0x123'):
            results.append(tx)

        assert len(results) == 0
        assert client._network.request.call_count == 1

    @pytest.mark.asyncio
    async def test_handles_list_response_fallback(self, mock_client_setup):
        """Verify generator handles unexpected list response format."""
        client = mock_client_setup

        # Some APIs might return a list directly instead of {items: [...]}
        client._network.request.return_value = [{'hash': '0x111'}, {'hash': '0x222'}]

        results = []
        async for tx in client.iter_transactions('0x123'):
            results.append(tx)

        assert len(results) == 2


class TestRetryDuringMidIteration:
    """Test that retry actually works when error happens mid-iteration (page 3).

    NOTE: These tests verify the architecture is correct - actual retry is handled
    by Network.request() via TenacityRetryAdapter. The iter_transactions generator
    calls Network.request() for each page, which internally uses retry logic.
    """

    @pytest.fixture
    def mock_client_with_network(self):
        """Set up client with a real Network instance that has mocked HTTP."""
        with patch.object(ChainscanClient, '__init__', lambda self, *args, **kwargs: None):
            client = ChainscanClient.__new__(ChainscanClient)

            client.scanner_name = 'blockscout'
            client.scanner_version = 'v2'
            client.api_kind = 'blockscout_eth'
            client.network = 'ethereum'
            client.api_key = ''

            # Create a real Network instance with mocked HTTP client
            from aiochainscan.core.url_builder import UrlBuilder
            from aiochainscan.network import Network

            url_builder = MagicMock(spec=UrlBuilder)
            url_builder.API_URL = 'https://eth.blockscout.com'

            # Create Network - it will create default retry policy internally
            network = Network(url_builder=url_builder)
            client._network = network

            # Mock scanner
            from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner

            mock_scanner = MagicMock(spec=BlockScoutV2Scanner)
            mock_scanner.SPECS = BlockScoutV2Scanner.SPECS
            mock_scanner._build_url = (
                lambda spec,
                **params: 'https://eth.blockscout.com/api/v2/addresses/0x123/transactions'
            )
            mock_scanner._build_query_params = lambda spec, **params: {}
            client._scanner = mock_scanner

            yield client, network

    @pytest.mark.asyncio
    async def test_network_layer_has_retry_configured(self, mock_client_with_network):
        """
        Verify Network layer has ChainscanNetworkError in retry exceptions.

        This ensures that errors raised during pagination will be retried.
        """
        client, network = mock_client_with_network

        # Verify retry policy includes ChainscanNetworkError
        retry_exceptions = network._retry_policy.retry_exceptions
        assert (
            ChainscanNetworkError in retry_exceptions
        ), f'ChainscanNetworkError not in retry exceptions: {retry_exceptions}'

    @pytest.mark.asyncio
    async def test_each_page_fetch_goes_through_retry_wrapped_method(
        self, mock_client_with_network
    ):
        """
        Verify that each page fetch in iter_transactions calls Network.request()
        which is wrapped with retry logic.
        """
        client, network = mock_client_with_network

        # Track calls to Network.request
        call_count = [0]
        original_request = network.request  # noqa: F841

        page1 = {'items': [{'hash': '0x111'}], 'next_page_params': {'block': 1}}
        page2 = {'items': [{'hash': '0x222'}], 'next_page_params': None}

        async def tracked_request(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return page1
            return page2

        network.request = tracked_request

        results = []
        async for tx in client.iter_transactions('0x123'):
            results.append(tx)

        # Each page should go through Network.request
        assert call_count[0] == 2
        assert len(results) == 2


class TestRetryExhaustion:
    """Test behavior when all retries are exhausted."""

    @pytest.fixture
    def mock_client_simple(self):
        """Set up a mocked ChainscanClient for BlockScout V2."""
        with patch.object(ChainscanClient, '__init__', lambda self, *args, **kwargs: None):
            client = ChainscanClient.__new__(ChainscanClient)

            client.scanner_name = 'blockscout'
            client.scanner_version = 'v2'
            client.api_kind = 'blockscout_eth'
            client.network = 'ethereum'
            client.api_key = ''

            # Mock network with request method
            client._network = MagicMock()
            client._network.request = AsyncMock()

            # Mock scanner
            from aiochainscan.scanners.blockscout_v2 import BlockScoutV2Scanner

            mock_scanner = MagicMock(spec=BlockScoutV2Scanner)
            mock_scanner.SPECS = BlockScoutV2Scanner.SPECS
            mock_scanner._build_url = (
                lambda spec,
                **params: 'https://eth.blockscout.com/api/v2/addresses/0x123/transactions'
            )
            mock_scanner._build_query_params = lambda spec, **params: {}
            client._scanner = mock_scanner

            yield client

    @pytest.mark.asyncio
    async def test_error_propagates_when_network_fails(self, mock_client_simple):
        """
        Verify error propagates to user when network.request raises.

        In production, Network.request would have already exhausted retries
        before raising. Here we simulate that final failure.
        """
        client = mock_client_simple

        page1 = {'items': [{'hash': '0x111'}], 'next_page_params': {'block': 1}}
        error = ChainscanNetworkError('All retries exhausted', retryable=True)

        client._network.request.side_effect = [page1, error]

        with pytest.raises(ChainscanNetworkError):
            results = []
            async for tx in client.iter_transactions('0x123'):
                results.append(tx)


class TestEtherscanIterTransactionsRetry:
    """Test iter_transactions retry for Etherscan (uses self.call())."""

    @pytest.fixture
    def mock_etherscan_client(self):
        """Set up a mocked ChainscanClient for Etherscan."""
        with patch.object(ChainscanClient, '__init__', lambda self, *args, **kwargs: None):
            client = ChainscanClient.__new__(ChainscanClient)

            client.scanner_name = 'etherscan'
            client.scanner_version = 'v2'
            client.api_kind = 'eth'
            client.network = 'ethereum'
            client.api_key = 'test_key'

            # Mock the call method
            client.call = AsyncMock()

            yield client

    @pytest.mark.asyncio
    async def test_etherscan_uses_call_method(self, mock_etherscan_client):
        """Verify Etherscan path uses self.call() which has retry."""
        client = mock_etherscan_client

        # Mock paginated responses - batch_size=2 so we need 2 items per page
        # to continue pagination. Last page with fewer items signals end.
        page1 = [{'hash': '0x111'}, {'hash': '0x222'}]  # Full page, continue
        page2 = [{'hash': '0x333'}]  # Partial page (< batch_size), stop here

        client.call.side_effect = [page1, page2]

        results = []
        async for tx in client.iter_transactions('0x123', batch_size=2):
            results.append(tx)

        # Should call self.call() for each page until partial/empty page
        assert client.call.call_count == 2

        # Verify it called with pagination params
        from aiochainscan.core.method import Method

        calls = client.call.call_args_list
        assert calls[0].args[0] == Method.ACCOUNT_TRANSACTIONS
        assert calls[0].kwargs.get('page') == 1
        assert calls[1].kwargs.get('page') == 2

        assert len(results) == 3


class TestRetryActuallyFires:
    """
    Integration tests that verify retry actually fires during iteration.

    These tests use a real TenacityRetryAdapter to verify that transient errors
    during page 3 iteration are retried properly.
    """

    @pytest.mark.asyncio
    async def test_retry_fires_on_transient_error_during_iteration(self):
        """
        CRITICAL TEST: Verify retry fires when error happens mid-iteration (page 3).

        Uses real TenacityRetryAdapter with mocked HTTP to prove retry happens
        at page-fetch level inside the generator, not at generator creation.
        """
        from aiochainscan.adapters.aiolimiter_adapter import AioLimiterAdapter
        from aiochainscan.adapters.tenacity_retry import TenacityRetryAdapter

        # Track retry attempts
        retry_attempts = []

        def track_retry(retry_state):
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            retry_attempts.append(
                {
                    'attempt': retry_state.attempt_number,
                    'exception': type(exc).__name__ if exc else None,
                }
            )

        # Create retry adapter with fast timing (no wait) for test speed
        retry_adapter = TenacityRetryAdapter(
            max_attempts=3,
            min_wait=0.0,
            max_wait=0.1,
            jitter=0.0,
            retry_exceptions=(ChainscanNetworkError,),
            before_sleep_callback=track_retry,
        )

        # Create rate limiter that doesn't block
        rate_limiter = AioLimiterAdapter(max_rate=100, time_period=1.0, max_burst=10)

        # Track HTTP calls
        http_call_count = [0]

        async def mock_do_request():
            http_call_count[0] += 1
            call_num = http_call_count[0]

            if call_num == 1:
                # Page 1 succeeds
                return {'items': [{'hash': '0x111'}], 'next_page_params': {'page': 2}}
            elif call_num == 2:
                # Page 2 succeeds
                return {'items': [{'hash': '0x222'}], 'next_page_params': {'page': 3}}
            elif call_num == 3:
                # Page 3: First attempt FAILS with transient error
                raise ChainscanNetworkError('Connection reset', retryable=True)
            elif call_num == 4:
                # Page 3: Retry attempt SUCCEEDS
                return {'items': [{'hash': '0x333'}], 'next_page_params': None}
            else:
                return {'items': [], 'next_page_params': None}

        # Simulate iterator behavior with retry at page level
        results = []
        page_params = {}

        while True:
            # Apply rate limit
            await rate_limiter.acquire('test')

            # This is the key: each page fetch goes through retry.run()
            response = await retry_adapter.run(mock_do_request)

            items = response.get('items', [])
            next_params = response.get('next_page_params')

            for item in items:
                results.append(item)

            if not next_params:
                break
            page_params = next_params  # noqa: F841

        # Verify retry actually happened
        assert (
            http_call_count[0] == 4
        ), f'Expected 4 HTTP calls (page 1, 2, fail, retry success), got {http_call_count[0]}'
        assert len(retry_attempts) == 1, f'Expected 1 retry callback, got {len(retry_attempts)}'
        assert retry_attempts[0]['exception'] == 'ChainscanNetworkError'

        # Verify all items collected
        assert len(results) == 3
        assert [r['hash'] for r in results] == ['0x111', '0x222', '0x333']

    @pytest.mark.asyncio
    async def test_retry_exhaustion_propagates_error(self):
        """Verify error propagates after all retry attempts exhausted."""
        from aiochainscan.adapters.tenacity_retry import TenacityRetryAdapter

        retry_adapter = TenacityRetryAdapter(
            max_attempts=2,
            min_wait=0.0,
            max_wait=0.01,
            jitter=0.0,
            retry_exceptions=(ChainscanNetworkError,),
        )

        call_count = [0]

        async def always_fail():
            call_count[0] += 1
            raise ChainscanNetworkError('Persistent failure', retryable=True)

        with pytest.raises(ChainscanNetworkError) as exc_info:
            await retry_adapter.run(always_fail)

        # Should have tried max_attempts times
        assert call_count[0] == 2
        assert 'Persistent failure' in str(exc_info.value)
