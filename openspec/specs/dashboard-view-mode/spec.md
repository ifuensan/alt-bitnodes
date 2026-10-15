# dashboard-view-mode Specification

## Purpose
The Overview's LIVE / N-DAY UNION toggle: what each view renders, how the choice persists, and how the page degrades when the union cache is not available.

## Requirements
### Requirement: The Overview offers a LIVE and an N-day UNION view

The header SHALL provide a two-state toggle, `LIVE` and `N-DAY UNION`
(N = 8). In LIVE the page renders the selected snapshot as before. In UNION
the globe, the three rankings, the side KPIs (countries, ASNs, median
height) and the node table SHALL render from the N-day union payload; the
"right now" KPI band SHALL keep the live snapshot figures; the snapshot
picker SHALL be hidden; the meta line SHALL state the number of snapshots
and the date span of the union; each affected panel SHALL carry a
"unique over N days" note; the table SHALL show a *Last seen* column.

#### Scenario: Switching to UNION
- **WHEN** the visitor activates `8-DAY UNION`
- **THEN** the panels re-render from `/api/window/8/stats` and
  `/api/window/8`, the snapshot picker disappears, the notes appear, and the
  "right now" band is unchanged

#### Scenario: Switching back to LIVE
- **WHEN** the visitor activates `LIVE`
- **THEN** the selected snapshot is reloaded and the union-only elements
  disappear

### Requirement: The chosen view persists and degrades to LIVE

The choice SHALL persist in `localStorage['pesquisa:view']` and apply on
the next visit; a `?view=union` or `?view=live` query parameter SHALL
select the view for that load (shareable link) without changing the
stored choice until the visitor toggles. If the union is not available (404), the toggle SHALL
disable the UNION button with an explanatory title and the page SHALL show
LIVE.

#### Scenario: Union cache absent
- **WHEN** `/api/window/8/stats` answers 404
- **THEN** the UNION button is disabled and the page renders the live
  snapshot without an error message
