"""
Scanner implementations for different blockchain explorers.

This module provides a unified interface for different blockchain scanner APIs
through the Scanner base class and registry system.
"""

from ..domain.method import Method
from .base import Scanner, spec_declares_block_range

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
        name: Scanner name (e.g., 'etherscan', 'blockscout')
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


def scanners_serving_completely(method: Method) -> tuple[str, ...]:
    """Labels of registered scanners that can serve ``method`` in full.

    "In full" means the scanner declares ``method`` and no result window
    bounds it (``Scanner.result_window_for(method) is None``): it paginates by
    a server-issued cursor that runs to exhaustion, so no cap can truncate it.
    The question is per-method, not per-scanner: a scanner may cap most
    endpoints and still serve one to exhaustion (BlockScout V1's holder list),
    and reading the scanner-wide window alone would hide that provider from
    the remedy this function computes.

    Args:
        method: Logical method to look for.

    Returns:
        Sorted ``'name/version'`` labels; empty when none qualifies.
    """
    return tuple(
        sorted(
            f'{name}/{version}'
            for (name, version), scanner in SCANNER_REGISTRY.items()
            if scanner.result_window_for(method) is None and method in scanner.SPECS
        )
    )


def scanners_serving_block_range(method: Method) -> tuple[str, ...]:
    """Labels of registered scanners that declare a block range for ``method``.

    Derived from ``Scanner.supports_block_range`` (spec ``param_map``, never
    scanner names). Used to name working alternatives when the configured
    provider would silently drop a bounded block range.

    Args:
        method: Logical method to look for.

    Returns:
        Sorted ``'name/version'`` labels; empty when none qualifies.
    """
    return tuple(
        sorted(
            f'{name}/{version}'
            for (name, version), scanner in SCANNER_REGISTRY.items()
            if method in scanner.SPECS and spec_declares_block_range(scanner.SPECS[method])
        )
    )


# Import scanner implementations to trigger registration
# This must be done after register_scanner is defined to avoid circular imports
from .blockscout_v1 import BlockScoutV1  # noqa: E402
from .blockscout_v2 import BlockScoutV2Scanner  # noqa: E402
from .etherscan_v2 import EtherscanV2  # noqa: E402
from .nodereal import NodeRealScanner  # noqa: E402

__all__ = [
    'Scanner',
    'register_scanner',
    'get_scanner_class',
    'list_scanners',
    'scanners_serving_completely',
    'scanners_serving_block_range',
    'EtherscanV2',
    'BlockScoutV1',
    'BlockScoutV2Scanner',
    'NodeRealScanner',
]
