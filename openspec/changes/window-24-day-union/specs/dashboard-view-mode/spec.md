## MODIFIED Requirements

### Requirement: The Overview offers a LIVE and an N-day UNION view

The header toolbar SHALL provide a toggle with a `LIVE` button and one union
button per configured union window: `8-DAY UNION` and `24-DAY UNION`. In
LIVE the page renders the selected snapshot as before. In a union view the
globe, the three rankings, the side KPIs (countries, ASNs, median height)
and the node table SHALL render from that window's union payload; the
"right now" KPI band SHALL keep the live snapshot figures; the lower KPI band
SHALL show the unique-over-N-days figures of the active window (8 days when
LIVE); the snapshot picker SHALL be hidden; the meta line SHALL state the
number of snapshots and the date span of the union; each affected panel and
the table note SHALL name the active window ("unique over N days"); the
table SHALL show a *Last seen* column.

#### Scenario: Switching to the 24-day union
- **WHEN** the visitor activates `24-DAY UNION`
- **THEN** the panels re-render from `/api/window/24/stats` and
  `/api/window/24`, the notes read "unique over 24 days", the lower KPI
  band shows the 24-day totals, and the "right now" band is unchanged

#### Scenario: Switching between union windows
- **WHEN** the visitor goes from `8-DAY UNION` to `24-DAY UNION`
- **THEN** only the active button changes state and every figure and note
  now refers to 24 days, with no stale 8-day label left on the page

#### Scenario: Switching back to LIVE
- **WHEN** the visitor activates `LIVE`
- **THEN** the selected snapshot is reloaded and the union-only elements
  disappear

### Requirement: The chosen view persists and degrades to LIVE

The choice SHALL persist in `localStorage['pesquisa:view']` as `live`,
`union8` or `union24` and apply on the next visit; a `?view=` query
parameter with one of those values SHALL select the view for that load
(shareable link) without changing the stored choice until the visitor
toggles. The legacy value `union` SHALL be read as `union8`; any other value
SHALL be read as `live`. Availability SHALL be per window: if a window's
union is not available (404) its button SHALL be disabled with an
explanatory title and the page SHALL show LIVE, while the other union
buttons keep working.

#### Scenario: Union cache absent
- **WHEN** `/api/window/8/stats` answers 404
- **THEN** the 8-DAY UNION button is disabled and the page renders the live
  snapshot without an error message

#### Scenario: Only the 24-day window is missing
- **WHEN** `/api/window/24/stats` answers 404 and the 8-day window is cached
- **THEN** `24-DAY UNION` is disabled and `8-DAY UNION` still works

#### Scenario: Legacy stored value
- **WHEN** `pesquisa:view` holds `union` or the URL carries `?view=union`
- **THEN** the page opens the 8-day union
