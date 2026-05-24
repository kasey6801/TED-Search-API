"""MCP server subpackage.

Public surface is the `ted-search-mcp` console script defined in
`pyproject.toml`. Programmatic use:

    from ted_search_api.mcp.server import mcp, search_notices
"""

from ted_search_api.mcp.server import mcp, search_notices, summarise

__all__ = ["mcp", "search_notices", "summarise"]
