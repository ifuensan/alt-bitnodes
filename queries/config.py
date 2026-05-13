"""Centralised configuration constants. Reads from environment with the same
defaults `app.py` used historically so behaviour is unchanged after the refactor.
"""

import os
from pathlib import Path

EXPORT_DIR = Path(
    os.environ.get(
        "BITNODES_EXPORT_DIR",
        "/mnt/datos/home_data/Work/myprojects/research/bitnodes/data/export/f9beb4d9",
    )
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
OPENDATA_TTL_SECONDS = 10

# `data/` here is the runtime data directory (gitignored), not the Python package.
RTT_DB_PATH = Path(
    os.environ.get(
        "RTT_DB_PATH",
        str(Path(__file__).resolve().parent.parent / "data" / "rtt.sqlite"),
    )
)
RTT_WINDOW_SECONDS = int(os.environ.get("RTT_WINDOW_SECONDS", "1800"))
RTT_RETENTION_DAYS = int(os.environ.get("RTT_RETENTION_DAYS", "30"))

FIELDS = [
    "address", "port", "protocol_version", "user_agent", "timestamp",
    "services", "height", "hostname", "city", "country",
    "latitude", "longitude", "timezone", "asn", "asn_name",
]
