"""Tier-1 drift detector: assert frozen historical notices still match.

For each canary in ``tests/fixtures/canary_notices.json``, query the live
TED API for that exact ``notice-identifier`` and compare every expected
field to the live response. Any mismatch (field disappeared, value
changed, type changed) is a high-confidence signal of semantic drift --
the schema diff in ``spec_diff.py`` would miss this entirely.

Exit codes
----------
0  all canaries PASS
1  one or more FAILED (drift, missing, or fetch error)

Run with::

    uv run python scripts/canary.py
    uv run python scripts/canary.py --verbose

Why these notices?
------------------
Selected from June 2025 (eForms-era, contracts long since finalised) and
chosen to span 5 different countries. They are deliberately past notices
on closed procurements: their values should be immutable. If any one of
them stops matching, something material has shifted upstream.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import sys
from pathlib import Path
from typing import Any

from ted_search_api import TedSearchClient

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "canary_notices.json"
)


def _format_value(v: Any) -> str:
    """Canonical pretty form for diffing -- stable across dict orderings."""
    return json.dumps(v, indent=2, sort_keys=True, ensure_ascii=False)


def _diff(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Per-field comparison; returns human-readable lines for failures only."""
    failures: list[str] = []
    for key, exp in expected.items():
        if key not in actual:
            failures.append(f"    MISSING field {key!r}")
            continue
        act = actual[key]
        if exp != act:
            exp_lines = _format_value(exp).splitlines()
            act_lines = _format_value(act).splitlines()
            udiff = list(
                difflib.unified_diff(
                    exp_lines, act_lines, fromfile="expected", tofile="actual", lineterm=""
                )
            )
            failures.append(f"    CHANGED field {key!r}:")
            failures.extend(f"      {line}" for line in udiff)
    return failures


async def _check_one(
    client: TedSearchClient, nid: str, expected: dict[str, Any]
) -> tuple[bool, list[str]]:
    fields = list(expected.keys())
    try:
        result = await client.search(
            f'notice-identifier = "{nid}"',
            fields=fields,
            limit=1,
            scope="ALL",
        )
    except Exception as e:
        return False, [f"    fetch error: {e!r}"]

    if not result.notices:
        return False, ["    NOT FOUND in current API (notice retracted or id changed?)"]

    return not (failures := _diff(expected, result.notices[0])), failures


async def _main_async(verbose: bool) -> int:
    fixture: dict[str, dict[str, Any]] = json.loads(FIXTURE_PATH.read_text())
    print(f"[canary] checking {len(fixture)} canaries against live API")

    pass_count = 0
    async with TedSearchClient() as client:
        for nid, expected in fixture.items():
            ok, failures = await _check_one(client, nid, expected)
            if ok:
                pass_count += 1
                if verbose:
                    print(f"  PASS  {nid}")
            else:
                print(f"  FAIL  {nid}")
                for line in failures:
                    print(line)

    total = len(fixture)
    print(f"\n[canary] {pass_count}/{total} {'PASS' if pass_count == total else 'FAIL'}")
    return 0 if pass_count == total else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_main_async(args.verbose))


if __name__ == "__main__":
    sys.exit(main())
