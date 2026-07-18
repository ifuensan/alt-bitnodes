"""Pure data-access layer shared by the REST API (`app.py`) and the MCP server.

No FastAPI / HTTP coupling. Functions return plain dicts / lists / tuples
and raise standard exceptions (FileNotFoundError, ValueError, LookupError).
HTTP-layer translation lives in `app.py`.
"""

from queries.config import (
    EXPORT_DIR,
    REDIS_URL,
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
from queries.nodes import (
    parse_node_id,
    node_status,
    opendata_index,
)
from queries.leaderboard import (
    NoSnapshotsError,
    SnapshotMissingError,
    rankings_by_country,
    rankings_by_asn,
    rankings_by_user_agent,
    groups_by_ip,
    group_by_ip_detail,
)
from queries.archives import (
    find_archive_file,
    list_archives,
)
from queries.util import iso2_to_iso3

__all__ = [
    "find_archive_file",
    "list_archives",
    "EXPORT_DIR",
    "REDIS_URL",
    "OPENDATA_TTL_SECONDS",
    "FIELDS",
    "list_snapshots",
    "load_snapshot",
    "snapshot_meta",
    "snapshot_stats",
    "to_dict",
    "known_addresses_set",
    "parse_node_id",
    "node_status",
    "opendata_index",
    "NoSnapshotsError",
    "SnapshotMissingError",
    "rankings_by_country",
    "rankings_by_asn",
    "rankings_by_user_agent",
    "groups_by_ip",
    "group_by_ip_detail",
    "iso2_to_iso3",
]
