import pytest
import pytest_asyncio

from aiochainscan.url_builder import UrlBuilder


def apikey():
    return 'test_api_key'


@pytest_asyncio.fixture
async def ub():
    ub = UrlBuilder(apikey(), 'eth', 'main')
    yield ub


def test_sign(ub):
    params, headers = ub.filter_and_sign({}, {})
    assert params == {'chainid': '1'}
    assert headers == {'X-API-Key': ub._API_KEY}

    params, headers = ub.filter_and_sign({'something': 'something'}, {})
    assert params == {'something': 'something', 'chainid': '1'}
    assert headers == {'X-API-Key': ub._API_KEY}

    # Legacy helper still proxies to the new implementation
    legacy_params, legacy_headers = ub._sign({}, {})
    assert legacy_params == {'chainid': '1'}
    assert legacy_headers == {'X-API-Key': ub._API_KEY}


def test_filter_params(ub):
    assert ub._filter_params({}) == {}
    assert ub._filter_params({1: 2, 3: None}) == {1: 2}
    assert ub._filter_params({1: 2, 3: 0}) == {1: 2, 3: 0}
    assert ub._filter_params({1: 2, 3: False}) == {1: 2, 3: False}


def test_query_param_auth():
    ub = UrlBuilder(apikey(), 'fantom', 'main')
    params, headers = ub.filter_and_sign({}, {})
    assert params == {'chainid': '250', 'apikey': ub._API_KEY}
    assert headers == {}


@pytest.mark.parametrize(
    'api_kind,network_name,expected',
    [
        # Etherscan V2 API - unified domain etherscan.io with chainid parameter
        # Reference: https://docs.etherscan.io/v2-migration
        ('eth', 'main', 'https://api.etherscan.io/v2/api'),
        ('bsc', 'main', 'https://api.etherscan.io/v2/api'),
        ('polygon', 'main', 'https://api.etherscan.io/v2/api'),
        ('optimism', 'main', 'https://api.etherscan.io/v2/api'),
        ('arbitrum', 'main', 'https://api.etherscan.io/v2/api'),
        ('base', 'main', 'https://api.etherscan.io/v2/api'),
        # Test networks for main V2-compatible chains
        ('eth', 'sepolia', 'https://api.etherscan.io/v2/api'),
        ('polygon', 'mumbai', 'https://api.etherscan.io/v2/api'),
        # Non-V2 APIs still use their own domains
        ('fantom', 'main', 'https://api.ftmscan.com/api'),
        ('fantom', 'testnet', 'https://api-testnet.ftmscan.com/api'),
        ('gnosis', 'main', 'https://api.gnosisscan.io/api'),
        ('flare', 'main', 'https://flare-explorer.flare.network/api'),
    ],
)
def test_api_url(api_kind, network_name, expected):
    ub = UrlBuilder(apikey(), api_kind, network_name)
    assert expected == ub.API_URL


@pytest.mark.parametrize(
    'api_kind,network_name,expected',
    [
        # Etherscan V2 API - unified domain etherscan.io
        ('eth', 'main', 'https://etherscan.io'),
        ('eth', 'sepolia', 'https://etherscan.io'),
        ('bsc', 'main', 'https://etherscan.io'),
        ('bsc', 'testnet', 'https://etherscan.io'),
        ('polygon', 'main', 'https://etherscan.io'),
        ('polygon', 'mumbai', 'https://etherscan.io'),
        ('optimism', 'main', 'https://etherscan.io'),
        ('arbitrum', 'main', 'https://etherscan.io'),
        ('base', 'main', 'https://etherscan.io'),
        # Non-V2 APIs still use their own domains
        ('fantom', 'main', 'https://ftmscan.com'),
        ('fantom', 'testnet', 'https://testnet.ftmscan.com'),
        ('gnosis', 'main', 'https://gnosisscan.io'),
        ('flare', 'main', 'https://flare.network'),
    ],
)
def test_base_url(api_kind, network_name, expected):
    ub = UrlBuilder(apikey(), api_kind, network_name)
    assert expected == ub.BASE_URL


def test_invalid_api_kind():
    with pytest.raises(ValueError) as exception:
        UrlBuilder(apikey(), 'wrong', 'main')
    assert 'Incorrect api_kind' in str(exception.value)


@pytest.mark.parametrize(
    'api_kind,expected',
    [
        ('eth', 'ETH'),
        ('bsc', 'BNB'),
        ('polygon', 'MATIC'),
        ('optimism', 'ETH'),
        ('arbitrum', 'ETH'),
        ('base', 'BASE'),
        ('fantom', 'FTM'),
    ],
)
def test_currency(api_kind, expected):
    ub = UrlBuilder(apikey(), api_kind, 'main')
    assert ub.currency == expected


# Smoke check for new/more api_kinds mapping shapes (no network I/O)
@pytest.mark.parametrize(
    'api_kind,network,expected_base_contains,expected_api_contains',
    [
        # Base network via Etherscan V2
        ('base', 'main', 'etherscan.io', 'https://api.etherscan.io/v2/api'),
        (
            'routscan_mode',
            'main',
            'api.routescan.io/v2/network/mainnet/evm/34443',
            'https://etherscan.api.routescan.io',
        ),
        ('blockscout_eth', 'main', 'eth.blockscout.com', 'https://eth.blockscout.com/api'),
        (
            'blockscout_sepolia',
            'sepolia',
            'eth-sepolia.blockscout.com',
            'https://eth-sepolia.blockscout.com/api',
        ),
        (
            'blockscout_gnosis',
            'main',
            'gnosis.blockscout.com',
            'https://gnosis.blockscout.com/api',
        ),
        (
            'blockscout_polygon',
            'main',
            'polygon.blockscout.com',
            'https://polygon.blockscout.com/api',
        ),
        ('moralis', 'main', 'deep-index.moralis.io', 'https://api.deep-index.moralis.io'),
    ],
)
def test_api_kinds_smoke(api_kind, network, expected_base_contains, expected_api_contains):
    ub = UrlBuilder(apikey(), api_kind, network)
    assert expected_base_contains in ub.BASE_URL
    assert ub.API_URL.startswith(expected_api_contains)


def test_api_kinds_drift_guard():
    # Ensure UrlBuilder knows all officially supported kinds from docs/instructions
    expected = {
        'eth',
        'bsc',
        'polygon',
        'optimism',
        'arbitrum',
        'fantom',
        'gnosis',
        'flare',
        'wemix',
        'chiliz',
        'mode',
        'linea',
        'blast',
        'base',
        'routscan_mode',
        'blockscout_eth',
        'blockscout_sepolia',
        'blockscout_gnosis',
        'blockscout_polygon',
        'moralis',
    }
    actual = set(UrlBuilder._API_KINDS.keys())
    # Must include at least the expected set (allowing more kinds in future)
    missing = expected - actual
    assert not missing, f'Missing api_kinds in UrlBuilder: {sorted(missing)}'
