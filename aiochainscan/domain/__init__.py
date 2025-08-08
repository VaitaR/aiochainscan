"""Domain layer: pure entities and value objects.

This package intentionally contains only pure, dependency-free code.
"""

from .models import Address, BlockNumber, TxHash

__all__ = [
    'Address',
    'BlockNumber',
    'TxHash',
]
