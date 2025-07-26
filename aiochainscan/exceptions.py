class ChainscanClientError(Exception):
    pass


class ChainscanClientContentTypeError(ChainscanClientError):
    def __init__(self, status, content):
        self.status = status
        self.content = content

    def __str__(self):
        return f'[{self.status}] {self.content!r}'


class ChainscanClientApiError(ChainscanClientError):
    def __init__(self, message, result):
        self.message = message
        self.result = result

    def __str__(self):
        return f'[{self.message}] {self.result}'


class ChainscanClientProxyError(ChainscanClientError):
    """JSON-RPC 2.0 Specification

    https://www.jsonrpc.org/specification#error_object
    """

    def __init__(self, code, message):
        self.code = code
        self.message = message

    def __str__(self):
        return f'[{self.code}] {self.message}'


class FeatureNotSupportedError(ChainscanClientError):
    """Raised when a feature is not supported by the specific blockchain scanner."""

    def __init__(self, feature: str, scanner: str):
        self.feature = feature
        self.scanner = scanner
        super().__init__(f'Feature "{feature}" is not supported by {scanner}')

    def __str__(self):
        return f'Feature "{self.feature}" is not supported by {self.scanner}'


class SourceNotVerifiedError(ChainscanClientError):
    """Contract source code is not verified on explorer."""

    def __init__(self, address: str):
        self.address = address
        super().__init__(f'Contract source code not verified for address {address}')

    def __str__(self):
        return f'Contract source code not verified for address {self.address}'
