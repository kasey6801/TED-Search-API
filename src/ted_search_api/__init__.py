"""TED Search API client.

Public re-exports. Importers should prefer:

    from ted_search_api import TedSearchClient, SearchRequest, SearchResponse
"""

from ted_search_api.client import TedSearchClient
from ted_search_api.errors import (
    TedAPIError,
    TedHTTPError,
    TedQueryError,
)
from ted_search_api.fields import PRESET_SUMMARY
from ted_search_api.models import (
    NoticeSummary,
    PaginationMode,
    Scope,
    SearchRequest,
    SearchResponse,
    parse_notice_summary,
)

__all__ = [
    "PRESET_SUMMARY",
    "NoticeSummary",
    "PaginationMode",
    "Scope",
    "SearchRequest",
    "SearchResponse",
    "TedAPIError",
    "TedHTTPError",
    "TedQueryError",
    "TedSearchClient",
    "parse_notice_summary",
]

__version__ = "0.0.1"
