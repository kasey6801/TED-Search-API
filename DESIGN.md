# TED-Search-API -- Design Document

**Last updated:** 2026-05-24
**Status:** Python committed (2026-05-24). The toolset in section 3.3 (`uv`, `httpx`, `pydantic` v2, `mcp`, `pytest`, `ruff`) is now the binding choice. This document is meant to be read top-to-bottom; later sections build on earlier ones.

> This document is deliberately tutorial-flavoured: it explains *why* each decision was made, not just what was decided. If you are new to building API clients or to Python project structure, read the "Why?" callouts -- they exist for you.

---

## 1. What we are building, in one paragraph

The European Union publishes every public-sector tender (above certain monetary thresholds) in a daily journal called **TED** -- *Tenders Electronic Daily*. There is an official, free, public HTTP API for searching it. Our project, `TED-Search-API`, wraps that API in two thin layers:

1. **A reusable Python client** -- a small library other programs can import to run TED searches programmatically.
2. **An MCP (Model Context Protocol) server** -- a process Claude (or any MCP-compatible AI client) can talk to in order to search TED on a user's behalf.

Optionally, later, we may add a third layer:

3. **A FastAPI HTTP wrapper** -- a small web server that re-exposes the client over HTTP/JSON, useful if a non-Python caller wants tender search without speaking MCP.

All three layers share the same underlying client. That shared core is the most important piece of the architecture.

> **Why?** If we built the MCP server and the FastAPI server independently, each would have its own HTTP-to-TED translation code, its own retry logic, its own paging logic. Two copies means twice the bugs and twice the maintenance. One shared client, two thin presentation layers, is the standard professional pattern.

---

## 2. The TED Search API, demystified

We read the live OpenAPI specification (`https://ted.europa.eu/docs/v3`) on 2026-05-24. Here is what we learned, in plain English.

### 2.1 Surface area

| Property | Value |
|---|---|
| Base URL | `https://api.ted.europa.eu/` |
| Mirror | `https://tedweb.api.ted.europa.eu/` |
| Specification | OpenAPI 3.1.0 |
| **Number of endpoints** | **1** |
| Authentication | None. Truly public, no key. |
| Request format | JSON |
| Response format | JSON |

That single endpoint is:

```
POST /v3/notices/search
```

> **Why only one endpoint?** Because TED's data model has effectively one resource -- a *notice* (a single procurement publication) -- and one operation we care about: *find notices matching some criteria*. The criteria can be very expressive (see "expert search" below), so a single search endpoint covers the whole API surface a consumer would touch.

### 2.2 The request body

The request is a JSON object with these fields (all optional unless noted):

| Field | Type | Default | Meaning |
|---|---|---|---|
| `query` | string | (none) | An *expert-search* query -- a small, structured query language. See section 2.4. |
| `fields` | string[] | (none, returns defaults) | Which fields of each notice to return. There are about **1 830** legal field names. |
| `page` | integer >= 1 | `1` | Which page of results to fetch (PAGE_NUMBER pagination). |
| `limit` | integer >= 0 | `10` | How many notices per page. **Max 250.** |
| `scope` | enum | `ALL` | `LATEST` = only the current OJ S release; `ACTIVE` = only currently active notices; `ALL` = everything ever. |
| `paginationMode` | enum | `PAGE_NUMBER` | `PAGE_NUMBER` caps results at 15 000; `ITERATION` uses opaque tokens, unlimited. |
| `iterationNextToken` | string | (none) | The opaque token returned by the previous ITERATION call. |
| `onlyLatestVersions` | bool | `false` | Skip superseded versions of notices. |
| `checkQuerySyntax` | bool | `false` | If `true`, the server validates the query without executing it. Free syntax-check. |

> **Why two pagination modes?** PAGE_NUMBER is easier to use (just increment `page`) but the server refuses to walk past result 15 000 -- a sane safety cap on a database with millions of notices. ITERATION uses a server-issued cursor token that encodes *where you left off*; with it you can iterate indefinitely, but the token can expire and you must keep state. For most queries we will start with PAGE_NUMBER and fall back to ITERATION only when a result set is genuinely huge.

### 2.3 The response body

```jsonc
{
  "notices":            [ /* array of notice objects, each containing only the fields you asked for */ ],
  "totalNoticeCount":   12345,        // total matches, not just this page
  "iterationNextToken": "eyJ...",     // present only in ITERATION mode; pass it back to get the next page
  "timedOut":           false         // true if the search hit an internal timeout
}
```

> **Why does `totalNoticeCount` matter?** It lets the caller decide whether to keep paging. If your query matched 9 notices total, fetching page 2 would be wasted work. The MCP tool we expose should always include this number in its response so the AI client can plan follow-up actions intelligently.

### 2.4 The "expert search" query language

The `query` field uses a small custom DSL documented at `https://ted.europa.eu/en/search/expert-search`. The syntax is field-based and looks roughly like a hybrid of Lucene and SQL `WHERE`:

```text
publication-date >= today(-30day) AND organisation-country-buyer = "FRA"
```

```text
classification-cpv IN (45000000, 71000000) AND notice-value-cur >= 1000000
```

Important features the language supports:

- Comparison operators: `=`, `!=`, `>=`, `<=`, `>`, `<`
- Set membership: `IN (...)`
- Boolean composition: `AND`, `OR`, `NOT`, parentheses
- Functions: `today(-N day|week|month|year)` for relative dates
- Wildcards and phrase matching on string fields
- Sorting via an `ORDER BY` suffix

The server returns *structured* errors when a query is malformed: not just "bad query", but the exact line/column, the offending field name, and -- for value errors -- the regex pattern of allowed values. Our client should bubble those structured errors up rather than collapsing them into a generic exception.

> **Why is this nice?** A tool exposed to an AI assistant benefits enormously from precise error feedback. If the AI tries `organistation-country-buyer = "FRA"` (typo), the server tells it *what the correct field name probably is*. The MCP tool we build should pass that diagnostic information back verbatim.

### 2.5 The `fields` enum -- a 1 830-element zoo

The list of legal field names is enormous because TED uses the EU's **eForms** standard, where every business term has a stable identifier like `BT-13(t)-Part` ("time limit for receipt of tenders, part level") or `organisation-country-buyer`. The OpenAPI spec lists all of them.

**Implication for our client:** we should not hardcode a `Literal[...]` of all 1 830 names; that would be fragile (the EU adds fields when eForms evolves). Instead the client accepts `list[str]` and validates only at request time, surfacing the server's `QueryUnknownFieldError` if a caller asks for something invalid. We *should*, however, ship a small curated list of common presets (e.g. `PRESET_SUMMARY = ["notice-identifier", "publication-date", "title-proc", "organisation-name-buyer", "organisation-country-buyer", "classification-cpv"]`) for ergonomic out-of-the-box use.

### 2.6 What the spec does *not* say

- **Rate limits.** Not documented. We should be polite by default (small client-side concurrency, exponential backoff on 429/5xx), and discover empirically.
- **SLAs.** None offered. Treat the service as best-effort.
- **Stability of field IDs.** eForms versions matter; field names can be added when a new eForms version ships.

---

## 3. Stack choice: Python vs Node.js

The user has not committed yet. Below is the honest comparison so the choice is informed.

### 3.1 Comparison table

| Dimension | Python | Node.js / TypeScript |
|---|---|---|
| MCP SDK maturity | **`mcp` Python SDK -- Anthropic's primary reference implementation, most examples target it.** | `@modelcontextprotocol/sdk` -- official, mature, slightly fewer examples. |
| Typing for 1 830-field enum | Pydantic v2 + `list[str]` validated lazily. Easy. | Zod or TypeBox + `string[]`. Equally easy, slightly more boilerplate. |
| HTTP client | `httpx` (async, type-safe, equivalent to JS `fetch`). Excellent. | Native `fetch` (Node 18+). Excellent. |
| OpenAPI -> models | `datamodel-code-generator` (mature, one command). | `openapi-typescript` (mature, one command). |
| FastAPI / HTTP layer (later) | FastAPI is best-in-class for async HTTP + Pydantic. | Hono or Fastify. Excellent but less type-integrated. |
| Data exploration tooling | **Jupyter, pandas, polars -- huge advantage if we ever want to analyse tenders interactively.** | Comparatively limited. |
| Familiarity ramp for a beginner | Smaller surface area; one venv, one `pyproject.toml`. | Familiar `package.json`, but `tsconfig.json` + transpilation steps add ceremony. |

### 3.2 Recommendation

**Python.** Two reasons in order of weight:

1. **MCP ecosystem.** This project's *whole point* is to expose tender search to an AI assistant. The Python MCP SDK is where the most examples, recipes, and Anthropic-supported tooling live. We will move faster.
2. **Data-shape fit.** Tender notices are deeply nested JSON with many optional fields. Pydantic v2 handles that gracefully, and if we ever want to interactively explore search results (which we *will*, while debugging), Python's data tools are dominant.

Node would not be wrong -- both stacks can ship this -- but on current evidence Python is the lower-risk choice.

> **Why not "use both"?** Because the shared client is the heart of the design (section 1). The whole value of writing it once is undone if we maintain it in two languages. Pick one, ship one.

### 3.3 If we picked Python, the concrete toolset

| Concern | Choice | Why |
|---|---|---|
| Package manager | **`uv`** | The 2026 default. Replaces pip + venv + (often) Poetry. Fast and reproducible. |
| HTTP client | **`httpx`** | Async, retries via `httpx-retries`, drop-in similar to `requests`. |
| Models / validation | **`pydantic` v2** | Best-in-class data validation; integrates with FastAPI if we add that layer. |
| MCP SDK | **`mcp`** (official) | The reference implementation. |
| Test runner | **`pytest`** + **`pytest-asyncio`** | Universally standard. |
| HTTP recording for tests | **`pytest-recording`** (VCR) | Makes integration tests reproducible without re-hitting the real API on every run. |
| OpenAPI -> Pydantic | **`datamodel-code-generator`** | One-shot generation; commit the output, do not regenerate on every build. |
| Lint / format | **`ruff`** | Replaces flake8 + isort + black. One tool, one config. |
| Type checker | **`mypy`** (or `pyright`) | Catches obvious mistakes before runtime. |

---

## 4. Project layout: one src-layout package

The chosen layout is a single Python package, `ted_search_api`, with submodules for each concern:

```
TED-Search-API/
├── pyproject.toml           # project metadata + dependencies (PEP 621)
├── README.md                # (later) short pitch + quickstart
├── DESIGN.md                # this document
├── CLAUDE.md                # AI-assist instructions (gitignored, local only)
├── .env                     # GITHUB_TOKEN etc. (gitignored)
├── .gitignore
├── _archive/                # change log, backlog, build overview (gitignored)
├── RELEASE/                 # release bundles (gitignored)
├── src/
│   └── ted_search_api/
│       ├── __init__.py      # public re-exports: TedSearchClient, NoticeResponse, ...
│       ├── client.py        # async TedSearchClient -- one method per logical operation
│       ├── models.py        # Pydantic request + response models (hand-written or generated)
│       ├── paging.py        # async iterator over pages, handles both pagination modes
│       ├── fields.py        # curated PRESET_* lists; no full enum
│       ├── errors.py        # typed exceptions mirroring the API's structured errors
│       ├── cli.py           # `python -m ted_search_api "<query>"` smoke entrypoint
│       ├── mcp/
│       │   ├── __init__.py
│       │   └── server.py    # MCP server exposing `search_notices` tool
│       └── api/             # (Milestone 3, optional)
│           ├── __init__.py
│           └── main.py      # FastAPI app
└── tests/
    ├── conftest.py
    ├── cassettes/           # VCR-recorded HTTP responses
    ├── test_client.py
    ├── test_paging.py
    └── test_mcp_server.py
```

### 4.1 Why src-layout?

A "src-layout" means your importable code lives under a `src/` directory, not at the project root. The two patterns:

- **Flat layout:** code lives at `TED-Search-API/ted_search_api/...`. You can `import ted_search_api` from the project root *without installing the package*, because the directory is on `sys.path`. This is convenient -- and dangerous.
- **Src layout:** code lives at `TED-Search-API/src/ted_search_api/...`. You **must** install the package (`uv pip install -e .`) before you can import it. This catches an entire class of bug: code that "works on my machine" because it accidentally imports a file from the project directory that won't be there once the package is installed elsewhere.

> **Why does this matter for a beginner?** The first time you `pip install` your own project on a fresh machine and an import fails because of a hidden flat-layout assumption, you'll lose an hour. src-layout makes that bug impossible.

### 4.2 Why one package and not three?

We considered `ted_client/` + `ted_mcp/` + `ted_api/` as separate top-level packages. We rejected it.

| Argument | Verdict |
|---|---|
| "Cleaner separation of concerns" | False premise: separation is achieved by *submodules within* one package just as well. |
| "Independent versioning" | We have no use case for shipping MCP v2 against client v1. The natural unit is the whole project. |
| "Easier to extract later" | True, but premature splitting is the more common professional mistake. If MCP grows into its own product, move it then -- a 30-minute refactor, once. |
| "Less boilerplate" | One `pyproject.toml`, one `uv sync`, one set of tests. Three packages would mean uv workspaces or three repos. Real cost, no current benefit. |

> **Rule of thumb a senior engineer would tell you:** start with the simplest structure that does not foreclose your options. The single src-layout package does not foreclose splitting later. The reverse (three packages collapsed into one) is harder.

---

## 5. Milestones

We will deliver in three deliberately small slices. Each milestone is independently useful.

### Milestone 1 -- The shared client (the "boring" foundation)

**Goal:** a Python developer can `pip install -e .` this project and run a real TED search from a REPL.

- `pyproject.toml` with the dependencies in section 3.3.
- `src/ted_search_api/models.py` -- Pydantic models for the request and response. Hand-written, narrow: don't model all 1 830 fields, model the *shape* (`notices`, `totalNoticeCount`, `iterationNextToken`, `timedOut`) and let individual notices be `dict[str, Any]` for now.
- `src/ted_search_api/client.py` -- one async method, `search(query: str, *, fields: list[str] | None = None, page: int = 1, limit: int = 10, scope: Scope = "ALL")`. Uses `httpx.AsyncClient` with sensible timeouts and retry on 429/5xx.
- `src/ted_search_api/errors.py` -- one exception type per documented error kind from the OpenAPI spec.
- `src/ted_search_api/cli.py` -- `python -m ted_search_api "publication-date >= today(-7day)"` prints the first 10 hits as a simple table.
- `tests/test_client.py` -- one happy-path test against a VCR cassette, one structured-error test.

**Acceptance:** running the CLI against the live API returns a result. The VCR test passes offline.

### Milestone 2 -- The MCP server   **(complete, 2026-05-24)**

**Goal:** Claude Code (or any MCP client) can invoke `search_notices` as a tool.

**Delivered:**
- `src/ted_search_api/mcp/server.py` -- FastMCP server with one tool, `search_notices(query, limit, scope, page)`. Caps `limit` at `MAX_LIMIT=50` (the raw API allows 250 but that floods LLM context). Returns a compact summary: `{total_matches, returned, page, next_page, has_more, notices: [{id, publication_date, title, buyer_country, buyer_name, cpv_codes}, ...]}`. Surfaces `TedAPIError` as `{error, error_type}` rather than crashing the tool call.
- `pyproject.toml`: `mcp>=1.0` promoted to required deps; `ted-search-mcp = "ted_search_api.mcp.server:main"` console script wired.
- `tests/test_mcp_server.py` -- 6 unit tests covering `summarise` shape, `has_more` corner cases (including the 15k cap), tool round-trip with monkey-patched client, limit clamping, and API-error path.
- `scripts/mcp_smoke.py` -- spawns `ted-search-mcp` as a subprocess, runs the MCP initialize handshake, lists tools, calls `search_notices` against the live API. End-to-end-verified 2026-05-24 (52240 active tenders, ROU/FRA/SWE notices).

**Claude Code config snippet (paste into `~/.claude/mcp_servers.json`):**

```json
{
  "mcpServers": {
    "ted-search": {
      "command": "uv",
      "args": ["--directory", "/Users/kcharles/ClaudeDev/CC_TED_Search_API", "run", "ted-search-mcp"]
    }
  }
}
```

### Milestone 3 (optional) -- The FastAPI HTTP wrapper

**Goal:** a non-Python caller can hit our server over HTTP/JSON.

- `src/ted_search_api/api/main.py` -- one FastAPI app with one route, `POST /search`, that delegates to `TedSearchClient`.
- Reuse the same Pydantic models -- FastAPI consumes them natively, so request validation and OpenAPI docs come for free.
- Dockerfile (later) for deployment.

We will only build M3 if there is a real consumer. It is genuinely optional.

---

## 6. Risks and open questions

| Risk | Mitigation |
|---|---|
| Undocumented rate limits could surprise us at scale. | Polite defaults (1-2 concurrent requests, exponential backoff). Discover limits empirically and document. |
| Field IDs evolve when EU publishes new eForms versions. | Keep `fields` typed as `list[str]`, not a closed enum. Bubble up `QueryUnknownFieldError` from the server. |
| The expert-search query DSL is non-trivial; users will mis-type. | Consider a `validate_query(query: str) -> ValidationResult` helper that calls the API with `checkQuerySyntax=true`. |
| Iteration tokens can expire. | Document the failure mode; provide a helper that restarts ITERATION if the token expires mid-iteration. |
| LLM clients may request enormous result sets via the MCP tool. | Cap `limit` server-side in the MCP wrapper (e.g. max 50 per call) and require explicit "next page" requests. |

---

## 7. What happens next

Once a stack decision is made, the first action is **Milestone 1, step 1**: write `pyproject.toml` and stand up an empty `src/ted_search_api/` package. From there each step is a small, testable increment.

If the stack stays open, this document is the deliverable; no code is needed yet.

---

## Appendix A -- A worked request/response example

A complete, copy-pastable example of what calling the API *actually looks like over the wire*, so the rest of this document has concrete grounding.

### Request

```http
POST /v3/notices/search HTTP/1.1
Host: api.ted.europa.eu
Content-Type: application/json

{
  "query":  "publication-date >= today(-7day) AND organisation-country-buyer = \"FRA\"",
  "fields": [
    "notice-identifier",
    "publication-date",
    "title-proc",
    "organisation-name-buyer",
    "organisation-country-buyer",
    "classification-cpv"
  ],
  "page":   1,
  "limit":  3,
  "scope":  "ACTIVE"
}
```

### Response (sketch)

```jsonc
{
  "notices": [
    {
      "notice-identifier":         "00123456-2026",
      "publication-date":          "2026-05-22",
      "title-proc":                { "eng": "Supply of cycling helmets" },
      "organisation-name-buyer":   ["Ville de Paris"],
      "organisation-country-buyer":["FRA"],
      "classification-cpv":        ["18443320"]
    },
    { /* ...notice 2... */ },
    { /* ...notice 3... */ }
  ],
  "totalNoticeCount":   412,
  "iterationNextToken": null,
  "timedOut":           false
}
```

This response is exactly what our `TedSearchClient.search(...)` method will deserialise into a `NoticeResponse` Pydantic model.

---

## Appendix B -- Glossary for newcomers

- **TED** -- *Tenders Electronic Daily.* The EU's official daily journal of public procurement notices.
- **Notice** -- a single procurement publication: a tender, an award, a corrigendum, etc.
- **eForms** -- the structured XML/JSON schema the EU mandates for all TED notices since 2024. Field IDs like `BT-13(t)-Part` come from this schema.
- **CPV** -- *Common Procurement Vocabulary.* The EU's classification code for what is being procured (e.g. `45000000` = construction work).
- **MCP** -- *Model Context Protocol.* The open protocol an AI assistant uses to talk to external tools.
- **Pydantic** -- a Python library that validates and parses JSON into typed objects.
- **httpx** -- a Python HTTP library; async-capable, similar API to `requests`.
- **VCR / cassette** -- a recording of a real HTTP request/response, replayed in tests so they run offline.
- **src-layout** -- the convention of putting importable code under `src/` rather than at the project root.
