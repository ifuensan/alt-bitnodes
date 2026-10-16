## ADDED Requirements

### Requirement: The Overview offers a BEST UNION view

The toggle SHALL include a `BEST UNION` button (view id `best`) after the
window buttons. In that view the globe, rankings, side KPIs and node table
SHALL render from `/api/best/stats` and `/api/best`; the lower KPI band SHALL
read "Unique up to <as_of>" with the frozen totals (including Tor and I2P);
panel and table notes SHALL read "unique up to <as_of>"; the snapshot picker
SHALL be hidden and the *Last seen* column shown; the meta line SHALL state
the snapshot count and the real date span. The view id SHALL persist and be
accepted in `?view=` like the others. If the union is not built (404) the
button SHALL be disabled with an explanatory title and the page SHALL show
LIVE, without affecting the other buttons.

#### Scenario: Switching to BEST UNION
- **WHEN** the visitor activates `BEST UNION`
- **THEN** the panels re-render from the frozen union, the lower band shows
  its Tor and I2P figures, and no "over N days" label remains

#### Scenario: Union not built on this host
- **WHEN** `/api/best/stats` answers 404
- **THEN** `BEST UNION` is disabled and the other union buttons still work
