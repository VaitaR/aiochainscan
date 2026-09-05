"""Shared JSON type aliases.

Root-level because every layer needs them: ``core``, ``services`` and the
scanners all speak in parsed-JSON dicts, and a home inside any one layer
would make the layering contracts in ``pyproject.toml`` false for the others.
"""

from __future__ import annotations

from typing import Any

JSONDict = dict[str, Any]
JSONList = list[JSONDict]
