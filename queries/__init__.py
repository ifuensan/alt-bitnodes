"""Pure data-access layer shared by the REST API (`app.py`) and the MCP server.

No FastAPI / HTTP coupling. Functions return plain dicts / lists / tuples
and raise standard exceptions (FileNotFoundError, ValueError, LookupError).
HTTP-layer translation lives in `app.py`.
"""

from queries.config import (
    EXPORT_DIR,
    REDIS_URL,
    RTT_DB_PATH,
    RTT_WINDOW_SECONDS,
    RTT_RETENTION_DAYS,
    OPENDATA_TTL_SECONDS,
    FIELDS,
)
from queries.snapshots import (
    list_snapshots,
    load_snapshot,
    snapshot_meta,
    snapshot_stats,
    to_dict,
    known_addresses_set,
)
from queries.rtt import (
    db as rtt_db,
    samples_for,
    median_rtt_for,
    medians_in_window,
    ingest_once,
    retention_pass,
)
from queries.nodes import (
    parse_node_id,
    node_status,
    opendata_index,
)
from queries.leaderboard import (
    NoSnapshotsError,
    SnapshotMissingError,
    leaderboard,
    rankings_by_country,
    rankings_by_asn,
    rankings_by_user_agent,
    groups_by_ip,
    group_by_ip_detail,
)
from queries.util import iso2_to_iso3

__all__ = [
    "EXPORT_DIR",
    "REDIS_URL",
    "RTT_DB_PATH",
    "RTT_WINDOW_SECONDS",
    "RTT_RETENTION_DAYS",
    "OPENDATA_TTL_SECONDS",
    "FIELDS",
    "list_snapshots",
    "load_snapshot",
    "snapshot_meta",
    "snapshot_stats",
    "to_dict",
    "known_addresses_set",
    "rtt_db",
    "samples_for",
    "median_rtt_for",
    "medians_in_window",
    "ingest_once",
    "retention_pass",
    "parse_node_id",
    "node_status",
    "opendata_index",
    "NoSnapshotsError",
    "SnapshotMissingError",
    "leaderboard",
    "rankings_by_country",
    "rankings_by_asn",
    "rankings_by_user_agent",
    "groups_by_ip",
    "group_by_ip_detail",
    "iso2_to_iso3",
]
