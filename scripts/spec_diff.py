"""Tier-1 drift detector: diff live TED OpenAPI spec against pinned snapshot.

Fetches the current spec, compares it structurally against the committed
fixture at ``tests/fixtures/ted_openapi_v3.snapshot.json``, and prints
any divergence. Exits 0 on no drift, 1 on any drift (suitable for cron
or a GitHub Actions schedule).

A diff doesn't necessarily mean breakage -- many additions are benign.
The signal is: drift detected -> human review required.

Notes
-----
- Uses the ``tedweb.api.ted.europa.eu`` mirror because the canonical
  ``ted.europa.eu`` host sits behind an AWS WAF challenge that rejects
  non-browser clients (verified 2026-05-25). The mirror serves the same
  spec without the challenge.
- Walks the JSON tree into a sorted list of ``(path, leaf_value)`` pairs
  and compares as sets -- catches added / removed / changed paths
  cleanly with no external dependency.

Run with::

    uv run python scripts/spec_diff.py
    uv run python scripts/spec_diff.py --update     # re-pin after review
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

SPEC_URL = "https://tedweb.api.ted.europa.eu/docs/v3"
SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "ted_openapi_v3.snapshot.json"
)


def _walk(node: Any, path: str = "$") -> Iterator[tuple[str, str]]:
    """Yield (json-path, repr-of-leaf) for every leaf in a JSON tree.

    Lists are walked by index, dicts by sorted key, so output is
    deterministic regardless of input ordering.
    """
    if isinstance(node, dict):
        for k in sorted(node):
            yield from _walk(node[k], f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield (path, repr(node))


def _fetch_live(attempts: int = 3) -> dict[str, Any]:
    """Fetch the spec, retrying on transient non-JSON responses.

    The mirror occasionally serves a 202 with an empty body (CDN cache
    miss / WAF challenge bleed-through). A handful of retries with a
    short backoff smooths over these without masking a real outage.
    """
    import time

    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        r = httpx.get(
            SPEC_URL,
            timeout=30.0,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        try:
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            last_err = e
            print(
                f"[spec_diff] fetch attempt {attempt}/{attempts} failed: "
                f"status={r.status_code} ct={r.headers.get('content-type')!r} "
                f"err={e!r}",
                file=sys.stderr,
            )
            if attempt < attempts:
                time.sleep(2 * attempt)
    assert last_err is not None
    raise last_err


def _diff(pinned: dict[str, Any], live: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    pinned_pairs = dict(_walk(pinned))
    live_pairs = dict(_walk(live))
    pinned_paths = set(pinned_pairs)
    live_paths = set(live_pairs)
    added = sorted(live_paths - pinned_paths)
    removed = sorted(pinned_paths - live_paths)
    changed = sorted(
        p for p in pinned_paths & live_paths if pinned_pairs[p] != live_pairs[p]
    )
    return added, removed, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="Overwrite the pinned snapshot with the current live spec.",
    )
    args = parser.parse_args()

    live = _fetch_live()

    if args.update:
        SNAPSHOT_PATH.write_text(
            json.dumps(live, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )
        print(f"[spec_diff] snapshot updated: {SNAPSHOT_PATH}")
        return 0

    pinned = json.loads(SNAPSHOT_PATH.read_text())
    added, removed, changed = _diff(pinned, live)

    if not (added or removed or changed):
        print("[spec_diff] no drift detected")
        return 0

    print(f"[spec_diff] drift detected: +{len(added)} -{len(removed)} ~{len(changed)}")
    if added:
        print("\n--- added ---")
        for p in added[:50]:
            print(f"  + {p}")
        if len(added) > 50:
            print(f"  ... and {len(added) - 50} more")
    if removed:
        print("\n--- removed ---")
        for p in removed[:50]:
            print(f"  - {p}")
        if len(removed) > 50:
            print(f"  ... and {len(removed) - 50} more")
    if changed:
        print("\n--- changed ---")
        for p in changed[:50]:
            print(f"  ~ {p}")
        if len(changed) > 50:
            print(f"  ... and {len(changed) - 50} more")
    print(
        "\nReview each entry -- additions are usually benign, but removals "
        "or changes to /paths or component schemas warrant updating the "
        "client and re-pinning (run with --update once reviewed)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
