from aiochainscan.exceptions import (
    ChainscanClientApiError,
    ChainscanClientContentTypeError,
    ChainscanClientProxyError,
)


def test_content_type_error():
    e = ChainscanClientContentTypeError(1, 2)
    assert e.status == 1
    assert e.content == 2
    assert str(e) == '[1] 2'


def test_api_error():
    e = ChainscanClientApiError(1, 2)
    assert e.message == 1
    assert e.result == 2
    assert str(e) == '[1] 2'


def test_proxy_error():
    e = ChainscanClientProxyError(1, 2)
    assert e.code == 1
    assert e.message == 2
    assert str(e) == '[1] 2'
