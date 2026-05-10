## Context

The dashboard's frontend renders four visual elements per snapshot: a Plotly orthographic globe (countries choropleth) and three horizontal bar charts (top countries, top user agents, top ASNs). The bar charts currently use Chart.js 4 (`static/app.js:55`, `templates/index.html:76`) and target `<canvas>` elements. Plotly is already loaded for the globe.

Two charting libraries on one page costs ~70 KB extra and yields a visual mismatch: Chart.js bars look generic next to the polished Plotly globe. The user has chosen Observable Plot (ISC) for its declarative grammar-of-graphics API and clean defaults.

## Goals / Non-Goals

**Goals:**
- Replace Chart.js with Observable Plot for the three bar charts.
- Preserve current behavior: horizontal layout, accent-orange bars, dark theme, top-N truncated labels for UAs/ASNs.
- Single source of bar-chart code (`makeBarChart`) — one function still drives all three panels.
- Keep Plotly for the globe (untouched).

**Non-Goals:**
- No backend or API changes.
- No build system / npm migration — keep CDN UMD scripts as today.
- No new chart types, no animations, no interactivity beyond default Plot tooltips.
- Not introducing a JS package manager or bundler.

## Decisions

**Decision 1: Library — Observable Plot 0.6 (UMD via CDN).**
Chosen over D3 alone (too low-level for one-liners) and ECharts/Plotly bars (heavier, less seaborn-like). Plot's `Plot.barX` with a `sort: { y: "x", reverse: true }` channel is a natural fit. Plot depends on D3, so we load both as separate UMD scripts (`d3@7` then `@observablehq/plot@0.6`).

**Decision 2: DOM element — `<div>` instead of `<canvas>`.**
Plot returns an SVG/HTML node. We replace the `<canvas id="chart-...">` with `<div id="chart-..." class="plot">` and `appendChild` the node returned by `Plot.plot(...)` after clearing the container's `innerHTML`.

**Decision 3: Drop the `charts` registry.**
Chart.js required `.destroy()` before re-render to free the canvas. Plot has no instance lifecycle — re-rendering is just `container.replaceChildren(Plot.plot(...))`. The module-level `charts = {}` map goes away.

**Decision 4: Theming via Plot `style` option + CSS.**
Plot accepts a `style` object that becomes inline CSS on the figure. We pass `{ background: "transparent", color: "var(--text)", fontSize: "12px" }` and use `color: { type: "linear" }`-free configuration since bars are single-color (`fill: "#f7931a"`). Axis tick colors inherit from `color`; grid lines via `x: { grid: true }`.

**Decision 5: Sorting and label truncation stay in the data layer.**
The API already returns `top_countries` / `top_user_agents` / `top_asns` pre-sorted. We keep the existing 30-char truncation for UA/ASN labels in `app.js` (Plot will faithfully render the truncated string). `Plot.barX` is given `sort: { y: "x", reverse: true }` to lock the visual order regardless of input order — defensive, cheap.

**Decision 6: Container height.**
Chart.js used `canvas { max-height: 240px }`. Plot uses an explicit `height` option. We pass `height: 240` to keep visual parity and remove the canvas CSS rule.

## Risks / Trade-offs

- **Risk**: CDN downtime for `d3` or `@observablehq/plot` breaks the bar charts.
  → Mitigation: use `cdn.jsdelivr.net` (same provider already used for chart.js); pin exact minor versions. Same risk class as today.

- **Risk**: SVG rendering is slower than canvas for thousands of bars.
  → Mitigation: top-N is bounded (≤20 per chart by API contract). Non-issue at this scale.

- **Risk**: Plot's default font/spacing differs subtly from Chart.js, breaking layout if panel width changes.
  → Mitigation: pass explicit `marginLeft` (~120 for UA/ASN labels, ~80 for countries) and `height: 240`; eyeball in dev.

- **Trade-off**: Two CDN scripts (d3 + plot) instead of one (chart.js). Net bundle size is similar (~90 KB gz vs ~70 KB gz) — acceptable for the visual upgrade.
