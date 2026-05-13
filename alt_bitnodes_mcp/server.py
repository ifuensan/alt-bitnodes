"""FastMCP server instance, wired with tools / resources / prompts."""

from mcp.server.fastmcp import FastMCP

from alt_bitnodes_mcp import prompts, resources, tools


def build_server() -> FastMCP:
    """Construct and return a fully-wired FastMCP server."""
    mcp = FastMCP("alt-bitnodes")
    tools.register(mcp)
    resources.register(mcp)
    prompts.register(mcp)
    return mcp
