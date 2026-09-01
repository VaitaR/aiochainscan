"""Focused URL-builder contract tests."""

from aiochainscan.core.url_builder import UrlBuilder


def test_etherscan_v2_api_key_is_query_auth_only() -> None:
    builder = UrlBuilder('secret-key', 'eth', 'main')

    params, headers = builder.filter_and_sign({'module': 'account'}, {})

    assert params['apikey'] == 'secret-key'
    assert params['chainid'] == '1'
    assert 'X-API-Key' not in headers
