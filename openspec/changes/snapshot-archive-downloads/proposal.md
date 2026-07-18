# Snapshot archive with Parquet/CSV downloads

## Why

Snapshots are 30-min JSONs pruned at 90 days: fine for the live dashboard,
useless for researchers who want history. A curated, tiered archive
(daily → weekly → monthly, GFS-style) preserves the network's evolution
forever at trivial disk cost, and a download screen in Parquet/CSV makes the
observatory's data reusable outside the API — including as raw material for
the future Delving Bitcoin write-up.

## What Changes

- New daily archiver job (systemd timer, dashboard side) that curates
  snapshot "photos" into three tiers and converts each to Parquet and CSV:
  - **Daily**: the last snapshot of each of the last 7 days.
  - **Weekly**: the last snapshot of each ISO week, for weeks older than the
    daily window (12 weeks by default).
  - **Monthly**: the last snapshot of each month, kept indefinitely.
  - Rotation removes only redundant finer-grain copies (a daily is dropped
    once its week has a weekly representative, a weekly once its month has a
    monthly one); archived files are never re-derivable from pruned raw
    JSONs, so nothing else is ever deleted.
- New API endpoints to list archives and download the files.
- New dashboard screen ("Archive") listing the photos with per-format
  download links, following the OSINT terminal design system.
- `pyarrow` joins the Python dependencies (Parquet writer).
- `install.sh` installs the archiver timer (dashboard-side unit; does not
  touch the crawler fingerprint).

## Capabilities

### New Capabilities
- `snapshot-archive`: the tiered curation pipeline — selection rules,
  rotation, storage layout, and Parquet/CSV conversion.
- `archive-downloads`: the public surface — list/download API endpoints and
  the dashboard screen.

### Modified Capabilities

<!-- none -->

## Impact

- New code: `archiver.py` (curation + conversion), `queries/archives.py`
  (listing for API/UI), endpoints in `app.py`, `templates/archive.html` +
  static assets, `deploy/alt-bitnodes-archive.{service,timer}`.
- `requirements.txt`: + `pyarrow`.
- Disk: ~2 MB per photo × (7 daily + 12 weekly + 12/year monthly) — MBs, not
  GBs; bounded by design.
- Downloads served through FastAPI behind nginx/CloudFront; long-cacheable
  (archived files are immutable).
