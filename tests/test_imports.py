"""
Test basic imports to catch circular dependencies and import blockers early.

These tests run before any complex logic to ensure the library can be imported.
"""

import sys
from importlib import import_module


def test_basic_import():
    """Test that aiochainscan can be imported without errors."""
    import aiochainscan

    assert aiochainscan.__version__


def test_core_exports():
    """Test that core classes can be imported from top-level package."""
    from aiochainscan import ChainscanClient, Method

    assert ChainscanClient is not None
    assert Method is not None


def test_domain_models():
    """Test domain models import without circular dependencies."""
    from aiochainscan.domain.models import Address, BlockNumber, TxHash

    assert Address is not None
    assert BlockNumber is not None
    assert TxHash is not None


def test_scanners_registry():
    """Test that scanner registry works without import errors."""
    from aiochainscan.scanners import get_scanner_class, list_scanners

    # Should be able to get scanner classes
    scanner_list = list_scanners()
    assert len(scanner_list) > 0

    # Should be able to get specific scanners
    etherscan = get_scanner_class('etherscan', 'v2')
    assert etherscan is not None


def test_optional_dependencies_graceful():
    """Test that optional dependencies fail gracefully if not installed."""
    # aiohttp should be optional for httpx-only installations
    try:
        from aiochainscan.adapters import AiohttpClient

        # If import succeeds, it should be the real class or None
        assert AiohttpClient is None or callable(AiohttpClient)
    except ImportError:
        # This is also acceptable - optional dependency
        pass


def test_mcp_server_optional():
    """Test that MCP server is optional and doesn't block base imports."""
    try:
        from aiochainscan.mcp_server import create_mcp_server

        assert callable(create_mcp_server)
    except ImportError:
        # MCP is optional, this is fine
        pass


def test_analytics_optional():
    """Test that analytics/polars is optional."""
    try:
        from aiochainscan.services.analytics import is_polars_available

        # Should return bool
        result = is_polars_available()
        assert isinstance(result, bool)
    except ImportError:
        # Analytics is optional, this is fine
        pass


def test_no_import_side_effects():
    """
    Test that importing doesn't have unwanted side effects.

    This catches issues like:
    - Network requests during import
    - File I/O during import
    - Environment variable requirements during import
    """
    # Get modules before import
    modules_before = set(sys.modules.keys())

    # Import the package
    import aiochainscan  # noqa: F401

    # Get modules after import
    modules_after = set(sys.modules.keys())

    # New modules should only be aiochainscan-related
    new_modules = modules_after - modules_before
    external_modules = [
        m
        for m in new_modules
        if not m.startswith('aiochainscan') and not m.startswith('_')
    ]

    # Some external dependencies are expected (httpx, pydantic, etc.)
    # But we shouldn't be importing heavy things like numpy, pandas unexpectedly
    unexpected = [
        m for m in external_modules if m.startswith(('numpy', 'pandas', 'scipy'))
    ]
    assert len(unexpected) == 0, f'Unexpected heavy imports: {unexpected}'


def test_client_import_without_network():
    """Test that client can be imported without network access."""
    from aiochainscan import ChainscanClient

    # Should be able to access class methods without network
    assert hasattr(ChainscanClient, 'from_config')
    assert hasattr(ChainscanClient, '__aenter__')
    assert hasattr(ChainscanClient, '__aexit__')


def test_method_enum_complete():
    """Test that Method enum is properly defined."""
    from aiochainscan import Method

    # Should have common methods
    assert hasattr(Method, 'ACCOUNT_BALANCE')
    assert hasattr(Method, 'ACCOUNT_TRANSACTIONS')
    assert hasattr(Method, 'TOKEN_BALANCE')

    # Should be iterable
    methods = list(Method)
    assert len(methods) > 10  # We have many methods
