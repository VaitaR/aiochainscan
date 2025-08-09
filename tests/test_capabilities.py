from aiochainscan import get_capabilities_overview
from aiochainscan.capabilities import (
    FEATURE_SUPPORT,
    get_supported_features,
    get_supported_scanners,
    is_feature_supported,
)


def test_is_feature_supported():
    """Test feature support checking."""
    # Gas estimate is only supported on Ethereum mainnet
    assert is_feature_supported('gas_estimate', 'eth', 'main') is True
    assert is_feature_supported('gas_estimate', 'eth', 'sepolia') is False
    assert is_feature_supported('gas_estimate', 'bsc', 'main') is False

    # Gas oracle is supported on multiple networks
    assert is_feature_supported('gas_oracle', 'eth', 'main') is True
    assert is_feature_supported('gas_oracle', 'eth', 'sepolia') is True
    assert is_feature_supported('gas_oracle', 'bsc', 'main') is True
    assert is_feature_supported('gas_oracle', 'polygon', 'main') is True
    assert is_feature_supported('gas_oracle', 'unsupported', 'main') is False

    # Unknown feature
    assert is_feature_supported('unknown_feature', 'eth', 'main') is False


def test_get_supported_scanners():
    """Test getting supported scanner/network combinations for a feature."""
    gas_estimate_scanners = get_supported_scanners('gas_estimate')
    assert gas_estimate_scanners == {('eth', 'main')}

    gas_oracle_scanners = get_supported_scanners('gas_oracle')
    expected_gas_oracle = {
        ('eth', 'main'),
        ('eth', 'sepolia'),
        ('bsc', 'main'),
        ('polygon', 'main'),
        ('arbitrum', 'main'),
        ('base', 'main'),
        ('optimism', 'main'),
    }
    assert gas_oracle_scanners == expected_gas_oracle

    # Unknown feature should return empty set
    unknown_scanners = get_supported_scanners('unknown_feature')
    assert unknown_scanners == set()


def test_get_supported_features():
    """Test getting supported features for a scanner/network combination."""
    # Ethereum mainnet supports both gas_estimate and gas_oracle
    eth_main_features = get_supported_features('eth', 'main')
    assert 'gas_estimate' in eth_main_features
    assert 'gas_oracle' in eth_main_features

    # Ethereum sepolia only supports gas_oracle
    eth_sepolia_features = get_supported_features('eth', 'sepolia')
    assert 'gas_estimate' not in eth_sepolia_features
    assert 'gas_oracle' in eth_sepolia_features

    # BSC mainnet only supports gas_oracle
    bsc_main_features = get_supported_features('bsc', 'main')
    assert 'gas_estimate' not in bsc_main_features
    assert 'gas_oracle' in bsc_main_features

    # Unsupported combination
    unsupported_features = get_supported_features('unknown', 'unknown')
    assert unsupported_features == set()


def test_feature_support_structure():
    """Test that the FEATURE_SUPPORT structure is properly formatted."""
    assert isinstance(FEATURE_SUPPORT, dict)

    for feature_name, combinations in FEATURE_SUPPORT.items():
        assert isinstance(feature_name, str)
        assert isinstance(combinations, set)

        for combination in combinations:
            assert isinstance(combination, tuple)
            assert len(combination) == 2
            scanner_id, network = combination
            assert isinstance(scanner_id, str)
            assert isinstance(network, str)


def test_get_supported_scanners_returns_copy():
    """Test that get_supported_scanners returns a copy, not the original set."""
    original_scanners = get_supported_scanners('gas_estimate')
    modified_scanners = get_supported_scanners('gas_estimate')

    # Modify the returned set
    modified_scanners.add(('fake', 'network'))

    # Original should be unchanged
    assert original_scanners != modified_scanners
    assert ('fake', 'network') not in original_scanners


def test_capabilities_overview_facade_structure():
    overview = get_capabilities_overview()
    assert isinstance(overview, dict)
    assert 'features' in overview and 'scanners' in overview

    # features is a mapping of feature -> set of (scanner, network)
    features = overview['features']
    assert isinstance(features, dict)
    # must include at least the known features
    assert 'gas_oracle' in features
    assert isinstance(features['gas_oracle'], set)

    # scanners is configuration metadata
    scanners = overview['scanners']
    assert isinstance(scanners, dict)
    assert 'eth' in scanners
    eth_meta = scanners['eth']
    assert 'name' in eth_meta and 'domain' in eth_meta and 'networks' in eth_meta
