"""Bearer-token auth middleware for the MCP HTTP transport.

Used only in `--http` mode. stdio mode runs without auth (local trust boundary).
"""

import hmac
import os
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

DEFAULT_TOKEN_PATH = "/etc/alt-bitnodes/mcp-token"


class MCPTokenMissingError(RuntimeError):
    """The token file does not exist or is empty."""


def load_token(path: str | os.PathLike | None = None) -> str:
    """Read the bearer token from `path` (default `/etc/alt-bitnodes/mcp-token`).

    The env var `MCP_TOKEN_PATH` overrides the default if `path` is None.
    """
    if path is None:
        path = os.environ.get("MCP_TOKEN_PATH", DEFAULT_TOKEN_PATH)
    p = Path(path)
    if not p.exists():
        raise MCPTokenMissingError(f"MCP token file not found: {p}")
    token = p.read_text().strip()
    if not token:
        raise MCPTokenMissingError(f"MCP token file is empty: {p}")
    return token


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests without a valid `Authorization: Bearer <token>` header.

    The token is loaded once at construction time. Comparison is constant-time.
    """

    def __init__(self, app: ASGIApp, *, token: str) -> None:
        super().__init__(app)
        if not token:
            raise ValueError("BearerAuthMiddleware requires a non-empty token")
        self._token = token

    async def dispatch(self, request: Request, call_next) -> Response:
        header = request.headers.get("authorization", "")
        scheme, _, value = header.partition(" ")
        if scheme.lower() != "bearer" or not value:
            return JSONResponse(
                {"error": "missing or malformed Authorization header"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="alt-bitnodes-mcp"'},
            )
        if not hmac.compare_digest(value, self._token):
            return JSONResponse(
                {"error": "invalid bearer token"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="alt-bitnodes-mcp"'},
            )
        return await call_next(request)
