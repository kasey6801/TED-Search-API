"""Stand-alone smoke test for the ted-search-mcp server.

Spawns the server over stdio (the same way an MCP client would), runs
the initialize handshake, lists tools, and calls `search_notices` once
against the live API. Prints a one-line PASS/FAIL.

Run with:
    uv run python scripts/mcp_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    params = StdioServerParameters(command="uv", args=["run", "ted-search-mcp"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        tools = await session.list_tools()
        names = [t.name for t in tools.tools]
        print(f"[smoke] tools registered: {names}")
        if "search_notices" not in names:
            print("[smoke] FAIL: search_notices not registered", file=sys.stderr)
            return 1

        result = await session.call_tool(
            "search_notices",
            arguments={"query": "publication-date >= 20260501", "limit": 3, "scope": "ACTIVE"},
        )
        # FastMCP returns tool output via the structured content field.
        payload = result.structuredContent or {}
        if "notices" not in payload:
            # Fall back to parsing the first text content block.
            for block in result.content:
                if hasattr(block, "text"):
                    payload = json.loads(block.text)
                    break

        total = payload.get("total_matches")
        returned = payload.get("returned")
        warnings = payload.get("validation_warnings")
        print(
            f"[smoke] total_matches={total} returned={returned} "
            f"validation_warnings={warnings}"
        )
        if not isinstance(total, int) or returned != 3:
            print("[smoke] FAIL: unexpected response shape", file=sys.stderr)
            return 1
        if warnings != 0:
            print(
                f"[smoke] FAIL: validation_warnings={warnings} -- live notices "
                "are failing strict validation; investigate drift",
                file=sys.stderr,
            )
            return 1

        first = payload["notices"][0]
        print(
            f"[smoke] first notice: id={first.get('id')} country={first.get('buyer_country')} "
            f"buyer={first.get('buyer_name')!r}"
        )
        print("[smoke] PASS")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
