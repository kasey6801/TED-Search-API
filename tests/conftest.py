"""Pytest configuration shared across the test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    """Default VCR settings.

    `match_on` keeps the cassette deterministic. We never record auth
    headers because TED is keyless, but we strip them defensively.
    """
    return {
        "match_on": ["method", "scheme", "host", "path", "body"],
        "filter_headers": ["authorization", "user-agent"],
        "record_mode": "once",
    }
