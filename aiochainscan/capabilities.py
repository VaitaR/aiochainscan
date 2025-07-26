"""
Feature capabilities matrix for different blockchain scanners and networks.

This module defines which features are supported by which scanner/network combinations.
"""

# Type aliases for better readability
ScannerNetwork = tuple[str, str]  # (scanner_id, network)
FeatureName = str

# Feature support matrix: feature_name -> set of (scanner_id, network) combinations
FEATURE_SUPPORT: dict[FeatureName, set[ScannerNetwork]] = {
    # Gas estimate is only supported on Ethereum mainnet
    'gas_estimate': {
        ('eth', 'main'),
    },
    # Gas oracle is supported on most networks
    'gas_oracle': {
        ('eth', 'main'),
        ('eth', 'sepolia'),
        ('bsc', 'main'),
        ('polygon', 'main'),
        ('arbitrum', 'main'),
        ('base', 'main'),
        ('optimism', 'main'),
    },
}


def is_feature_supported(feature: FeatureName, scanner_id: str, network: str) -> bool:
    """
    Check if a feature is supported for a given scanner and network combination.

    Args:
        feature: Name of the feature to check
        scanner_id: Scanner identifier (e.g., 'eth', 'bsc')
        network: Network name (e.g., 'main', 'sepolia')

    Returns:
        True if the feature is supported, False otherwise
    """
    supported_combinations = FEATURE_SUPPORT.get(feature, set())
    return (scanner_id, network) in supported_combinations


def get_supported_scanners(feature: FeatureName) -> set[ScannerNetwork]:
    """
    Get all scanner/network combinations that support a given feature.

    Args:
        feature: Name of the feature

    Returns:
        Set of (scanner_id, network) tuples that support the feature
    """
    return FEATURE_SUPPORT.get(feature, set()).copy()


def get_supported_features(scanner_id: str, network: str) -> set[FeatureName]:
    """
    Get all features supported by a given scanner/network combination.

    Args:
        scanner_id: Scanner identifier
        network: Network name

    Returns:
        Set of feature names supported by the scanner/network
    """
    target = (scanner_id, network)
    return {feature for feature, combinations in FEATURE_SUPPORT.items() if target in combinations}
