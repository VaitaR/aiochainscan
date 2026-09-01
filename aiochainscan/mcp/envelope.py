"""Standardized MCP tool-response envelope.

Every MCP tool answers with a :class:`ToolResponse` instead of a bare string:
structured ``data`` for programmatic use, ``notes`` explaining limits and
caveats, ``instructions`` bridging to the next tool call, optional
``pagination`` with an opaque cursor and a ready-to-use ``next_call``, and a
compact ``content_text`` summary for LLM clients that only read text.

This module deliberately has no ``mcp`` dependency: the tool layer is
testable offline and the FastMCP wiring (``aiochainscan.mcp.server``) only
converts envelopes into MCP content blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    'DEFAULT_PAGE_SIZE',
    'MAX_PAGE_SIZE',
    'MIN_PAGE_SIZE',
    'STRING_TRUNCATION_LIMIT',
    'NextCall',
    'Pagination',
    'ToolResponse',
    'build_tool_response',
    'clamp_page_size',
    'format_units',
    'truncate_long_strings',
]

DEFAULT_PAGE_SIZE = 50
"""Default items-per-page for paginated MCP tools."""

MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 50
"""Hard cap on items per response — the LLM-context protection budget."""

STRING_TRUNCATION_LIMIT = 512
"""Longest string kept verbatim inside ``data`` before flagging truncation."""


@dataclass
class NextCall:
    """Ready-to-execute follow-up call for the next page."""

    tool: str
    params: dict[str, Any]


@dataclass
class Pagination:
    """Pagination block: what was shown and how to continue."""

    has_more: bool
    items_shown: int
    next_cursor: str | None = None
    next_call: NextCall | None = None
    total: int | None = None
    """Total items in the full collection, when the scanner can tell."""

    def to_payload(self) -> dict[str, Any]:
        return {
            'has_more': self.has_more,
            'items_shown': self.items_shown,
            'next_cursor': self.next_cursor,
            'next_call': None
            if self.next_call is None
            else {'tool': self.next_call.tool, 'params': self.next_call.params},
            'total': self.total,
        }


@dataclass
class ToolResponse:
    """The standardized envelope every MCP tool returns."""

    data: Any
    notes: list[str] | None = None
    instructions: list[str] | None = None
    pagination: Pagination | None = None
    content_text: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """JSON-able structured payload (``content_text`` stays text-only)."""
        return {
            'data': self.data,
            'notes': self.notes,
            'instructions': self.instructions,
            'pagination': None if self.pagination is None else self.pagination.to_payload(),
        }


def build_tool_response(
    data: Any,
    notes: list[str] | None = None,
    instructions: list[str] | None = None,
    pagination: Pagination | None = None,
    content_text: str | None = None,
) -> ToolResponse:
    """Assemble a :class:`ToolResponse`, auto-appending pagination guidance.

    When ``pagination`` carries a ``next_call``, two instructions are appended
    so the agent cannot miss that more data is one call away (mirrors the
    Blockscout MCP contract).
    """
    final_instructions: list[str] | None = instructions

    if pagination is not None and pagination.next_call is not None:
        bridged = list(instructions) if instructions is not None else []
        bridged.append('MORE DATA AVAILABLE: use pagination.next_call to fetch the next page.')
        bridged.append(
            'Keep calling subsequent pages while pagination.has_more is true '
            'if you need comprehensive results.'
        )
        final_instructions = bridged

    return ToolResponse(
        data=data,
        notes=notes,
        instructions=final_instructions,
        pagination=pagination,
        content_text=content_text,
    )


def clamp_page_size(limit: int | None) -> int:
    """Clamp a requested page size into ``[MIN_PAGE_SIZE, MAX_PAGE_SIZE]``."""
    if limit is None:
        return DEFAULT_PAGE_SIZE
    return max(MIN_PAGE_SIZE, min(MAX_PAGE_SIZE, int(limit)))


def truncate_long_strings(data: Any, limit: int = STRING_TRUNCATION_LIMIT) -> tuple[Any, bool]:
    """Recursively replace over-long strings with a flagged sample.

    Returns the processed structure and whether anything was truncated. Long
    values become ``{'value_sample': <first N chars>, 'value_truncated': True}``
    so agents can see both the preview and the fact that data was cut.
    """
    if isinstance(data, str):
        if len(data) > limit:
            return {'value_sample': data[:limit], 'value_truncated': True}, True
        return data, False
    if isinstance(data, list):
        processed: list[Any] = []
        was_truncated = False
        for item in data:
            processed_item, item_truncated = truncate_long_strings(item, limit)
            processed.append(processed_item)
            was_truncated = was_truncated or item_truncated
        return processed, was_truncated
    if isinstance(data, tuple):
        processed_items: list[Any] = []
        tuple_truncated = False
        for item in data:
            processed_item, item_truncated = truncate_long_strings(item, limit)
            processed_items.append(processed_item)
            tuple_truncated = tuple_truncated or item_truncated
        return tuple(processed_items), tuple_truncated
    if isinstance(data, dict):
        processed_dict: dict[Any, Any] = {}
        dict_truncated = False
        for key, value in data.items():
            processed_value, value_truncated = truncate_long_strings(value, limit)
            processed_dict[key] = processed_value
            dict_truncated = dict_truncated or value_truncated
        return processed_dict, dict_truncated
    return data, False


def format_units(value: str | int, decimals: int = 18) -> str:
    """Format a raw-unit integer amount as a lossless decimal string.

    Pure integer math — never float, so Wei-scale precision survives. Values
    that are not valid integers are returned unchanged (explorers already
    answer some balances as pre-formatted strings).
    """
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return str(value)
    if decimals < 0:
        return str(value)
    scale = 10**decimals
    whole, remainder = divmod(amount, scale)
    if remainder == 0:
        return str(whole)
    fraction = str(remainder).rjust(decimals, '0').rstrip('0')
    return f'{whole}.{fraction}'
