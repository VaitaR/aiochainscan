from __future__ import annotations

from typing import Any


class ChainscanClientError(Exception):
    """Base error type for aiochainscan client failures."""

    pass


class ChainscanClientContentTypeError(ChainscanClientError):
    def __init__(self, status: int, content: Any) -> None:
        self.status: int = status
        self.content: Any = content

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'[{self.status}] {self.content!r}'


class ChainscanClientApiError(ChainscanClientError):
    def __init__(self, message: str | None, result: Any) -> None:
        self.message: str | None = message
        self.result: Any = result

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'[{self.message}] {self.result}'


class ChainscanClientProxyError(ChainscanClientError):
    """JSON-RPC 2.0 Specification

    https://www.jsonrpc.org/specification#error_object
    """

    def __init__(self, code: int | None, message: str | None) -> None:
        self.code: int | None = code
        self.message: str | None = message

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'[{self.code}] {self.message}'


class FeatureNotSupportedError(ChainscanClientError):
    """Raised when a feature is not supported by the specific blockchain scanner."""

    def __init__(self, feature: str, scanner: str) -> None:
        self.feature = feature
        self.scanner = scanner
        super().__init__(f'Feature "{feature}" is not supported by {scanner}')

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'Feature "{self.feature}" is not supported by {self.scanner}'


class SourceNotVerifiedError(ChainscanClientError):
    """Contract source code is not verified on explorer."""

    def __init__(self, address: str) -> None:
        self.address = address
        super().__init__(f'Contract source code not verified for address {address}')

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'Contract source code not verified for address {self.address}'
