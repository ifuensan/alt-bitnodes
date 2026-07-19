"""Centralised configuration constants. Reads from environment with the same
defaults `app.py` used historically so behaviour is unchanged after the refactor.
"""

import os
from pathlib import Path

EXPORT_DIR = Path(
    os.environ.get(
        "BITNODES_EXPORT_DIR",
        "/mnt/datos/home_data/Work/hacknodes/myprojects/research/bitnodes/data/export/f9beb4d9",
    )
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
ARCHIVE_DIR = Path(os.environ.get("BITNODES_ARCHIVE_DIR", "data/archive"))
WINDOW_STATS_FILE = Path(
    os.environ.get("BITNODES_WINDOW_STATS_FILE", "data/window-stats.json")
)
OPENDATA_TTL_SECONDS = 10

FIELDS = [
    "address", "port", "protocol_version", "user_agent", "timestamp",
    "services", "height", "hostname", "city", "country",
    "latitude", "longitude", "timezone", "asn", "asn_name",
]
