"""
Test deprecation warnings for facade functions.
"""

import warnings

import pytest


def test_facade_function_deprecation_warning():
    """Test that facade functions emit DeprecationWarning."""
    from aiochainscan import _warn_facade_deprecation

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        _warn_facade_deprecation('get_balance')

        # Check warning was raised
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)

        # Check warning message contains key information
        message = str(w[0].message)
        assert 'get_balance()' in message
        assert 'deprecated' in message.lower()
        assert 'v0.5.0' in message
        assert 'ChainscanClient' in message
        assert 'connection pooling' in message.lower()
        assert 'MIGRATION_GUIDE.md' in message


@pytest.mark.asyncio
async def test_get_balance_emits_deprecation():
    """Test that get_balance actually emits the deprecation warning."""
    from aiochainscan import get_balance
    from aiochainscan.adapters.httpx_client import HttpxClientAdapter

    # Create a mock HTTP client to avoid actual network calls
    http = HttpxClientAdapter()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')

        try:
            # This will fail because we're not providing valid params,
            # but it should still emit the warning before failing
            await get_balance(
                address='0x0000000000000000000000000000000000000000',
                api_kind='eth',
                network='main',
                api_key='test',
                http=http,
            )
        except Exception:
            # We expect it to fail, we just want to check the warning
            pass
        finally:
            await http.aclose()

        # Check that deprecation warning was emitted
        deprecation_warnings = [
            warning for warning in w if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1
        assert 'get_balance' in str(deprecation_warnings[0].message)


@pytest.mark.asyncio
async def test_get_block_emits_deprecation():
    """Test that get_block emits the deprecation warning."""
    from aiochainscan import get_block
    from aiochainscan.adapters.httpx_client import HttpxClientAdapter

    http = HttpxClientAdapter()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')

        try:
            await get_block(
                tag='latest',
                full=False,
                api_kind='eth',
                network='main',
                api_key='test',
                http=http,
            )
        except Exception:
            pass
        finally:
            await http.aclose()

        deprecation_warnings = [
            warning for warning in w if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1
        assert 'get_block' in str(deprecation_warnings[0].message)


def test_deprecation_message_quality():
    """Test that deprecation message is helpful and actionable."""
    from aiochainscan import _warn_facade_deprecation

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        _warn_facade_deprecation('test_function')

        message = str(w[0].message)

        # Should explain the problem
        assert '100+ TCP connection' in message or 'TCP connection' in message
        assert 'TLS handshake' in message
        assert 'HTTP/2 multiplexing' in message

        # Should provide solution
        assert 'from aiochainscan import ChainscanClient' in message
        assert 'from aiochainscan.core.method import Method' in message
        assert 'client.call' in message
        assert 'await client.close()' in message

        # Should have link to migration guide
        assert 'MIGRATION_GUIDE.md' in message
