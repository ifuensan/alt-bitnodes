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
- **WHEN** a user-agent or ASN label exceeds 40 characters
- **THEN** the rendered Y-axis label is truncated to 39 characters followed by an ellipsis (`…`)

#### Scenario: Tooltip shows the full label
- **WHEN** the user hovers a bar whose label was truncated
- **THEN** the tooltip shows the complete, untruncated label together with its count

### Requirement: Dark theme styling
Bar charts SHALL be styled from the dashboard's design-system tokens and SHALL follow the active theme (dark or light), rather than hard-coded hex values.

#### Scenario: Visual styling
- **WHEN** a chart is rendered
- **THEN** bar fill comes from the `primary` token, the figure background is transparent, axis text uses the active theme's text token, and X-axis grid lines use a border token — all resolved from the current theme, not literal hex values

#### Scenario: Dynamic height
- **WHEN** a chart is rendered with `n` bars
- **THEN** its height scales with `n` (a fixed per-bar height plus top/bottom margins) so every bar has enough vertical room for its label, instead of a fixed 240px height

#### Scenario: Follows theme switch
- **WHEN** the user toggles between dark and light themes
- **THEN** the chart re-renders with the new theme's token values

### Requirement: Y-axis labels are left-aligned and monospaced
To keep variable-length categorical labels (notably Bitcoin client versions) scannable, each bar chart SHALL render its Y-axis labels left-aligned at a consistent starting position, in a monospaced font.

#### Scenario: Variable-length version labels line up
- **WHEN** the top user agents chart renders labels such as `/Satoshi:30.2.0/` and `/Satoshi:29.3.0/Knots:20260210/`
- **THEN** every label starts at the same x position (the left edge of the chart's left margin) and is drawn in a monospaced font, so the labels read as an aligned column rather than ragged right-aligned text

#### Scenario: Left margin fits the longest label
- **WHEN** a chart is rendered
- **THEN** its left margin is sized from the longest label in the dataset (up to a capped maximum), not a hard-coded constant

#### Scenario: First character is never clipped
- **WHEN** any chart renders its Y-axis labels
- **THEN** the full label is visible, including its first character — the left margin sizing accounts for the real monospace character width so no label is cut off at the left edge

### Requirement: Charts fill the container width
Each bar chart SHALL render at the width of its container instead of Observable Plot's default fixed width.

#### Scenario: Chart fills the panel
- **WHEN** a chart is rendered into its `.plot` container
- **THEN** its width is taken from the container's measured width, so bars and the X axis span the available horizontal space rather than leaving dead space on the right

### Requirement: Country chart shows full country names
The top countries chart SHALL display full country names rather than ISO-2 codes.

#### Scenario: ISO-2 codes are humanised
- **WHEN** the API returns `top_countries` with codes such as `US`, `DE`, `GB`
- **THEN** the chart's Y-axis labels read `United States`, `Germany`, `United Kingdom`

#### Scenario: Unknown codes fall back gracefully
- **WHEN** a country code cannot be resolved to a name (e.g. an anonymising-proxy code)
- **THEN** the chart falls back to showing the raw code instead of failing

### Requirement: Hover tooltip is enlarged for readability
The bar chart hover tooltip SHALL render at roughly 1.5× the base text size.

#### Scenario: Enlarged tooltip
- **WHEN** the user hovers a bar
- **THEN** the tooltip text and padding are noticeably larger than the chart's base 12px text, improving readability without obscuring neighbouring bars

### Requirement: Re-render on snapshot change
When the user selects a different snapshot, charts SHALL re-render in place without leaking previous DOM nodes.

#### Scenario: Switching snapshots
- **WHEN** the user picks a different timestamp from the snapshot selector
- **THEN** each chart container's previous contents are removed and replaced with the freshly computed Plot node, with no duplicate SVG elements remaining
