"""Tiered snapshot archive: selection rules and archive listing.

The archive keeps one "photo" (snapshot) per period at decreasing
granularity — GFS-style rotation:

- daily: the last snapshot of each of the last DAILY_DAYS complete days
- weekly: the last snapshot of each ISO week older than that, up to
  WEEKLY_WEEKS
- monthly: the last snapshot of each month, forever

A photo's tier follows from the age of its UTC date, so photos cascade
daily -> weekly -> monthly as they age. While a week straddles the
daily/weekly boundary its weekly representative may briefly be an earlier
day; once the whole week ages out the true last-of-week takes over and the
earlier copy rotates away.
"""

import datetime as dt
import json
from pathlib import Path

from queries.config import ARCHIVE_DIR

DAILY_DAYS = 7
WEEKLY_WEEKS = 12

TIERS = ("daily", "weekly", "monthly")

FORMATS = {"csv": "text/csv", "parquet": "application/vnd.apache.parquet"}

META_FILE = "meta.json"


def utc_date(timestamp: int) -> dt.date:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).date()


def tier_and_period(date: dt.date, today: dt.date) -> tuple[str, str] | None:
    """Tier and period key for a photo date, or None if not archivable yet
    (today's snapshots are still accumulating)."""
    age = (today - date).days
    if age < 1:
        return None
    if age <= DAILY_DAYS:
        return "daily", date.isoformat()
    if age <= DAILY_DAYS + WEEKLY_WEEKS * 7:
        iso = date.isocalendar()
        return "weekly", f"{iso[0]}-W{iso[1]:02d}"
    return "monthly", f"{date.year}-{date.month:02d}"


def compute_keep(timestamps, today: dt.date) -> dict[int, str]:
    """Map timestamp -> tier for the photos the archive should contain.

    `timestamps` must be the union of raw snapshot timestamps and already
    archived ones: raw files get pruned, so archived photos keep asserting
    their period through this function.
    """
    best: dict[tuple[str, str], int] = {}
    for ts in timestamps:
        placed = tier_and_period(utc_date(ts), today)
        if placed is None:
            continue
        if best.get(placed) is None or ts > best[placed]:
            best[placed] = ts
    return {ts: tier for (tier, _period), ts in best.items()}


def photo_basename(timestamp: int) -> str:
    return f"{utc_date(timestamp).isoformat()}-{timestamp}"


def photo_path(tier: str, timestamp: int, fmt: str, root: Path = None) -> Path:
    root = root or ARCHIVE_DIR
    return root / tier / f"{photo_basename(timestamp)}.{fmt}"


def scan_archive(root: Path = None) -> dict[int, str]:
    """Map timestamp -> tier for photos present on disk (either format)."""
    root = root or ARCHIVE_DIR
    found: dict[int, str] = {}
    for tier in TIERS:
        tier_dir = root / tier
        if not tier_dir.exists():
            continue
        for p in tier_dir.iterdir():
            stem, _, _ = p.name.rpartition(".")
            ts = stem.rsplit("-", 1)[-1]
            if ts.isdigit():
                found[int(ts)] = tier
    return found


def load_meta(root: Path = None) -> dict:
    root = root or ARCHIVE_DIR
    path = root / META_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def list_archives(root: Path = None) -> list[dict]:
    """Photos on disk, newest first, with sizes and metadata for the API."""
    root = root or ARCHIVE_DIR
    meta = load_meta(root)
    entries = []
    for ts, tier in scan_archive(root).items():
        formats = {}
        for fmt in FORMATS:
            p = photo_path(tier, ts, fmt, root)
            if p.exists():
                formats[fmt] = {
                    "size": p.stat().st_size,
                    "url": f"/api/v1/archives/{ts}.{fmt}",
                }
        if not formats:
            continue
        entries.append(
            {
                "tier": tier,
                "date": utc_date(ts).isoformat(),
                "timestamp": ts,
                "total_nodes": meta.get(str(ts), {}).get("total_nodes"),
                "formats": formats,
            }
        )
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries


def find_archive_file(timestamp: int, fmt: str, root: Path = None) -> Path | None:
    """Path to an archived photo file, or None."""
    if fmt not in FORMATS:
        return None
    root = root or ARCHIVE_DIR
    tier = scan_archive(root).get(timestamp)
    if tier is None:
        return None
    path = photo_path(tier, timestamp, fmt, root)
    return path if path.exists() else None
