"""Unit tests for `NoticeSummary` / `parse_notice_summary`.

These guard the drift-detection layer: the model must accept well-formed
notices, reject malformed values loudly, and silently ignore unknown
fields (so benign upstream additions don't trigger false alarms).
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from ted_search_api import NoticeSummary, parse_notice_summary

VALID_NOTICE = {
    "notice-identifier": "abc-123",
    "publication-date": "2026-05-04+02:00",
    "title-proc": {"eng": "Cycling helmets"},
    "buyer-name": {"fra": ["Ville de Paris"]},
    "organisation-country-buyer": ["FRA"],
    "classification-cpv": ["18443320"],
}


def test_valid_notice_parses() -> None:
    notice = NoticeSummary.model_validate(VALID_NOTICE)
    assert notice.notice_identifier == "abc-123"
    assert notice.publication_date.startswith("2026-05-04")
    assert notice.organisation_country_buyer == ["FRA"]
    assert notice.classification_cpv == ["18443320"]


def test_strict_validation_raises_on_malformed_date() -> None:
    bad = {**VALID_NOTICE, "publication-date": "May 4, 2026"}
    with pytest.raises(ValidationError):
        NoticeSummary.model_validate(bad)


def test_unknown_fields_silently_ignored() -> None:
    """`extra="ignore"` -- upstream may add fields without breaking us."""
    augmented = {**VALID_NOTICE, "brand-new-field-2027": "anything"}
    notice = NoticeSummary.model_validate(augmented)
    assert notice.notice_identifier == "abc-123"


def test_parse_notice_summary_returns_none_on_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bad = {**VALID_NOTICE, "notice-identifier": ""}  # min_length=1 violated
    with caplog.at_level(logging.WARNING, logger="ted_search_api.models"):
        result = parse_notice_summary(bad)
    assert result is None
    assert any(
        "validation failed" in r.message.lower() for r in caplog.records
    ), "expected a WARNING log; got none"


def test_parse_notice_summary_returns_model_on_success() -> None:
    result = parse_notice_summary(VALID_NOTICE)
    assert result is not None
    assert result.notice_identifier == "abc-123"
