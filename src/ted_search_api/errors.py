"""Typed exceptions for the TED Search API client.

The TED API returns richly structured errors for 400 Bad Request responses
(unknown field names, syntax errors with line/column, invalid iteration
tokens, etc.). We surface those structured details on `TedQueryError`
rather than collapsing them into a generic exception.
"""

from __future__ import annotations

from typing import Any


class TedAPIError(Exception):
    """Base class for all errors originating from the TED Search API."""


class TedHTTPError(TedAPIError):
    """Raised when the API responds with a non-2xx status that is not a
    structured query/validation error (e.g. 5xx, network error)."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"TED API returned HTTP {status_code}: {body[:300]}")
        self.status_code = status_code
        self.body = body


class TedQueryError(TedAPIError):
    """Raised on 400 Bad Request. Carries the API's structured error payload.

    Inspect `.payload` (the raw JSON dict) or the convenience attributes
    (`.error_type`, `.field_name`, `.location`) to recover programmatically.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        # The API nests structured details under `error`, with the human
        # message at the top level. Tolerate both shapes defensively.
        raw_inner = payload.get("error")
        inner: dict[str, Any] = raw_inner if isinstance(raw_inner, dict) else {}
        self.error_type: str | None = inner.get("type") or payload.get("type")
        self.field_name: str | None = inner.get("fieldName") or payload.get("fieldName")
        self.location: dict[str, Any] | None = (
            inner.get("location") or payload.get("location")
        )
        msg = payload.get("message") or self.error_type or "TED query error"
        if self.field_name:
            msg = f"{msg} (field={self.field_name})"
        if self.location:
            msg = f"{msg} at {self.location}"
        super().__init__(msg)
