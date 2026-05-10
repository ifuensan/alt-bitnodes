# dashboard-bar-charts

## Purpose

Defines how the dashboard renders categorical bar charts (top countries, top user agents, top ASNs) on top of snapshot stats — library choice, layout, theming, and data contract from the existing `/api/snapshot/{ts}/stats` endpoint.

## Requirements

### Requirement: Bar charts use Observable Plot
The dashboard SHALL render the three categorical bar charts (top countries, top user agents, top ASNs) using Observable Plot. Chart.js MUST NOT be loaded by the page.

#### Scenario: Page loads required libraries
- **WHEN** a user opens the dashboard
- **THEN** `index.html` includes `<script>` tags for `d3` and `@observablehq/plot` from a CDN, and does NOT include any `chart.js` script tag

#### Scenario: Bar chart renders into a div
- **WHEN** snapshot stats are received and a bar chart is rendered
- **THEN** the chart is appended as an SVG/HTML node into a `<div>` container (e.g., `#chart-countries`), not a `<canvas>`

### Requirement: Horizontal bar layout with descending sort
Each bar chart SHALL display categorical labels on the Y axis and numeric counts on the X axis, sorted descending by count.

#### Scenario: Top countries chart
- **WHEN** the API returns `top_countries` as `[[label, count], ...]`
- **THEN** the chart shows one horizontal bar per entry, ordered from highest count at the top to lowest at the bottom

#### Scenario: Long category labels are truncated
- **WHEN** a user-agent or ASN label exceeds 32 characters
- **THEN** the rendered Y-axis label is truncated to 30 characters followed by an ellipsis (`…`)

### Requirement: Dark theme styling
Bar charts SHALL be styled to match the dashboard's dark theme.

#### Scenario: Visual styling
- **WHEN** a chart is rendered
- **THEN** bars use the accent fill `#f7931a`, the figure background is transparent, axis text uses the page text color, and X-axis grid lines are visible

#### Scenario: Fixed height
- **WHEN** a chart is rendered
- **THEN** its height is fixed at 240px to match the panel layout

### Requirement: Re-render on snapshot change
When the user selects a different snapshot, charts SHALL re-render in place without leaking previous DOM nodes.

#### Scenario: Switching snapshots
- **WHEN** the user picks a different timestamp from the snapshot selector
- **THEN** each chart container's previous contents are removed and replaced with the freshly computed Plot node, with no duplicate SVG elements remaining
