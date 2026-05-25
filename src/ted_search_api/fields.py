"""Curated field-name presets for the TED Search API.

The API accepts ~1830 eForms field IDs in the `fields` request parameter.
Listing them all here would be high-noise. Instead we ship a few small
named subsets for common use cases. Callers can always pass arbitrary
field-name lists if these presets don't fit.

Field-name reference: https://ted.europa.eu/en/search/expert-search
"""

from __future__ import annotations

PRESET_SUMMARY: list[str] = [
    "notice-identifier",
    "publication-date",
    "title-proc",
    "buyer-name",
    "organisation-country-buyer",
    "classification-cpv",
]
"""Minimal fields for a one-line summary of each notice -- useful for
search-result tables and LLM consumption."""

PRESET_BUYER_AND_VALUE: list[str] = [
    "notice-identifier",
    "publication-date",
    "title-proc",
    "buyer-name",
    "organisation-country-buyer",
    "classification-cpv",
    "total-value",
    "total-value-cur",
]
"""Summary + the headline contract value (when present).

`total-value` / `total-value-cur` are the eForms field IDs for the
overall contract total. Other value-related fields (`tender-value`,
`estimated-value-*`, `framework-*-value-*`) exist but cover different
semantics -- see the OpenAPI spec for the full ~50-field value family."""
