"""Token gate for the research page.

The research page holds exploratory charts that are not maintained to the
standard of the public dashboard, so it is served only to whoever holds the
token. Fails closed: with no token file configured the page is unavailable.

The token arrives as `?token=` on the first visit and is then kept in a
cookie, so deep links (`/research#services`) work on later visits. Rejected
requests get 404, not 403 — an unauthenticated visitor learns nothing about
whether the page exists.
"""

import hmac
import os
from pathlib import Path

DEFAULT_TOKEN_PATH = "/etc/alt-bitnodes/research-token"
COOKIE_NAME = "research_token"


def load_token(path: str | os.PathLike | None = None) -> str | None:
    """Read the gate token, or None when not configured (page stays closed)."""
    if path is None:
        path = os.environ.get("RESEARCH_TOKEN_PATH", DEFAULT_TOKEN_PATH)
    p = Path(path)
    try:
        token = p.read_text().strip()
    except OSError:
        return None
    return token or None


def is_authorised(supplied: str | None, expected: str | None) -> bool:
    """Constant-time check of a supplied token against the configured one."""
    if not expected or not supplied:
        return False
    return hmac.compare_digest(supplied, expected)
