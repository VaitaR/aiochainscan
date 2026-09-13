"""
Scanner implementations for different blockchain explorers.

This module provides a unified interface for different blockchain scanner APIs
through the Scanner base class and registry system.
"""

from ..chain_registry import get_chain_name, list_supported_chains, resolve_scanner_target
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
        raise ValueError(f"Scanner '{name}' {version} not found. Available: {available}")
    return SCANNER_REGISTRY[key]


def list_scanners() -> dict[tuple[str, str], type[Scanner]]:
    """
    Get all registered scanners.

    Returns:
        Dictionary mapping (name, version) to scanner classes
    """
    return dict(SCANNER_REGISTRY)


def chains_served_by(scanner: str) -> list[str]:
    """Canonical chain names a client for ``scanner`` actually constructs on.

    The two construction gates as ONE query — the one the CLI's ``chains``
    listing, ``ChainscanClient.from_config`` and anything else that must not
    advertise an unconstructible chain all share:

    1. the registry must resolve the chain for this scanner
       (:func:`aiochainscan.chain_registry.resolve_scanner_target`), and
    2. the scanner class must declare the resulting scanner-dialect network
       (``supported_networks`` — the check the Scanner constructor itself
       applies).

    Gate 1 alone passes chains the BlockScout legs have no instance for,
    which is why the second gate exists. ``api_key=''`` keeps credential
    lookup out of it: this asks where a client can be constructed, not
    whether it is configured.

    Args:
        scanner: Public scanner name (e.g. ``'etherscan'``,
            ``'blockscout_v2'``). Unknown names fail exactly as walking the
            gates by hand would.

    Returns:
        Sorted canonical chain names.
    """
    served: list[str] = []
    for chain_id in list_supported_chains():
        try:
            target = resolve_scanner_target(scanner, chain_id, api_key='')
        except ValueError:
            continue
        scanner_class = get_scanner_class(target.scanner_name, target.scanner_version)
        if target.scanner_network not in scanner_class.supported_networks:
            continue
        served.append(get_chain_name(chain_id))
    return sorted(served)


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
    'chains_served_by',
    'scanners_serving_completely',
    'scanners_serving_block_range',
    'EtherscanV2',
    'BlockScoutV1',
    'BlockScoutV2Scanner',
    'NodeRealScanner',
]
