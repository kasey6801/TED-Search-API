"""Command-line smoke test for the TED Search API client.

    uv run ted-search "publication-date >= today(-7day)" --limit 5

Outputs one result per line by default, or pretty-printed JSON with
`--json`. Designed to exercise the live API end-to-end; not a polished
production CLI.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Annotated

import typer

from ted_search_api.client import TedSearchClient
from ted_search_api.errors import TedAPIError
from ted_search_api.fields import PRESET_SUMMARY
from ted_search_api.models import Scope, SearchResponse

app = typer.Typer(
    add_completion=False,
    help="Smoke-test the TED Search API client.",
    no_args_is_help=True,
)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Expert-search DSL query.")],
    limit: Annotated[int, typer.Option(min=1, max=250)] = 10,
    scope: Annotated[Scope, typer.Option()] = "ACTIVE",
    page: Annotated[int, typer.Option(min=1)] = 1,
    fields_preset: Annotated[
        str,
        typer.Option(
            "--fields-preset",
            help="Use a curated field list. 'summary' (default) or 'none' (server defaults).",
        ),
    ] = "summary",
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Print the raw JSON response instead of a table."),
    ] = False,
) -> None:
    """Run one search against https://api.ted.europa.eu/ and print the results."""
    fields: list[str] | None
    if fields_preset == "summary":
        fields = PRESET_SUMMARY
    elif fields_preset == "none":
        fields = None
    else:
        typer.echo(f"Unknown --fields-preset: {fields_preset!r}", err=True)
        raise typer.Exit(code=2)

    try:
        result = asyncio.run(
            _run_search(query=query, fields=fields, limit=limit, scope=scope, page=page)
        )
    except TedAPIError as e:
        typer.echo(f"TED API error: {e}", err=True)
        raise typer.Exit(code=1) from e

    if as_json:
        json.dump(result.model_dump(), sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return

    typer.echo(f"Total matches: {result.totalNoticeCount}  (showing {len(result.notices)})")
    typer.echo("-" * 80)
    for n in result.notices:
        ident = n.get("notice-identifier") or "?"
        date = n.get("publication-date") or "?"
        title = _flatten(n.get("title-proc")) or "?"
        buyer = _flatten(n.get("buyer-name")) or "?"
        country = _flatten(n.get("organisation-country-buyer")) or "?"
        typer.echo(f"[{date}] {ident} | {country} | {buyer}")
        typer.echo(f"    {title}")


async def _run_search(
    *,
    query: str,
    fields: list[str] | None,
    limit: int,
    scope: Scope,
    page: int,
) -> SearchResponse:
    async with TedSearchClient() as ted:
        return await ted.search(query, fields=fields, limit=limit, scope=scope, page=page)


def _flatten(value: object) -> str | None:
    """Reduce a multilingual / list-wrapped field to a single string.

    The TED API returns many fields as either:
      - a plain string,                  e.g. "FRA"
      - a list of strings,               e.g. ["FRA", "FRA"]
      - a {lang: str} dict,              e.g. {"eng": "Cycling helmets"}
      - a {lang: [str, ...]} dict,       e.g. {"ron": ["UM 0929", "UM 0502"]}
    This helper prefers English where present, then any other language,
    then collapses lists by taking the first entry.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return _flatten(value[0]) if value else None
    if isinstance(value, dict):
        if not value:
            return None
        chosen = value.get("eng") or value.get("ENG") or next(iter(value.values()))
        return _flatten(chosen)
    return str(value)


def main() -> None:
    """Console script entrypoint for `ted-search`."""
    app()


if __name__ == "__main__":
    main()
