"""End-to-end tests for `TedSearchClient`.

The HTTP tests are recorded with VCR (`pytest-recording`). The first run
hits the live API and saves a cassette under `tests/cassettes/`. Later
runs replay the cassette, so the suite is offline-safe and deterministic.

Re-record with: `uv run pytest --record-mode=rewrite`.
"""

from __future__ import annotations

import pytest

from ted_search_api import (
    PRESET_SUMMARY,
    TedQueryError,
    TedSearchClient,
)


@pytest.mark.vcr
async def test_search_returns_real_notices() -> None:
    """Happy path: a syntactically valid query returns notices."""
    async with TedSearchClient() as ted:
        result = await ted.search(
            "publication-date >= 20260501",
            fields=PRESET_SUMMARY,
            limit=3,
            scope="ACTIVE",
        )

    assert result.totalNoticeCount > 0
    assert 1 <= len(result.notices) <= 3
    first = result.notices[0]
    assert "notice-identifier" in first
    assert "publication-date" in first


@pytest.mark.vcr
async def test_query_syntax_error_is_structured() -> None:
    """A malformed query raises `TedQueryError` with structured details."""
    async with TedSearchClient() as ted:
        with pytest.raises(TedQueryError) as exc_info:
            await ted.search(
                "publication-date >= today(-7day)",
                fields=PRESET_SUMMARY,
                limit=1,
            )

    err = exc_info.value
    assert err.error_type is not None
    assert err.payload  # full server payload is preserved
