# TED Search API

> Async Python client and MCP server for the EU's [Tenders Electronic Daily](https://ted.europa.eu/) -- the official journal of public procurement in the European Union.

TED publishes every public-sector tender in the EU above certain monetary thresholds. The EU exposes a free, keyless HTTP search API. This project wraps that API in two ways:

1. **A reusable async Python client** -- `TedSearchClient` -- that any Python program can import.
2. **An MCP (Model Context Protocol) server** -- `ted-search-mcp` -- that exposes TED search as a single `search_notices` tool to Claude Desktop, Claude Code, and any other MCP-compatible AI client.

A small typer-based CLI (`ted-search`) is also included for live smoke-testing.

**Status:** Milestone 1 (shared client + CLI) and Milestone 2 (MCP server) are complete. The MCP server is verified end-to-end against the live API. See [`DESIGN.md`](DESIGN.md) for architecture rationale and the full milestone breakdown.

---

## Quickstart

You'll need [`uv`](https://docs.astral.sh/uv/) installed.

```bash
git clone https://github.com/kasey6801/TED-Search-API.git
cd TED-Search-API
uv sync
```

### Use it from the command line

```bash
uv run ted-search "publication-date >= 20260501" --limit 5 --scope ACTIVE
```

Sample output:

```
Total matches: 52240  (showing 5)
--------------------------------------------------------------------------------
[2026-05-04+02:00] daec2c64-4e45-4e9f-81b7-2a1510f39c54 | ROU | UM 0929 Bucuresti
    Prestare servicii de mentenanță aparatură medicală, de stomatologie și laborator
[2026-05-04+02:00] db5ccb01-87ba-4d99-8aed-98ae2e3d8934 | FRA | Dijon Métropole
    DIJON METROPOLE -- Relance réfection des couches de roulement...
...
```

Pass `--json` for the raw structured response, `--fields-preset none` to use the server's default field set, `--page N` to paginate.

### Use it from Python

```python
import asyncio
from ted_search_api import TedSearchClient, PRESET_SUMMARY

async def main():
    async with TedSearchClient() as ted:
        result = await ted.search(
            "publication-date >= 20260501",
            fields=PRESET_SUMMARY,
            limit=10,
            scope="ACTIVE",
        )
        print(result.totalNoticeCount, "matches")
        for n in result.notices:
            print(n["notice-identifier"], n.get("buyer-name"))

asyncio.run(main())
```

For unbounded result sets, use the async iterator:

```python
from ted_search_api import TedSearchClient
from ted_search_api.paging import iter_notices

async with TedSearchClient() as ted:
    async for notice in iter_notices(ted, "publication-date >= 20260101", limit=100):
        ...
```

### Use it from Claude (MCP server)

Run it as a subprocess (you don't usually launch it manually -- the MCP host does):

```bash
uv run ted-search-mcp
```

#### Wire into Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (replace `/Users/YOU` paths):

```json
{
  "mcpServers": {
    "ted-search": {
      "command": "/Users/YOU/.local/bin/uv",
      "args": [
        "--directory",
        "/Users/YOU/path/to/TED-Search-API",
        "run",
        "ted-search-mcp"
      ]
    }
  }
}
```

Fully quit Claude Desktop (⌘Q) and reopen it. The `search_notices` tool then becomes available in any conversation.

#### Wire into Claude Code

```bash
claude mcp add ted-search --scope user -- \
  /Users/YOU/.local/bin/uv \
  --directory /Users/YOU/path/to/TED-Search-API \
  run ted-search-mcp
```

(The absolute path to `uv` matters -- MCP hosts spawn subprocesses with a minimal `PATH` that may not include `~/.local/bin`.)

Then, in a Claude conversation:

> *"Use the ted-search tool to find 5 active French tenders for road resurfacing published since May 1st 2026."*

---

## The query language

The `query` argument uses TED's [expert-search DSL](https://ted.europa.eu/en/search/expert-search). It's a small SQL-`WHERE`-like syntax. A few non-obvious things worth knowing:

- **Dates are literal `YYYYMMDD` strings.** There is **no** `today(-N day)` function -- a query like `publication-date >= today(-7day)` will be rejected with a structured syntax error.
- **The `fields` parameter is required** even though the OpenAPI spec marks it optional. Sending without it returns "Validation error".
- **The API silently drops field names that don't apply to a given notice** -- no warning, just absence. The correct field for buyer name is `buyer-name` (multilingual dict), not `organisation-name-buyer`.

Examples:

```text
publication-date >= 20260501
publication-date >= 20260501 AND organisation-country-buyer = "FRA"
classification-cpv = "45000000"
notice-type = "cn-standard"
```

See the [TED expert-search reference](https://ted.europa.eu/en/search/expert-search) for the full grammar and the [TED OpenAPI spec](https://ted.europa.eu/docs/v3) for the complete list of ~1830 valid field names.

---

## Project structure

```
src/ted_search_api/
├── __init__.py     # public re-exports
├── client.py       # TedSearchClient (async, httpx-based)
├── models.py       # Pydantic SearchRequest / SearchResponse
├── errors.py       # TedAPIError / TedHTTPError / TedQueryError
├── paging.py       # iter_notices() async generator
├── fields.py       # PRESET_SUMMARY, PRESET_BUYER_AND_VALUE
├── cli.py          # `ted-search` typer entrypoint
└── mcp/
    ├── __init__.py
    └── server.py   # FastMCP server, `search_notices` tool
tests/              # 10 tests, offline via VCR cassettes
scripts/
└── mcp_smoke.py    # MCP stdio round-trip against the live API
```

See [`DESIGN.md`](DESIGN.md) § 4 for the layout rationale (single `src`-layout package, not three).

---

## Development

```bash
uv sync                                 # install deps
uv run pytest                           # 10 tests, offline via VCR cassettes
uv run pytest --record-mode=rewrite     # re-record cassettes against the live API
uv run ruff check .                     # lint
uv run mypy src                         # strict type-check (zero issues across 9 files)
uv run python scripts/mcp_smoke.py      # MCP stdio round-trip against the live API
```

---

## Limitations and roadmap

- **No automatic retries** on 429 / 5xx -- failures surface as `TedHTTPError`. The TED API does not document rate limits; client-side backoff is left to the caller.
- **MCP tool caps `limit` at 50** (the raw API allows 250). This keeps LLM context manageable; raise via the `MAX_LIMIT` constant in `src/ted_search_api/mcp/server.py` if you need more per call.
- **`paginationMode=PAGE_NUMBER` is capped server-side at 15 000 results.** For larger sweeps, call `iter_notices(..., mode="ITERATION")` -- it uses opaque continuation tokens and has no fixed cap.
- **Milestone 3 (FastAPI HTTP wrapper) is deliberately not built** -- only worth doing if a non-Python, non-MCP consumer appears. See [`DESIGN.md`](DESIGN.md) § 5.

---

## License

[MIT](LICENSE) © 2026 Kévin C ([@kasey6801](https://github.com/kasey6801)). See the [`LICENSE`](LICENSE) file for the full text.

---

## See also

- [`DESIGN.md`](DESIGN.md) -- full architecture rationale, alternatives considered, milestone breakdown, beginner-friendly glossary.
- [TED official search UI](https://ted.europa.eu/en/) -- the same data via the EU's web interface.
- [TED OpenAPI spec](https://ted.europa.eu/docs/v3) -- live machine-readable spec.
- [TED expert-search DSL reference](https://ted.europa.eu/en/search/expert-search) -- query language.
- [Model Context Protocol](https://modelcontextprotocol.io/) -- the open protocol the MCP server speaks.
