
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientError,
    ChainscanClientProxyError,
    FeatureNotSupportedError,
    SourceNotVerifiedError,
)


def test_source_not_verified_exception():
    """Test SourceNotVerifiedError exception."""
    address = "0x1234567890123456789012345678901234567890"

    # Test creation
    exc = SourceNotVerifiedError(address)

    # Test properties
    assert exc.address == address
    assert address in str(exc)
    assert "Contract source code not verified" in str(exc)

    # Test inheritance
    assert isinstance(exc, ChainscanClientError)
    assert isinstance(exc, Exception)


def test_feature_not_supported_error():
    """Test FeatureNotSupportedError exception."""
    feature = "gas_estimate"
    scanner = "bsc:main"

    # Test creation
    exc = FeatureNotSupportedError(feature, scanner)

    # Test properties
    assert exc.feature == feature
    assert exc.scanner == scanner
    assert feature in str(exc)
    assert scanner in str(exc)

    # Test inheritance
    assert isinstance(exc, ChainscanClientError)


def test_all_exceptions_inherit_properly():
    """Test that all custom exceptions inherit from ChainscanClientError."""
    exceptions_to_test = [
        ChainscanClientApiError("test", "result"),
        ChainscanClientContentTypeError(500, "error"),
        ChainscanClientProxyError("123", "message"),
        FeatureNotSupportedError("feature", "scanner"),
        SourceNotVerifiedError("0x123"),
    ]

    for exc in exceptions_to_test:
        assert isinstance(exc, ChainscanClientError)
        assert isinstance(exc, Exception)

        # Test that they have meaningful string representations
        assert len(str(exc)) > 0


def test_exception_messages():
    """Test exception message formatting."""
    # SourceNotVerifiedError
    exc = SourceNotVerifiedError("0xabc123")
    expected = "Contract source code not verified for address 0xabc123"
    assert str(exc) == expected

    # FeatureNotSupportedError
    exc = FeatureNotSupportedError("test_feature", "test_scanner")
    expected = 'Feature "test_feature" is not supported by test_scanner'
    assert str(exc) == expected
