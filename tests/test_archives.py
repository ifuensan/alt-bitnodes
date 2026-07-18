import csv
import datetime as dt

import pyarrow.parquet as pq

import archiver
from queries.archives import (
    compute_keep,
    find_archive_file,
    list_archives,
    photo_path,
    scan_archive,
    tier_and_period,
)
from tests.conftest import make_row

TODAY = dt.date(2026, 7, 18)


def ts_at(date: dt.date, hour: int = 12) -> int:
    return int(
        dt.datetime(date.year, date.month, date.day, hour, tzinfo=dt.timezone.utc).timestamp()
    )


class TestTierAndPeriod:
    def test_today_not_archivable(self):
        assert tier_and_period(TODAY, TODAY) is None

    def test_daily_window(self):
        assert tier_and_period(TODAY - dt.timedelta(days=1), TODAY) == ("daily", "2026-07-17")
        assert tier_and_period(TODAY - dt.timedelta(days=7), TODAY)[0] == "daily"

    def test_weekly_window(self):
        assert tier_and_period(TODAY - dt.timedelta(days=8), TODAY)[0] == "weekly"
        assert tier_and_period(TODAY - dt.timedelta(days=7 + 12 * 7), TODAY)[0] == "weekly"

    def test_monthly_beyond(self):
        tier, period = tier_and_period(TODAY - dt.timedelta(days=7 + 12 * 7 + 1), TODAY)
        assert tier == "monthly"
        assert period == "2026-04"

    def test_iso_week_key_crosses_year(self):
        # 2026-01-01 falls in ISO week 2026-W01; 2027-01-01 in 2026-W53.
        assert tier_and_period(dt.date(2027, 1, 1), dt.date(2027, 8, 1)) == (
            "monthly",
            "2027-01",
        )


class TestComputeKeep:
    def test_picks_last_snapshot_per_day(self):
        d = TODAY - dt.timedelta(days=2)
        early, late = ts_at(d, 3), ts_at(d, 22)
        keep = compute_keep([early, late], TODAY)
        assert keep == {late: "daily"}

    def test_one_keeper_per_week(self):
        base = TODAY - dt.timedelta(days=30)
        monday = base - dt.timedelta(days=base.weekday())
        stamps = [ts_at(monday + dt.timedelta(days=i)) for i in range(7)]
        keep = compute_keep(stamps, TODAY)
        weekly = [ts for ts, tier in keep.items() if tier == "weekly"]
        assert weekly == [stamps[-1]]

    def test_gap_days_are_fine(self):
        keep = compute_keep([ts_at(TODAY - dt.timedelta(days=3))], TODAY)
        assert list(keep.values()) == ["daily"]


class TestArchiverRun:
    def _write_raw(self, write_snapshot, date, hour=12, n=3):
        ts = ts_at(date, hour)
        write_snapshot(ts, [make_row(port=8333 + i) for i in range(n)])
        return ts

    def test_backfill_and_formats_match(self, write_snapshot, archive_dir):
        ts = self._write_raw(write_snapshot, TODAY - dt.timedelta(days=1), n=4)
        stats = archiver.run(today=TODAY)
        assert stats["written"] == 1

        csv_path = photo_path("daily", ts, "csv")
        parquet_path = photo_path("daily", ts, "parquet")
        with csv_path.open() as f:
            rows = list(csv.reader(f))
        table = pq.read_table(parquet_path)
        assert len(rows) - 1 == table.num_rows == 4
        assert rows[0] == table.column_names
        assert table.column("port").to_pylist() == [8333, 8334, 8335, 8336]

        listing = list_archives()
        assert listing[0]["total_nodes"] == 4
        assert set(listing[0]["formats"]) == {"csv", "parquet"}

    def test_idempotent_rerun(self, write_snapshot, archive_dir):
        self._write_raw(write_snapshot, TODAY - dt.timedelta(days=1))
        archiver.run(today=TODAY)
        before = {p: p.stat().st_mtime_ns for p in archive_dir.rglob("*") if p.is_file()}
        stats = archiver.run(today=TODAY)
        after = {p: p.stat().st_mtime_ns for p in archive_dir.rglob("*") if p.is_file()}
        assert stats["written"] == 0 and stats["removed"] == 0
        assert {p for p in before} == {p for p in after}
        unchanged = [p for p in before if p.name != "meta.json"]
        assert all(before[p] == after[p] for p in unchanged)

    def test_cascade_daily_to_weekly_moves_files(self, write_snapshot, archive_dir):
        d = TODAY - dt.timedelta(days=6)
        ts = self._write_raw(write_snapshot, d)
        archiver.run(today=TODAY)
        assert scan_archive()[ts] == "daily"
        # A week later the photo has aged into the weekly tier.
        later = TODAY + dt.timedelta(days=7)
        stats = archiver.run(today=later)
        assert stats["moved"] == 1
        assert scan_archive()[ts] == "weekly"
        assert find_archive_file(ts, "csv") is not None

    def test_rotation_drops_redundant_daily_keeps_last_of_week(
        self, write_snapshot, archive_dir
    ):
        base = TODAY - dt.timedelta(days=1)
        monday = base - dt.timedelta(days=base.weekday())
        stamps = [
            self._write_raw(write_snapshot, monday + dt.timedelta(days=i))
            for i in range(5)
        ]
        archiver.run(today=TODAY)
        assert all(scan_archive()[ts] == "daily" for ts in stamps)

        # Two weeks later: only the last of that week survives, as weekly.
        later = TODAY + dt.timedelta(days=14)
        archiver.run(today=later)
        archived = scan_archive()
        assert archived.get(stamps[-1]) == "weekly"
        assert all(ts not in archived for ts in stamps[:-1])

    def test_never_orphans_a_period(self, write_snapshot, archive_dir, export_dir):
        d = TODAY - dt.timedelta(days=2)
        ts = self._write_raw(write_snapshot, d)
        archiver.run(today=TODAY)
        # Raw pruned; much later the photo should survive by cascading,
        # never be deleted.
        (export_dir / f"{ts}.json").unlink()
        far = TODAY + dt.timedelta(days=200)
        archiver.run(today=far)
        assert ts in scan_archive()
        assert scan_archive()[ts] == "monthly"
