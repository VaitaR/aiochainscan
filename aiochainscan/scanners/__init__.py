"""
Scanner implementations for different blockchain explorers.

This module provides a unified interface for different blockchain scanner APIs
through the Scanner base class and registry system.
"""

from .base import Scanner

# Global scanner registry: (name, version) -> Scanner class
SCANNER_REGISTRY: dict[tuple[str, str], type[Scanner]] = {}


def register_scanner(scanner_class: type[Scanner]) -> type[Scanner]:
    """
    Decorator to register a scanner implementation.

    Args:
        scanner_class: Scanner class to register

    Returns:
        The same scanner class (for use as decorator)

    Example:
        @register_scanner
        class EtherscanV2(Scanner):
            name = "etherscan"
            version = "v2"
            ...
    """
    key = (scanner_class.name, scanner_class.version)
    if key in SCANNER_REGISTRY:
        raise ValueError(
            f'Scanner {scanner_class.name} v{scanner_class.version} already registered'
        )

    SCANNER_REGISTRY[key] = scanner_class
    return scanner_class


def get_scanner_class(name: str, version: str) -> type[Scanner]:
    """
    Get scanner class by name and version.

    Args:
        name: Scanner name (e.g., 'etherscan', 'oklink')
        version: Scanner version (e.g., 'v1', 'v2')

    Returns:
        Scanner class

    Raises:
        ValueError: If scanner not found
    """
    key = (name, version)
    if key not in SCANNER_REGISTRY:
        available = list(SCANNER_REGISTRY.keys())
        raise ValueError(f"Scanner '{name}' v{version} not found. Available: {available}")
    return SCANNER_REGISTRY[key]


def list_scanners() -> dict[tuple[str, str], type[Scanner]]:
    """
    Get all registered scanners.

    Returns:
        Dictionary mapping (name, version) to scanner classes
    """
    return dict(SCANNER_REGISTRY)


# Import scanner implementations to trigger registration
# This must be done after register_scanner is defined to avoid circular imports
from .basescan_v1 import BaseScanV1  # noqa: E402
from .blockscout_v1 import BlockScoutV1  # noqa: E402
from .etherscan_v2 import EtherscanV2  # noqa: E402
from .moralis_v1 import MoralisV1  # noqa: E402
from .routscan_v1 import RoutScanV1  # noqa: E402

__all__ = [
    'Scanner',
    'register_scanner',
    'get_scanner_class',
    'list_scanners',
    'EtherscanV2',
    'RoutScanV1',
    'BaseScanV1',
    'BlockScoutV1',
    'MoralisV1',
]
