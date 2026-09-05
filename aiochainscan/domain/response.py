"""Envelope→items coercion for parsed provider responses.

Pure and dependency-free, and in ``domain`` because both layers that need it
sit above: ``Scanner._coerce_items`` (scanners) and
``services.pagination.normalize_items`` (services, which must not import
scanners or core). One coercion contract, maintained once.
"""

from __future__ import annotations

from typing import Any


def coerce_response_items(response: Any) -> list[dict[str, Any]]:
    """Coerce a parsed API response into a list of item dicts.

    Accepts the shapes explorers actually return: a plain list, an envelope
    dict with an ``'items'`` key, or anything else (treated as no data).
    """
    if isinstance(response, list):
        return list(response)
    if isinstance(response, dict):
        items = response.get('items')
        return list(items) if items else []
    return []
