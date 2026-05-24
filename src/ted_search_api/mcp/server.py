"""MCP server exposing TED Search as a single `search_notices` tool.

Designed to be wired into any MCP-compatible client (Claude Code,
Claude Desktop, etc.). Communicates over stdio by default.

Claude Code config snippet (e.g. in ~/.claude/mcp_servers.json):

    {
      "mcpServers": {
        "ted-search": {
          "command": "uv",
          "args": ["--directory", "/path/to/TED-Search-API", "run", "ted-search-mcp"]
        }
      }
    }

Then call the tool from a conversation:
    > Use the ted-search MCP to find recent French tenders.

The tool returns a compact JSON summary tuned for LLM consumption: each
notice is reduced to id / date / title / buyer country / buyer name, and
the response includes `total_matches`, `has_more`, and `next_page` so
the assistant can decide whether to call again.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ted_search_api.client import TedSearchClient
from ted_search_api.errors import TedAPIError
from ted_search_api.fields import PRESET_SUMMARY
from ted_search_api.models import SearchResponse

mcp = FastMCP("ted-search")

MAX_LIMIT = 50
"""Hard cap on `limit` for MCP callers. The raw API supports 250 per page
but that overwhelms most LLM context windows; 50 is a more useful chunk
for an assistant deciding whether to paginate."""

Scope = Literal["LATEST", "ACTIVE", "ALL"]


@mcp.tool()
async def search_notices(
    query: str,
    limit: int = 10,
    scope: Scope = "ACTIVE",
    page: int = 1,
) -> dict[str, Any]:
    """Search the EU TED (Tenders Electronic Daily) procurement notices.

    Arguments
    ---------
    query : str
        Expert-search DSL query. Examples:
          - "publication-date >= 20260501"
          - "publication-date >= 20260501 AND organisation-country-buyer = \\"FRA\\""
          - "classification-cpv = \\"45000000\\""
        Important: the DSL does NOT support relative-date functions like
        today(-7day); use literal YYYYMMDD strings instead.
        Reference: https://ted.europa.eu/en/search/expert-search
    limit : int
        Number of notices to return (1-50). Default 10.
    scope : "LATEST" | "ACTIVE" | "ALL"
        ACTIVE returns only currently open tenders (default). LATEST
        restricts to the most recent OJ S release. ALL includes
        historical notices.
    page : int
        1-based page number (default 1). Use the returned `next_page`
        for subsequent calls when `has_more` is true.

    Returns
    -------
    dict
        {
          "total_matches": int,       # total matches for the query
          "returned":      int,       # how many notices in this response
          "page":          int,       # the page we returned
          "next_page":     int | None,
          "has_more":      bool,
          "notices": [
            {
              "id":             str,
              "publication_date": str,
              "title":          str | None,
              "buyer_country":  str | None,
              "buyer_name":     str | None,
              "cpv_codes":      list[str],
            },
            ...
          ]
        }
    """
    limit = max(1, min(limit, MAX_LIMIT))
    try:
        async with TedSearchClient() as ted:
            result = await ted.search(
                query,
                fields=PRESET_SUMMARY,
                limit=limit,
                scope=scope,
                page=page,
            )
    except TedAPIError as e:
        return {
            "error": str(e),
            "error_type": type(e).__name__,
        }

    return summarise(result, page=page, limit=limit)


def summarise(
    result: SearchResponse, *, page: int, limit: int
) -> dict[str, Any]:
    """Reduce a `SearchResponse` to the compact LLM-friendly shape."""
    notices = [_compact(n) for n in result.notices]
    consumed = page * limit
    has_more = consumed < result.totalNoticeCount and consumed < 15000
    return {
        "total_matches": result.totalNoticeCount,
        "returned": len(notices),
        "page": page,
        "next_page": page + 1 if has_more else None,
        "has_more": has_more,
        "notices": notices,
    }


def _compact(notice: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": notice.get("notice-identifier"),
        "publication_date": notice.get("publication-date"),
        "title": _flatten(notice.get("title-proc")),
        "buyer_country": _flatten(notice.get("organisation-country-buyer")),
        "buyer_name": _flatten(notice.get("buyer-name")),
        "cpv_codes": _as_list(notice.get("classification-cpv")),
    }


def _flatten(value: object) -> str | None:
    """Collapse multilingual / list-wrapped fields to a single string.

    Mirrors `ted_search_api.cli._flatten`. Kept local so the MCP module
    has no dependency on the CLI subpackage.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return _flatten(value[0]) if value else None
    if isinstance(value, dict):
        if not value:
            return None
        chosen = value.get("eng") or value.get("ENG") or next(iter(value.values()))
        return _flatten(chosen)
    return str(value)


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return sorted({str(v) for v in value})
    if value is None:
        return []
    return [str(value)]


def main() -> None:
    """Console script entrypoint for `ted-search-mcp`. Runs over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
