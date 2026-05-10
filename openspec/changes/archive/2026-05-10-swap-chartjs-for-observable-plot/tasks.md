## 1. HTML scaffolding

- [x] 1.1 In `templates/index.html`, replace the three `<canvas id="chart-countries|chart-uas|chart-asns">` elements with `<div id="..." class="plot"></div>`
- [x] 1.2 Remove the `chart.js` UMD `<script>` tag
- [x] 1.3 Add `<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>` and `<script src="https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6"></script>` before `/static/app.js`

## 2. JS rewrite

- [x] 2.1 In `static/app.js`, remove the module-level `let charts = {}` registry
- [x] 2.2 Rewrite `makeBarChart(containerId, labels, values, label)` to build `data = labels.map((l, i) => ({ label: l, value: values[i] }))`
- [x] 2.3 Implement the chart with `Plot.plot({ height: 240, marginLeft, x: { grid: true, label }, y: { label: null }, style: { background: "transparent", color: "#e6edf3", fontSize: "12px" }, marks: [Plot.barX(data, { x: "value", y: "label", fill: "#f7931a", sort: { y: "x", reverse: true } }), Plot.ruleX([0], { stroke: "#2d333b" })] })`
- [x] 2.4 Mount via `const el = document.getElementById(containerId); el.replaceChildren(Plot.plot(...))`
- [x] 2.5 Use `marginLeft: 80` for `chart-countries` and `marginLeft: 260` for `chart-uas` / `chart-asns` to fit full labels

## 3. CSS adjustments

- [x] 3.1 In `static/app.css`, remove the `canvas { max-height: 240px }` rule
- [x] 3.2 Add `.plot { width: 100%; min-height: 240px }` and `.plot svg { display: block }`

## 4. Verification

- [x] 4.1 Run the FastAPI dev server and load the dashboard in a browser
- [x] 4.2 Confirm all three bar charts render with descending order, accent-orange bars, dark background
- [x] 4.3 Switch snapshots from the selector and confirm each chart re-renders without duplicate SVG nodes (inspect each `#chart-*` div has exactly one child)
- [x] 4.4 Confirm the Plotly globe still renders correctly (no regression)
- [x] 4.5 Check the browser console has no errors from missing `Chart`, `d3`, or `Plot` globals
