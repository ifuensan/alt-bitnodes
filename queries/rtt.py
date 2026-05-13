"""RTT samples store (SQLite) + Redis ingest helpers.

Pure data-layer. The asyncio ingest loop that wraps `ingest_once` lives in
`app.py` for now since it's tied to the FastAPI startup event.
"""

import sqlite3
import statistics
import threading
import time
from functools import lru_cache

import redis

from queries.config import RTT_DB_PATH, RTT_RETENTION_DAYS, RTT_WINDOW_SECONDS


class _MedianAgg:
    def __init__(self) -> None:
        self.values: list[int] = []

    def step(self, value) -> None:
        if value is not None:
            self.values.append(int(value))

    def finalize(self):
        if not self.values:
            return None
        return int(statistics.median(self.values))


_db_lock = threading.Lock()


@lru_cache(maxsize=1)
def db() -> sqlite3.Connection:
    RTT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(RTT_DB_PATH), check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rtt_samples (
            address TEXT NOT NULL,
            port    INTEGER NOT NULL,
            ts      INTEGER NOT NULL,
            rtt_ms  INTEGER NOT NULL,
            PRIMARY KEY (address, port, ts, rtt_ms)
        ) WITHOUT ROWID;
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rtt_node_ts ON rtt_samples(address, port, ts DESC);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rtt_ts ON rtt_samples(ts);")
    conn.create_aggregate("median", 1, _MedianAgg)
    return conn


def _parse_rtt_key(key: bytes) -> tuple[str, int] | None:
    """rtt:<addr>-<port> → (addr, port). addr may contain ':' (IPv6)."""
    try:
        s = key.decode("ascii", "replace")
    except Exception:
        return None
    if not s.startswith("rtt:"):
        return None
    rest = s[4:]
    addr, _, port_s = rest.rpartition("-")
    if not addr or not port_s.isdigit():
        return None
    return addr, int(port_s)


def _count_new_rtts(items: list, prev_head, prev_len: int) -> int:
    new_len = len(items)
    if prev_head is None:
        return new_len
    if new_len > prev_len:
        return new_len - prev_len
    if items[0] == prev_head:
        return 0
    try:
        return items.index(prev_head)
    except ValueError:
        return new_len


def _process_rtt_key(
    redis_conn: redis.Redis, key, prev_state: dict, now: int, inserts: list, new_state: dict
) -> None:
    parsed = _parse_rtt_key(key)
    if parsed is None:
        return
    addr, port = parsed
    try:
        items = redis_conn.lrange(key, 0, -1)
    except redis.RedisError:
        return
    if not items:
        return

    prev_head, prev_len = prev_state.get((addr, port), (None, 0))
    new_count = _count_new_rtts(items, prev_head, prev_len)

    for v in items[:new_count]:
        try:
            rtt_ms = int(v)
        except (ValueError, TypeError):
            continue
        inserts.append((addr, port, now, rtt_ms))

    new_state[(addr, port)] = (items[0], len(items))


def ingest_once(redis_conn: redis.Redis, prev_state: dict) -> dict:
    """Pull fresh RTT samples from Redis into SQLite. Returns updated state."""
    now = int(time.time())
    new_state: dict = {}
    inserts: list[tuple[str, int, int, int]] = []

    cursor = 0
    while True:
        cursor, batch = redis_conn.scan(cursor=cursor, match="rtt:*", count=1000)
        for key in batch:
            _process_rtt_key(redis_conn, key, prev_state, now, inserts, new_state)
        if cursor == 0:
            break

    if inserts:
        with _db_lock:
            db().executemany(
                "INSERT OR IGNORE INTO rtt_samples(address, port, ts, rtt_ms) VALUES (?, ?, ?, ?)",
                inserts,
            )
    return new_state


def retention_pass() -> int:
    cutoff = int(time.time()) - RTT_RETENTION_DAYS * 86400
    with _db_lock:
        cur = db().execute("DELETE FROM rtt_samples WHERE ts < ?", (cutoff,))
        return cur.rowcount or 0


def median_rtt_for(addr: str, port: int, window_seconds: int = RTT_WINDOW_SECONDS) -> int | None:
    cutoff = int(time.time()) - window_seconds
    row = db().execute(
        "SELECT median(rtt_ms) FROM rtt_samples WHERE address=? AND port=? AND ts>=?",
        (addr, port, cutoff),
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def medians_in_window(window_seconds: int = RTT_WINDOW_SECONDS) -> dict[tuple[str, int], int]:
    cutoff = int(time.time()) - window_seconds
    rows = db().execute(
        "SELECT address, port, median(rtt_ms) FROM rtt_samples WHERE ts>=? GROUP BY address, port",
        (cutoff,),
    ).fetchall()
    return {(r[0], r[1]): r[2] for r in rows if r[2] is not None}


def samples_for(addr: str, port: int, hours: int) -> list[tuple[int, int]]:
    cutoff = int(time.time()) - hours * 3600
    rows = db().execute(
        "SELECT ts, rtt_ms FROM rtt_samples WHERE address=? AND port=? AND ts>=? ORDER BY ts ASC",
        (addr, port, cutoff),
    ).fetchall()
    return [(int(r[0]), int(r[1])) for r in rows]


def has_samples(addr: str, port: int) -> bool:
    row = db().execute(
        "SELECT 1 FROM rtt_samples WHERE address=? AND port=? LIMIT 1",
        (addr, port),
    ).fetchone()
    return row is not None
