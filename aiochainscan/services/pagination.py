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


def decode_rest_cursor(cursor: str | None) -> tuple[int | None, int | None]:
    """Decode opaque cursor back into (page, offset)."""

    if not cursor:
        return None, None
    qs = parse_qs(cursor, keep_blank_values=False)
    page = int(qs['page'][0]) if 'page' in qs and qs['page'] else None
    offset = int(qs['offset'][0]) if 'offset' in qs and qs['offset'] else None
    return page, offset
