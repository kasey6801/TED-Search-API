"""Tests for the MCP server's `search_notices` tool.

We test the tool function directly rather than booting a stdio loop:
- `summarise()` is pure and easy to cover with canned `SearchResponse` data.
- The `search_notices` tool is monkey-patched at the `TedSearchClient`
  layer so no real HTTP is made.
"""

from __future__ import annotations

from typing import Any

import pytest

from ted_search_api.errors import TedQueryError
from ted_search_api.mcp import server as srv
from ted_search_api.models import SearchResponse


def _fake_response(*, total: int, notices: list[dict[str, Any]]) -> SearchResponse:
    return SearchResponse(
        notices=notices,
        totalNoticeCount=total,
        iterationNextToken=None,
        timedOut=False,
    )


SAMPLE_NOTICE: dict[str, Any] = {
    "notice-identifier": "abc-123",
    "publication-date": "2026-05-04+02:00",
    "title-proc": {"eng": "Cycling helmets"},
    "organisation-country-buyer": ["FRA"],
    "buyer-name": {"fra": ["Ville de Paris"]},
    "classification-cpv": ["18443320", "18443320"],
}


def test_summarise_compacts_a_notice() -> None:
    summary = srv.summarise(
        _fake_response(total=1, notices=[SAMPLE_NOTICE]), page=1, limit=10
    )
    assert summary["total_matches"] == 1
    assert summary["returned"] == 1
    assert summary["page"] == 1
    assert summary["has_more"] is False
    assert summary["next_page"] is None
    assert summary["validation_warnings"] == 0

    n = summary["notices"][0]
    assert n["id"] == "abc-123"
    assert n["publication_date"] == "2026-05-04+02:00"
    assert n["title"] == "Cycling helmets"
    assert n["buyer_country"] == "FRA"
    assert n["buyer_name"] == "Ville de Paris"
    assert n["cpv_codes"] == ["18443320"]  # de-duplicated


def test_summarise_counts_validation_warnings_on_malformed_notice() -> None:
    """A notice with a broken `publication-date` should still appear in
    the compact output (so callers see *something*), but contribute one
    to the `validation_warnings` counter so the LLM knows to flag."""
    broken = {**SAMPLE_NOTICE, "publication-date": "not-a-date"}
    summary = srv.summarise(
        _fake_response(total=2, notices=[SAMPLE_NOTICE, broken]),
        page=1,
        limit=10,
    )
    assert summary["validation_warnings"] == 1
    assert summary["returned"] == 2  # both still surfaced


def test_summarise_signals_has_more_when_total_exceeds_consumed() -> None:
    summary = srv.summarise(
        _fake_response(total=42, notices=[SAMPLE_NOTICE] * 10),
        page=1,
        limit=10,
    )
    assert summary["has_more"] is True
    assert summary["next_page"] == 2


def test_summarise_clamps_has_more_at_15000_cap() -> None:
    # PAGE_NUMBER mode is capped server-side at 15000 results.
    summary = srv.summarise(
        _fake_response(total=999_999, notices=[SAMPLE_NOTICE] * 50),
        page=300,  # 300 * 50 == 15000 -> exactly at the cap
        limit=50,
    )
    assert summary["has_more"] is False
    assert summary["next_page"] is None


async def test_search_notices_tool_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_search(self: object, query: str, **kwargs: Any) -> SearchResponse:
        captured["query"] = query
        captured["kwargs"] = kwargs
        return _fake_response(total=2, notices=[SAMPLE_NOTICE, SAMPLE_NOTICE])

    monkeypatch.setattr(
        "ted_search_api.mcp.server.TedSearchClient.search", fake_search
    )

    out = await srv.search_notices("publication-date >= 20260501", limit=5)

    assert captured["query"] == "publication-date >= 20260501"
    assert captured["kwargs"]["limit"] == 5
    assert captured["kwargs"]["scope"] == "ACTIVE"
    assert out["total_matches"] == 2
    assert len(out["notices"]) == 2


async def test_search_notices_tool_caps_limit_at_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_search(self: object, query: str, **kwargs: Any) -> SearchResponse:
        captured["kwargs"] = kwargs
        return _fake_response(total=0, notices=[])

    monkeypatch.setattr(
        "ted_search_api.mcp.server.TedSearchClient.search", fake_search
    )

    await srv.search_notices("q", limit=999)
    assert captured["kwargs"]["limit"] == srv.MAX_LIMIT


async def test_search_notices_tool_returns_error_dict_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(self: object, query: str, **kwargs: Any) -> SearchResponse:
        raise TedQueryError({"message": "boom", "error": {"type": "QUERY_SYNTAX_ERROR"}})

    monkeypatch.setattr(
        "ted_search_api.mcp.server.TedSearchClient.search", fake_search
    )

    out = await srv.search_notices("garbage")
    assert "error" in out
    assert out["error_type"] == "TedQueryError"
