# Design — 24-day union and header

## One table of union windows

The frontend had one constant (`UNION_DAYS = 8`) threaded through the fetch
URLs, the notes and the KPI band. It becomes
`UNION_VIEWS = { union8: 8, union24: 24 }`; every consumer receives the
window from the active view. Adding a third window later is one entry plus
one button. The buttons are generated in markup (`data-view="union24"`,
`data-days="24"`) and the script reads `data-days`, so the table in JS is
the only place that maps view id to days.

## Backward compatibility of view ids

`pesquisa:view` and `?view=` used `union` for the 8-day view. `normalizeView`
maps `union` → `union8`; unknown values fall back to `live`. Persisting
writes the new id.

## The KPI band follows the view

The lower band ("Unique over N days") read the 8-day window unconditionally.
With two union windows that would contradict the panels below it. The band
now shows the window of the active union view and the 8-day window when the
view is LIVE. The data comes from the single `/api/v1/stats/window` fetch,
kept in memory, so switching views re-renders it without a request.

## Independent degradation

Each union button carries its own availability. A 404 on one window disables
that button only. Right after the deploy the stats cache still lacks 24
until the next hourly run, so 24-DAY UNION is disabled and 8-DAY keeps
working; the nodes cache check (`days > widest` → 404) keeps the two
endpoints in agreement while the caches are mid-rewrite.

## Header

Two rows. Row one: title, tabs, theme toggle pushed right. Row two (only the
Overview has it): a toolbar containing the view toggle, the snapshot picker
and the meta line. The toolbar is `flex-wrap`; the meta line is allowed to
shrink and wrap and aligns right when there is room, so the longest string
(union span) never forces horizontal scroll. The other pages keep their
single row with the same rules (title, tabs, theme toggle right), so the
three pages stay visually aligned. At phone width the tabs and toggle buttons
wrap onto their own lines.

## Cost

Reading 24 days of snapshots triples the job's input. The job is hourly,
niced and write-atomic; no request path changes. The first run on the
production VM is timed and recorded.
