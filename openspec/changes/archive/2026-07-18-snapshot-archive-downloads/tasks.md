# Tasks — snapshot-archive-downloads

## 1. Data layer + archiver

- [x] 1.1 `queries/archives.py`: tier selection (last snapshot per
      day/ISO-week/month, windows 7d/12w/∞), keep-set computation, and
      archive listing (tier, date, ts, sizes) from the archive dir.
- [x] 1.2 `archiver.py`: materialise missing photos (Parquet via pyarrow,
      CSV via stdlib, 15 FIELDS columns), rotate per keep-set, idempotent,
      per-snapshot error isolation; add `pyarrow` to requirements.txt.
- [x] 1.3 Tests: tier selection edge cases (week/month boundaries, gaps),
      rotation never orphans a period, conversion round-trip CSV≡Parquet,
      idempotent re-run.

## 2. API + screen

- [x] 2.1 `app.py`: `GET /api/v1/archives/` listing +
      `GET /api/v1/archives/{ts}.{csv,parquet}` FileResponse with immutable
      cache headers; 404s for unknown ts/format.
- [x] 2.2 `templates/archive.html` + static assets: Archive screen per the
      OSINT terminal design system, grouped by tier, empty state; link from
      the main page.
- [x] 2.3 Endpoint tests (listing, download headers, 404s) with a fixture
      archive dir.

## 3. Deploy

- [x] 3.1 `deploy/alt-bitnodes-archive.service` + `.timer` (oneshot, daily
      03:30 UTC + jitter, dashboard venv/user, placeholder substitution);
      wire into `install.sh` (install, sed, enable — crawler fingerprint
      untouched).
- [x] 3.2 Commit, push, CI green; verify deploy log shows "Crawler
      unchanged".
- [x] 3.3 Verify on production: first archiver run backfills, listing
      non-empty, CSV and Parquet download correctly, screen renders.

## 4. Bookkeeping

- [x] 4.1 Update docs/follow-ups.md if anything was deferred; archive the
      change and sync both specs.
