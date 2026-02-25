from __future__ import annotations

from urllib.parse import parse_qs, urlencode


def encode_rest_cursor(*, page: int | None, offset: int | None) -> str | None:
    """Encode page/offset into an opaque cursor string.

    Returns None when both values are None.
    """

    if page is None and offset is None:
        return None
    params: dict[str, str] = {}
    if page is not None:
        params['page'] = str(page)
    if offset is not None:
        params['offset'] = str(offset)
    return urlencode(params)


def _safe_int(values: list[str]) -> int | None:
    """Safely parse the first element of a list to int, returning None on failure."""
    try:
        return int(values[0])
    except (IndexError, ValueError, TypeError):
        return None


def decode_rest_cursor(cursor: str | None) -> tuple[int | None, int | None]:
    """Decode opaque cursor back into (page, offset)."""

    if not cursor:
        return None, None
    qs = parse_qs(cursor, keep_blank_values=False)
    page = _safe_int(qs.get('page', []))
    offset = _safe_int(qs.get('offset', []))
    return page, offset
