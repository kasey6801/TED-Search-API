"""Async iteration helpers that hide the two pagination modes.

The TED Search API has two pagination modes:

- PAGE_NUMBER: increment `page` until `page * limit >= totalNoticeCount`.
  Capped server-side at 15 000 results.
- ITERATION:   pass back the `iterationNextToken` from the previous
  response. Unlimited, but tokens can expire.

`iter_notices()` picks PAGE_NUMBER by default and transparently iterates
pages, yielding individual notice dicts. Pass `mode="ITERATION"` for
result sets that would exceed 15 000.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ted_search_api.client import TedSearchClient
from ted_search_api.models import PaginationMode, Scope


async def iter_notices(
    client: TedSearchClient,
    query: str,
    *,
    fields: list[str] | None = None,
    limit: int = 100,
    scope: Scope = "ALL",
    mode: PaginationMode = "PAGE_NUMBER",
    max_notices: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield notices one at a time, advancing pages as needed.

    Stops when the server runs out of results, when `max_notices` is
    reached, or (PAGE_NUMBER mode only) when the 15 000-result cap is
    hit.
    """
    yielded = 0
    page = 1
    token: str | None = None

    while True:
        result = await client.search(
            query,
            fields=fields,
            page=page if mode == "PAGE_NUMBER" else 1,
            limit=limit,
            scope=scope,
            pagination_mode=mode,
            iteration_next_token=token,
        )

        for notice in result.notices:
            yield notice
            yielded += 1
            if max_notices is not None and yielded >= max_notices:
                return

        if not result.notices:
            return

        if mode == "PAGE_NUMBER":
            if page * limit >= result.totalNoticeCount or page * limit >= 15000:
                return
            page += 1
        else:
            if not result.iterationNextToken:
                return
            token = result.iterationNextToken
