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
