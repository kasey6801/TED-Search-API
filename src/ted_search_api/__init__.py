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
    PaginationMode,
    Scope,
    SearchRequest,
    SearchResponse,
)

__all__ = [
    "PRESET_SUMMARY",
    "PaginationMode",
    "Scope",
    "SearchRequest",
    "SearchResponse",
    "TedAPIError",
    "TedHTTPError",
    "TedQueryError",
    "TedSearchClient",
]

__version__ = "0.0.1"
