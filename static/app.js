const fmt = new Intl.NumberFormat("en-US");
let currentNodes = [];
let globeInitialized = false;

// ISO-2 country code → full English name. Falls back to the raw code for
// unknown / invalid codes (e.g. anonymising proxies).
const _regionNames = new Intl.DisplayNames(["en"], { type: "region" });
function countryName(code) {
  if (!code) return code;
  try {
    return _regionNames.of(code) || code;
  } catch {
    return code;
  }
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function updateGlobe(stats) {
  const locations = stats.countries_iso3.map(([iso3]) => iso3);
  const counts = stats.countries_iso3.map(([, c]) => c);
  const data = [{
    type: "choropleth",
    locationmode: "ISO-3",
    locations,
    z: counts,
    colorscale: [
      [0,    "#1a2a1a"],
      [0.25, "#244c24"],
      [0.5,  "#3a8a3a"],
      [0.75, "#7ad57a"],
      [1,    "#cdf5cd"],
    ],
    showscale: false,
    marker: { line: { color: "#0e1116", width: 0.4 } },
    hovertemplate: "<b>%{location}</b><br>%{z} nodes<extra></extra>",
  }];
  const layout = {
    geo: {
      projection: { type: "orthographic", rotation: { lon: -30, lat: 25 } },
      showocean: true, oceancolor: "#0a0d12",
      showland: true,  landcolor: "#161b22",
      showcountries: true, countrycolor: "#0e1116",
      showcoastlines: false,
      showframe: false,
      bgcolor: "#161b22",
    },
    paper_bgcolor: "#161b22",
    plot_bgcolor: "#161b22",
    margin: { l: 0, r: 0, t: 0, b: 0 },
    font: { color: "#e6edf3" },
  };
  const config = { displayModeBar: false, responsive: true };
  if (globeInitialized) {
    Plotly.react("globe", data, layout, config);
  } else {
    Plotly.newPlot("globe", data, layout, config);
    globeInitialized = true;
  }
}

const BAR_HEIGHT = 28;
const BAR_MARGIN_TOP = 10;
const BAR_MARGIN_BOTTOM = 34;
const LABEL_MAX = 40;
const MONO_FONT = "ui-monospace, SFMono-Regular, Menlo, monospace";
// Width of one monospace char at 12px (measured ~7.2px; round up so the
// computed left margin never under-sizes and clips the first character).
const MONO_CHAR_PX = 7.5;
const LABEL_PAD_LEFT = 14;

function makeBarChart(containerId, labels, values, label) {
  const el = document.getElementById(containerId);
  const data = labels.map((l, i) => ({
    label: l.length > LABEL_MAX ? l.slice(0, LABEL_MAX - 1) + "…" : l,
    full: l,
    value: values[i],
  }));
  // Height scales with bar count so labels never overlap.
  const height = data.length * BAR_HEIGHT + BAR_MARGIN_TOP + BAR_MARGIN_BOTTOM;
  // Fill the container's width instead of Plot's ~640px default.
  const width = el.clientWidth || 640;
  // Left margin sized from the longest (displayed) label, with padding so
  // the first character is never clipped. Capped so a pathological label
  // can't eat the whole bar width.
  const longest = data.reduce((m, d) => Math.max(m, d.label.length), 0);
  const marginLeft = Math.min(longest * MONO_CHAR_PX + LABEL_PAD_LEFT, 420);
  const chart = Plot.plot({
    width,
    height,
    marginTop: BAR_MARGIN_TOP,
    marginBottom: BAR_MARGIN_BOTTOM,
    marginLeft,
    marginRight: 24,
    x: { grid: true, label },
    y: { label: null },
    style: { background: "transparent", color: "#e6edf3", fontSize: "12px" },
    marks: [
      // Left-aligned, monospaced Y-axis labels: variable-length version
      // strings read as an aligned column instead of ragged right-aligned
      // text. dx pulls the label to the SVG's left edge (+8px padding).
      Plot.axisY({
        textAnchor: "start",
        fontFamily: MONO_FONT,
        tickSize: 0,
        dx: -marginLeft + 8,
      }),
      Plot.barX(data, {
        x: "value",
        y: "label",
        fill: "#f7931a",
        sort: { y: "x", reverse: true },
      }),
      Plot.tip(data, Plot.pointerY({
        x: "value",
        y: "label",
        title: (d) => `${d.full}\n${d.value}`,
        fill: "#0e1116",
        stroke: "#2d333b",
        // ~1.5x the base 12px text / 8px padding for easier reading on hover.
        fontSize: 18,
        textPadding: 12,
        lineHeight: 1.3,
      })),
      Plot.ruleX([0], { stroke: "#2d333b" }),
    ],
  });
  el.replaceChildren(chart);
}

function updateTable(nodes) {
  const tbody = document.querySelector("#nodes-table tbody");
  tbody.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const n of nodes.slice(0, 1000)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${n.address}</td>
      <td>${n.port}</td>
      <td>${n.user_agent || ""}</td>
      <td>${n.country || ""}</td>
      <td>${n.city || ""}</td>
      <td>${n.asn || ""} ${n.asn_name || ""}</td>
      <td>${n.height}</td>
    `;
    frag.appendChild(tr);
  }
  tbody.appendChild(frag);
}

function applyFilter() {
  const q = document.getElementById("filter").value.toLowerCase();
  if (!q) return updateTable(currentNodes);
  const filtered = currentNodes.filter(n =>
    [n.address, n.country, n.city, n.asn, n.asn_name, n.user_agent]
      .filter(Boolean).join(" ").toLowerCase().includes(q)
  );
  updateTable(filtered);
}

async function loadSnapshot(ts) {
  const t = Number(ts);
  if (!Number.isInteger(t) || t < 0) {
    throw new Error(`invalid snapshot timestamp: ${ts}`);
  }
  const [snap, stats] = await Promise.all([
    fetchJSON(`/api/snapshot/${t}`),
    fetchJSON(`/api/snapshot/${t}/stats`),
  ]);
  currentNodes = snap.nodes;
  document.getElementById("kpi-total").textContent = fmt.format(stats.total);
  document.getElementById("kpi-countries").textContent = fmt.format(stats.countries_total);
  document.getElementById("kpi-asns").textContent = fmt.format(stats.asns_total);
  document.getElementById("kpi-height").textContent = stats.median_height ?? "—";
  document.getElementById("kpi-latency").textContent = stats.median_latency_ms ?? "—";
  document.getElementById("snapshot-meta").textContent =
    new Date(ts * 1000).toISOString().replace("T", " ").slice(0, 19) + " UTC";

  makeBarChart("chart-countries",
    stats.top_countries.map(([k]) => countryName(k)),
    stats.top_countries.map(([, v]) => v),
    "nodes");
  makeBarChart("chart-uas",
    stats.top_user_agents.map(([k]) => k),
    stats.top_user_agents.map(([, v]) => v),
    "nodes");
  makeBarChart("chart-asns",
    stats.top_asns.map(([k]) => k),
    stats.top_asns.map(([, v]) => v),
    "nodes");

  updateGlobe(stats);
  updateTable(currentNodes);
  loadLeaderboard().catch(err => console.warn("leaderboard failed", err));
}

async function loadLeaderboard() {
  const data = await fetchJSON("/api/v1/nodes/leaderboard/?limit=20");
  const tbody = document.querySelector("#leaderboard-table tbody");
  tbody.innerHTML = "";
  if (!data.results.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="7" style="opacity:.6;text-align:center">No RTT samples yet — ingest may not have run, or upstream pong sniffer is offline.</td>`;
    tbody.appendChild(tr);
    return;
  }
  data.results.forEach((n, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${i + 1}</td><td>${n.address}</td><td>${n.port}</td><td>${n.country ?? ""}</td><td>${n.asn ?? ""}</td><td>${n.user_agent ?? ""}</td><td>${n.latency_ms}</td>`;
    tbody.appendChild(tr);
  });
}

async function init() {
  const { timestamps } = await fetchJSON("/api/snapshots");
  const select = document.getElementById("snapshot-select");
  for (const ts of [...timestamps].reverse()) {
    const opt = document.createElement("option");
    opt.value = ts;
    opt.textContent = new Date(ts * 1000).toISOString().replace("T", " ").slice(0, 19);
    select.appendChild(opt);
  }
  select.addEventListener("change", e => loadSnapshot(Number.parseInt(e.target.value, 10)));
  document.getElementById("filter").addEventListener("input", applyFilter);

  if (timestamps.length) {
    select.value = timestamps[timestamps.length - 1];
    await loadSnapshot(timestamps[timestamps.length - 1]);
  }
}

try {
  await init();
} catch (err) {
  console.error(err);
  document.getElementById("snapshot-meta").textContent = "error: " + err.message;
}
