"""Materialise the tiered snapshot archive as Parquet + CSV photos.

Run daily by alt-bitnodes-archive.timer. Idempotent: photos are written
only when missing, rotation removes only copies whose period already has a
materialised representative, and a re-run with no new snapshots changes
nothing. One broken snapshot never aborts the run.
"""

import csv
import datetime as dt
import json
import logging
import sys

import pyarrow as pa
import pyarrow.parquet as pq

from queries.archives import (
    ARCHIVE_DIR,
    META_FILE,
    TIERS,
    compute_keep,
    photo_path,
    scan_archive,
    tier_and_period,
    utc_date,
)
from queries.config import EXPORT_DIR, FIELDS
from queries.snapshots import list_snapshots

logger = logging.getLogger("archiver")


def _load_rows(timestamp: int) -> list[list]:
    # Deliberately not queries.load_snapshot: no point pushing archive-only
    # reads through the API's lru_cache.
    return json.loads((EXPORT_DIR / f"{timestamp}.json").read_text())


def _photo_complete(tier: str, timestamp: int) -> bool:
    return all(photo_path(tier, timestamp, f).exists() for f in ("parquet", "csv"))


def _write_photo(tier: str, timestamp: int, rows: list[list]) -> None:
    """Materialise both formats (idempotent per format). Writes go to a temp
    file then rename, so a crash/ENOSPC never leaves a truncated photo that
    scan_archive would count as done and rotation would make permanent."""
    columns = {field: [row[i] for row in rows] for i, field in enumerate(FIELDS)}

    parquet_path = photo_path(tier, timestamp, "parquet")
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    if not parquet_path.exists():
        tmp = parquet_path.with_suffix(".parquet.tmp")
        pq.write_table(pa.table(columns), tmp)
        tmp.replace(parquet_path)

    csv_path = photo_path(tier, timestamp, "csv")
    if not csv_path.exists():
        tmp = csv_path.with_suffix(".csv.tmp")
        with tmp.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(FIELDS)
            writer.writerows(rows)
        tmp.replace(csv_path)


def run(today: dt.date = None) -> dict:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    raw = set(list_snapshots())
    archived = scan_archive()
    keep = compute_keep(raw | set(archived), today)

    written = skipped = moved = removed = 0
    meta = {}
    meta_path = ARCHIVE_DIR / META_FILE
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            meta = {}

    # Materialise (or re-tier) every keeper.
    for ts, tier in sorted(keep.items()):
        current_tier = archived.get(ts)
        if current_tier == tier:
            # Already in the right tier — but repair a missing/half-written
            # format (crash between the two writes) while the raw is still on
            # disk; otherwise rotation would make the gap permanent.
            if ts in raw and not _photo_complete(tier, ts):
                try:
                    _write_photo(tier, ts, _load_rows(ts))
                    written += 1
                except (OSError, ValueError, json.JSONDecodeError) as err:
                    logger.warning("failed to repair %d: %s", ts, err)
                    skipped += 1
            continue
        if current_tier is not None:
            # Cascade to a coarser tier by moving the existing files.
            for fmt in ("parquet", "csv"):
                src = photo_path(current_tier, ts, fmt)
                if src.exists():
                    dst = photo_path(tier, ts, fmt)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    src.rename(dst)
            moved += 1
            continue
        if ts not in raw:
            logger.warning("keeper %d has no raw snapshot and no archive", ts)
            skipped += 1
            continue
        try:
            rows = _load_rows(ts)
            _write_photo(tier, ts, rows)
            meta[str(ts)] = {"total_nodes": len(rows)}
            written += 1
        except (OSError, ValueError, json.JSONDecodeError) as err:
            logger.warning("failed to archive %d: %s", ts, err)
            skipped += 1

    # Rotate: drop archived photos that are no longer keepers, but only if
    # their period's representative is materialised (never orphan a period).
    now_archived = scan_archive()
    for ts, tier in archived.items():
        if ts in keep:
            continue
        placed = tier_and_period(utc_date(ts), today)
        if placed is not None:
            keeper = next(
                (k for k, t in keep.items()
                 if t == placed[0] and tier_and_period(utc_date(k), today) == placed),
                None,
            )
            if keeper is None or keeper not in now_archived:
                continue
        for fmt in ("parquet", "csv"):
            path = photo_path(tier, ts, fmt)
            if path.exists():
                path.unlink()
        meta.pop(str(ts), None)
        removed += 1

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, sort_keys=True))

    stats = {"written": written, "moved": moved, "removed": removed, "skipped": skipped}
    logger.info("archive run: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run()
    print(json.dumps(result))
    sys.exit(0)
