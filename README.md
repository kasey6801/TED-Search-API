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

### Use it as an MCP server

The server speaks the [Model Context Protocol](https://modelcontextprotocol.io/) over stdio. Any MCP-compatible host -- Claude Desktop, Claude Code, Cursor, Continue.dev, Cline, Zed, or a custom client built on the official Python / TypeScript SDKs -- can spawn it as a subprocess and call the `search_notices` tool.

You don't normally launch the server by hand; the host does. You can sanity-check that it boots with:

```bash
uv run ted-search-mcp        # waits on stdin for MCP JSON-RPC frames; Ctrl-C to exit
```

#### What every host needs to know

Every MCP host configures servers with the same three pieces of information:

| Field | Value for `ted-search` |
|---|---|
| **Server name** | A label you choose, e.g. `ted-search`. |
| **Command** | The absolute path to your `uv` binary. Run `which uv` to find it -- on macOS it is typically `/Users/YOU/.local/bin/uv`. |
| **Args** | `["--directory", "/path/to/TED-Search-API", "run", "ted-search-mcp"]` |

> **Why the absolute path to `uv`?** MCP hosts spawn subprocesses with a minimal `PATH` that usually does *not* include `~/.local/bin`. If you write `"command": "uv"` and the host can't resolve it, the server silently fails to launch and the tool simply never appears. Hardcoding the full path eliminates this entire class of bug.

#### Generic JSON config

Most hosts use a JSON config file with this exact shape:

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

The shape is identical across hosts; only the *file* you drop it into differs:

| Host | Config file (or command) |
|---|---|
| **Claude Desktop** (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Claude Desktop** (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Claude Code** | `~/.claude.json` -- or run `claude mcp add` (see below) |
| **Cursor** | `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (per-project) |
| **Continue.dev** | `~/.continue/config.json`, under an `mcpServers` key |
| **Cline** (VS Code extension) | VS Code Settings → search "Cline: MCP" → edit the servers JSON |
| **Anything else** | Check your host's MCP docs; the JSON shape above is the de facto convention. |

After editing, **fully restart the host application** -- close all windows *and* quit the menu-bar / background process. Closing the window alone is usually not enough.

#### CLI shortcut (Claude Code)

If you have the `claude` CLI installed, skip the JSON edit entirely:

```bash
claude mcp add ted-search --scope user -- \
  /Users/YOU/.local/bin/uv \
  --directory /Users/YOU/path/to/TED-Search-API \
  run ted-search-mcp
```

(`--scope user` makes it available across every project. Drop the flag for project-only scope, which writes a local `.mcp.json` instead.) The VS Code Claude Code extension reads the same registry as the CLI.

#### From a custom MCP client

`scripts/mcp_smoke.py` in this repo is a ~60-line working example. The core pattern:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(
    command="/Users/YOU/.local/bin/uv",
    args=["--directory", "/path/to/TED-Search-API", "run", "ted-search-mcp"],
)
async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
    await session.initialize()
    tools = await session.list_tools()             # → [Tool(name='search_notices', ...)]
    result = await session.call_tool(
        "search_notices",
        arguments={"query": "publication-date >= 20260501", "limit": 5, "scope": "ACTIVE"},
    )
    print(result.structuredContent)
```

#### Verifying it works

Once the host has spawned the server, the `search_notices` tool is available in any conversation. Test it with something like:

> *"Use the ted-search tool to find 5 active French tenders for road resurfacing published since May 1st 2026."*

The tool returns a compact JSON summary: `total_matches`, `returned`, `page`, `next_page`, `has_more`, and a list of notices (each with `id`, `publication_date`, `title`, `buyer_country`, `buyer_name`, `cpv_codes`). The host surfaces it as a tool-call invocation; the assistant interprets the result.

If the tool doesn't appear after a restart, check the host's MCP logs for stderr from the spawn -- almost always either a `PATH`/`command not found` issue (use the absolute path) or a stale config file path.

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

## Operational guardrails

The TED API is publicly maintained and can change between releases. Three guardrails ship with the project so drift surfaces loudly instead of poisoning downstream results silently.

```bash
uv run python scripts/spec_diff.py        # diff live OpenAPI spec vs pinned snapshot
uv run python scripts/spec_diff.py --update   # re-pin after reviewing a benign diff
uv run python scripts/canary.py -v         # assert 5 frozen historical notices still match
```

In addition, every notice flowing through the MCP `search_notices` tool is run through a strict `NoticeSummary` Pydantic model (`src/ted_search_api/models.py`). Unknown upstream fields are tolerated silently, but malformed values on known fields are surfaced via the response's `validation_warnings` counter. A non-zero count is the assistant's cue to flag results for human review rather than treat them as authoritative.

Run any of the three scripts manually, on a cron, or as a GitHub Action -- they each exit non-zero on drift, so wiring them into a scheduler is one line.

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
