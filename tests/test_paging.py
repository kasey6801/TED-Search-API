"""Unit tests for the paging iterator (no HTTP)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from ted_search_api import TedSearchClient
from ted_search_api.paging import iter_notices


class _MockTransport(httpx.AsyncBaseTransport):
    """Fake transport that returns canned pages."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        idx = min(self.calls, len(self.pages) - 1)
        self.calls += 1
        return httpx.Response(200, json=self.pages[idx], request=request)


@pytest.fixture
def two_page_transport() -> _MockTransport:
    return _MockTransport(
        pages=[
            {
                "notices": [{"notice-identifier": "n1"}, {"notice-identifier": "n2"}],
                "totalNoticeCount": 3,
                "iterationNextToken": None,
                "timedOut": False,
            },
            {
                "notices": [{"notice-identifier": "n3"}],
                "totalNoticeCount": 3,
                "iterationNextToken": None,
                "timedOut": False,
            },
        ]
    )


async def test_iter_notices_walks_pages(two_page_transport: _MockTransport) -> None:
    async with TedSearchClient(transport=two_page_transport) as ted:
        ids = [n["notice-identifier"] async for n in iter_notices(ted, "q", limit=2)]
    assert ids == ["n1", "n2", "n3"]
    assert two_page_transport.calls == 2


async def test_iter_notices_respects_max_notices(
    two_page_transport: _MockTransport,
) -> None:
    async with TedSearchClient(transport=two_page_transport) as ted:
        ids = [
            n["notice-identifier"]
            async for n in iter_notices(ted, "q", limit=2, max_notices=1)
        ]
    assert ids == ["n1"]
    # we should have stopped after a single page
    assert two_page_transport.calls == 1
