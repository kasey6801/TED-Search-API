"""Pydantic models for the TED Search API request and response.

Mirrors `PublicExpertSearchRequestV1` and `ExpertSearchResponse` from the
live OpenAPI spec at https://ted.europa.eu/docs/v3 .

Notes:
- We keep `fields` as `list[str]` rather than a closed `Literal[...]` of
  the ~1830 eForms field names: the enum evolves as eForms versions ship,
  and the server already validates and returns a precise error.
- Individual notice objects are typed as `dict[str, Any]` because their
  shape varies with which `fields` were requested. Strong typing per-
  notice would require modelling all 1830 fields, which we deliberately
  avoid (see DESIGN.md section 2.5).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Scope = Literal["LATEST", "ACTIVE", "ALL"]
PaginationMode = Literal["PAGE_NUMBER", "ITERATION"]


class SearchRequest(BaseModel):
    """Request body for POST /v3/notices/search."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Expert-search DSL query.")
    fields: list[str] | None = Field(
        default=None,
        description="Which notice fields to return. None = server defaults.",
    )
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=0, le=250)
    scope: Scope = "ALL"
    paginationMode: PaginationMode = "PAGE_NUMBER"
    iterationNextToken: str | None = None
    onlyLatestVersions: bool = False
    checkQuerySyntax: bool = False


class SearchResponse(BaseModel):
    """Response body for POST /v3/notices/search."""

    model_config = ConfigDict(extra="ignore")

    notices: list[dict[str, Any]] = Field(default_factory=list)
    totalNoticeCount: int = 0
    iterationNextToken: str | None = None
    timedOut: bool = False
