"""Domain layer: pure entities and value objects.

This package intentionally contains only pure, dependency-free code.
"""

from .contract import DecodedEvent, DecodedTransaction, SmartContract
from .models import Address, BlockNumber, TxHash

__all__ = [
    'Address',
    'BlockNumber',
    'TxHash',
    'SmartContract',
    'DecodedEvent',
    'DecodedTransaction',
]
