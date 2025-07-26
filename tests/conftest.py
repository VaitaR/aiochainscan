"""
Pytest configuration for aiochainscan tests.
"""

import pytest


def pytest_configure(config):
    """Configure pytest - display API key status for integration tests."""
    # Only show API key status if integration tests are being run
    if config.getoption("keyword", None) == "integration" or "test_integration" in str(config.args):
        try:
            from tests.test_integration import print_api_key_status
            print_api_key_status()
        except ImportError:
            pass


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers and information."""
    integration_tests = []
    unit_tests = []
    
    for item in items:
        if "test_integration" in str(item.fspath):
            integration_tests.append(item)
        else:
            unit_tests.append(item)
    
    # If only integration tests are being run, show the status
    if integration_tests and not unit_tests:
        try:
            from tests.test_integration import print_api_key_status
            print_api_key_status()
        except ImportError:
            pass


@pytest.fixture(scope="session", autouse=True)
def integration_test_setup():
    """Setup for integration tests - show API key status if needed."""
    # This fixture runs automatically for all test sessions
    pass 