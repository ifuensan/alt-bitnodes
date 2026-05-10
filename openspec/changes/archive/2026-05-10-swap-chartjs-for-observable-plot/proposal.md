## Why

The current bar charts (top countries, user agents, ASNs) are rendered with Chart.js, which produces a generic look-and-feel and uses a different rendering model than the Plotly-based globe. We want a more polished, seaborn-like aesthetic with a declarative API while keeping interactivity and the existing dark theme.

## What Changes

- Replace Chart.js with Observable Plot for the three horizontal bar charts (`chart-countries`, `chart-uas`, `chart-asns`).
- Swap the corresponding `<canvas>` elements in `templates/index.html` for `<div>` containers that Plot can render SVG into.
- Drop the Chart.js CDN `<script>` tag; load `d3` and `@observablehq/plot` UMD bundles instead.
- Update `static/app.js` `makeBarChart` to use `Plot.plot` with `Plot.barX`, sorted descending, styled for the dark theme (transparent background, accent fill `#f7931a`, muted axes).
- Adjust `static/app.css`: remove the `canvas { max-height }` rule and add minimal styling for the new Plot containers (height, overflow).
- **BREAKING**: none — purely a frontend rendering swap; API and data shape unchanged.

## Capabilities

### New Capabilities
- `dashboard-bar-charts`: defines how the dashboard renders categorical bar charts (top countries, top user agents, top ASNs) on top of snapshot stats — library choice, layout, theming, and data contract from the existing `/api/snapshot/{ts}/stats` endpoint.

### Modified Capabilities
<!-- None — no backend specs change. -->

## Impact

- `templates/index.html`: replace 3 `<canvas>` with `<div class="plot">`, swap `chart.js` CDN for `d3` + `@observablehq/plot` CDNs.
- `static/app.js`: rewrite `makeBarChart`; remove `charts` registry / `.destroy()` (Plot returns a fresh node each call so we replace `innerHTML`).
- `static/app.css`: replace `canvas { max-height }` with `.plot` container rules.
- No backend, API, or data changes.
- External deps (CDN only, no package.json): drop `chart.js@4`, add `d3@7` and `@observablehq/plot@0.6` (both ISC-licensed, OSI-approved).
