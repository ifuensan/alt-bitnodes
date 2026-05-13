"""CLI entrypoint for the alt-bitnodes MCP server.

Examples:
    python -m alt_bitnodes_mcp --stdio
    python -m alt_bitnodes_mcp --http --host 127.0.0.1 --port 8001
"""

import argparse
import logging
import os
import sys

import uvicorn

from alt_bitnodes_mcp.auth import BearerAuthMiddleware, load_token
from alt_bitnodes_mcp.server import build_server


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="alt-bitnodes-mcp")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stdio", action="store_true", help="Speak MCP over stdin/stdout")
    group.add_argument("--http", action="store_true", help="Serve Streamable HTTP")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for --http (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8001, help="Bind port for --http (default 8001)")
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="(http) Skip bearer auth. Local development only. Forbidden when MCP_REQUIRE_AUTH=1.",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("MCP_LOG_LEVEL", "INFO"),
        help="Python log level (default INFO; env MCP_LOG_LEVEL)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("alt-bitnodes-mcp")

    mcp = build_server()

    if args.stdio:
        log.info("starting alt-bitnodes MCP server (stdio, no auth)")
        mcp.run(transport="stdio")
        return 0

    # --- HTTP mode ---
    require_auth_env = os.environ.get("MCP_REQUIRE_AUTH", "1") not in ("0", "false", "no", "off")
    use_auth = True
    if args.no_auth:
        if require_auth_env:
            log.error("--no-auth refused: MCP_REQUIRE_AUTH=1 in environment")
            return 2
        use_auth = False

    app = mcp.streamable_http_app()
    if use_auth:
        token = load_token()
        app.add_middleware(BearerAuthMiddleware, token=token)
        log.info(
            "bearer auth enabled (token loaded from %s)",
            os.environ.get("MCP_TOKEN_PATH", "/etc/alt-bitnodes/mcp-token"),
        )
    else:
        log.warning("bearer auth DISABLED (--no-auth). Do NOT use in production.")

    log.info("starting alt-bitnodes MCP server (http) on %s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
