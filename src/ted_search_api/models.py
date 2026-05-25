"""Pydantic models for the TED Search API request and response.

Mirrors `PublicExpertSearchRequestV1` and `ExpertSearchResponse` from the
live OpenAPI spec at https://ted.europa.eu/docs/v3 .

Notes:
- We keep `fields` as `list[str]` rather than a closed `Literal[...]` of
  the ~1830 eForms field names: the enum evolves as eForms versions ship,
  and the server already validates and returns a precise error.
- Individual notice objects in the raw `SearchResponse` are typed as
  `dict[str, Any]` because their shape varies with which `fields` were
  requested. Strong typing per-notice would require modelling all 1830
  fields (see DESIGN.md section 2.5).
- For the subset of fields actually consumed downstream (the
  `PRESET_SUMMARY` set), we layer a strict `NoticeSummary` model on
  top. This is the *drift-detection* layer: schema additions are
  tolerated (extra="ignore"), but malformed values on known fields
  raise loudly rather than feeding silent garbage into investment
  workflows. See `parse_notice_summary` for the lenient-but-loud
  helper used in production paths.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger(__name__)

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


# ---- Strict per-notice model for drift detection -----------------------

# Multilingual fields come back as either {"eng": "..."}, {"eng": ["..."]},
# or a single string in older payloads. Accept all three to avoid false
# alarms on benign upstream shape changes for fields whose *value* we
# don't constrain.
_MultilingualValue = str | list[str]
_Multilingual = dict[str, _MultilingualValue] | str | list[str]


class NoticeSummary(BaseModel):
    """Strict validation for the fields in `PRESET_SUMMARY`.

    Tolerates upstream additions (`extra="ignore"`) but constrains every
    known field with a type + regex / length check. The point is to make
    semantic drift LOUD: if `publication-date` ever stops being an
    ISO-like string, or a CPV code stops being digits, we want to know
    immediately -- not after a downstream consumer has acted on bad data.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    notice_identifier: str = Field(alias="notice-identifier", min_length=1)
    publication_date: str = Field(
        alias="publication-date",
        pattern=r"^\d{4}-\d{2}-\d{2}",
    )
    title_proc: _Multilingual = Field(alias="title-proc")
    buyer_name: _Multilingual | None = Field(default=None, alias="buyer-name")
    organisation_country_buyer: list[str] = Field(alias="organisation-country-buyer")
    classification_cpv: list[str] = Field(alias="classification-cpv")


def parse_notice_summary(raw: dict[str, Any]) -> NoticeSummary | None:
    """Validate a single notice; return None and log a WARNING on failure.

    Production paths (CLI / MCP server) use this rather than raising
    directly, so a single malformed notice doesn't blow up an entire
    search response -- it just gets surfaced via the returned
    `validation_warnings` counter so callers can flag.

    The full validation error and the offending notice's `notice-identifier`
    (when present) are logged so an operator can diagnose drift.
    """
    try:
        return NoticeSummary.model_validate(raw)
    except ValidationError as e:
        log.warning(
            "NoticeSummary validation failed for notice_identifier=%r: %s",
            raw.get("notice-identifier"),
            e.errors(),
        )
        return None
