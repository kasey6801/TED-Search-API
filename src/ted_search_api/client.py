"""Async TED Search API client.

Single endpoint wrapper: `TedSearchClient.search(...)` calls
`POST /v3/notices/search` and returns a typed `SearchResponse`.

Usage:
    async with TedSearchClient() as ted:
        result = await ted.search("publication-date >= today(-7day)", limit=5)
        print(result.totalNoticeCount, "matches")
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx

from ted_search_api.errors import TedHTTPError, TedQueryError
from ted_search_api.models import PaginationMode, Scope, SearchRequest, SearchResponse

DEFAULT_BASE_URL = "https://api.ted.europa.eu/"
DEFAULT_TIMEOUT = 30.0
DEFAULT_USER_AGENT = "ted-search-api/0.0.1 (+https://github.com/kasey6801/TED-Search-API)"


class TedSearchClient:
    """Async client for the public TED Search API.

    The client wraps an `httpx.AsyncClient`. Use it as an async context
    manager to ensure the underlying connection pool is closed:

        async with TedSearchClient() as ted:
            await ted.search(...)

    Or, if you manage the lifecycle yourself, call `await client.aclose()`.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def search(
        self,
        query: str,
        *,
        fields: list[str] | None = None,
        page: int = 1,
        limit: int = 10,
        scope: Scope = "ALL",
        pagination_mode: PaginationMode = "PAGE_NUMBER",
        iteration_next_token: str | None = None,
        only_latest_versions: bool = False,
        check_query_syntax: bool = False,
    ) -> SearchResponse:
        """Call `POST /v3/notices/search`.

        Raises:
            TedQueryError: 400 Bad Request with a structured payload.
            TedHTTPError:  any other non-2xx response.
        """
        req = SearchRequest(
            query=query,
            fields=fields,
            page=page,
            limit=limit,
            scope=scope,
            paginationMode=pagination_mode,
            iterationNextToken=iteration_next_token,
            onlyLatestVersions=only_latest_versions,
            checkQuerySyntax=check_query_syntax,
        )
        payload = req.model_dump(exclude_none=True)
        try:
            r = await self._http.post("/v3/notices/search", json=payload)
        except httpx.HTTPError as e:
            raise TedHTTPError(0, f"network error: {e}") from e

        if r.status_code == 400:
            raise TedQueryError(_safe_json(r))
        if r.status_code >= 400:
            raise TedHTTPError(r.status_code, r.text)

        return SearchResponse.model_validate(_safe_json(r))


def _safe_json(r: httpx.Response) -> dict[str, Any]:
    try:
        data = r.json()
    except ValueError:
        return {"raw": r.text}
    if isinstance(data, dict):
        return data
    return {"raw": data}
