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


class ChainscanRateLimitError(ChainscanClientError):
    """Rate limit exceeded - includes AI-friendly retry instructions.

    Etherscan and similar APIs often return HTTP 200 with error message
    like {"status":"0","message":"NOTOK","result":"Max rate limit reached"}.
    This exception signals that the request should be retried after a delay.
    """

    def __init__(
        self, message: str | None = None, result: Any = None, retry_after: int = 5
    ) -> None:
        self.message: str | None = message
        self.result: Any = result
        self.retry_after = retry_after
        self._ai_instruction = (
            f'[AI_INSTRUCTION: Rate limit hit. Wait {retry_after} seconds using '
            f'asyncio.sleep({retry_after}), then retry with exact same arguments. '
            f'Do not ask user for permission to retry.]'
        )
        super().__init__(str(self))

    def __str__(self) -> str:
        base = f'Rate limit exceeded: [{self.message}] {self.result}'
        return f'{base} {self._ai_instruction}'


class ChainscanInvalidAddressError(ChainscanClientError):
    """Invalid address format - includes AI-friendly correction hint."""

    def __init__(self, address: str) -> None:
        self.address = address
        self._ai_instruction = (
            f"[AI_INSTRUCTION: The address '{address}' is invalid. "
            f"Valid Ethereum addresses are 42 characters starting with '0x'. "
            f'Ask the user to provide a correct address.]'
        )
        super().__init__(str(self))

    def __str__(self) -> str:
        return f'Invalid address format: {self.address}. {self._ai_instruction}'


class ChainscanNetworkError(ChainscanClientError):
    """Network/connection error - includes AI-friendly retry guidance."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        self.message = message
        self.retryable = retryable
        if retryable:
            self._ai_instruction = (
                '[AI_INSTRUCTION: Network error occurred. Wait 3 seconds, '
                'then retry. If fails 3 times, inform user of connectivity issues.]'
            )
        else:
            self._ai_instruction = (
                '[AI_INSTRUCTION: Non-recoverable network error. '
                'Inform user and suggest checking network/API status.]'
            )
        super().__init__(str(self))

    def __str__(self) -> str:
        return f'{self.message} {self._ai_instruction}'
