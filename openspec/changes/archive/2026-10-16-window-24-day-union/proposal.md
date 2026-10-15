# 24-day union view and a header that fits

## Why

The LIVE / 8-DAY UNION toggle (archived 2026-10-15) answered "what does the
network look like accumulated". Eight days is the window bitnodes-style
trackers use, but for Tor and for slow-churning clearnet nodes a longer
horizon is informative: it shows how much of the 8-day population is
persistent and how much is a revolving door. ifuensan asked (2026-10-16) for
the same button with 24 days. Raw exports are kept 90 days, so the data
already exists.

Adding a third toggle button also exposed that the header does not fit: the
title, the nav tabs, the toggle, the snapshot picker, the meta line ("union
of N snapshots · date → date") and the theme toggle all share one flex row
and overflow on narrow screens.

## What Changes

- `WINDOWS_DAYS` gains 24 (`1, 3, 5, 8, 24`). The hourly job already reads
  the widest window once; the nodes cache now covers 24 days and the
  narrower windows keep being filtered from it.
- The toggle becomes `LIVE | 8-DAY UNION | 24-DAY UNION`, driven by one
  table of union windows instead of a single hard-coded `UNION_DAYS`. Panel
  notes, table note, meta line and the unique-over-N-days KPI band follow
  the selected window.
- View ids are `live`, `union8`, `union24`; the previously stored/linked
  `union` is read as `union8` so existing links and saved choices keep working.
- Each union button disables itself independently when its window is not
  cached yet (a deploy precedes the first hourly run that includes 24).
- The header is reorganised in two rows: identity and navigation on top
  (title, tabs, theme toggle), a toolbar below (view toggle, snapshot
  picker, meta line) that wraps instead of overflowing, down to phone width.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `windowed-stats`: 24 is a configured window.
- `dashboard-view-mode`: N union buttons, view ids, window-aware labels and KPI band.
- `dashboard-design-system`: header layout requirement.

## Impact

- `queries/window_stats.py`, `templates/index.html`, `static/app.{js,css}`,
  `templates/{archive,research}.html` (header rules shared, markup unchanged),
  tests, README.
- Hourly job reads ~3x more snapshots (about 930 instead of 310); it runs
  at Nice=15 and is I/O bound, so the cost is wall-clock time, not request
  latency. The node cache grows with the 24-day union.
