// Research page: exploratory charts over the collector-precomputed datasets.
// Sections fetch and render independently — one empty dataset never blocks
// the others (research-page spec).

const fmt = new Intl.NumberFormat("en-US");

const NETWORKS = ["ipv4", "ipv6", "tor", "i2p"];
const MONO_FONT_STACK = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

function themeTokens() {
  const cs = getComputedStyle(document.documentElement);
  const t = (name) => cs.getPropertyValue(name).trim();
  return {
    surface: t("--surface"),
    border: t("--border"),
    text: t("--text"),
    muted: t("--muted"),
    primary: t("--primary"),
    ok: t("--ok"),
    warn: t("--warn"),
    accent: t("--accent"),
  };
}

// One color per network class, shared by every chart on the page (and by the
// overview tiles' ordering): ipv4 orange, ipv6 amber, tor pink, i2p green.
function networkColors() {
  const tok = themeTokens();
  return { ipv4: tok.primary, ipv6: tok.warn, tor: tok.accent, i2p: tok.ok };
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function note(id, text) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.hidden = false;
}

// --- Section 1: block propagation ----------------------------------------

let propAggregate = null;   // cached /api/propagation payload
let propSelected = null;    // hash of the drilled-down block, or null

function ecdfPoints(ecdfByNet) {
  const pts = [];
  for (const net of NETWORKS) {
    for (const [t, frac] of ecdfByNet?.[net] || []) {
      // t=0 is the first announcer itself; clamp for the log scale.
      pts.push({ t: Math.max(1, t), frac, net });
    }
  }
  return pts;
}

function renderPropagationChart(ecdfByNet, title, yLabel = "fraction of announcers") {
  const el = document.getElementById("chart-propagation");
  const tok = themeTokens();
  const colors = networkColors();
  const data = ecdfPoints(ecdfByNet);
  if (!data.length) {
    el.replaceChildren();
    return;
  }
  const chart = Plot.plot({
    width: el.clientWidth || 900,
    height: 320,
    style: { background: "transparent", color: tok.text, fontSize: "12px", fontFamily: MONO_FONT_STACK },
    x: { type: "log", grid: true, label: "ms since first observed announcement (log)" },
    y: { domain: [0, 1], grid: true, label: yLabel, tickFormat: ".0%" },
    color: {
      domain: NETWORKS,
      range: NETWORKS.map((n) => colors[n]),
      legend: true,
    },
    marks: [
      Plot.line(data, {
        x: "t", y: "frac", stroke: "net", curve: "step-after", strokeWidth: 1.8,
      }),
      Plot.tip(data, Plot.pointer({
        x: "t", y: "frac",
        title: (d) => `${d.net}\n${fmt.format(d.t)} ms — ${(d.frac * 100).toFixed(1)}%`,
        fill: tok.surface, stroke: tok.border,
      })),
    ],
  });
  el.replaceChildren(chart);
  document.getElementById("prop-caption").textContent = title;
}

function shortHash(h) {
  return h.slice(0, 8) + "…" + h.slice(-8);
}

function renderBlockTable(blocks) {
  const tbody = document.querySelector("#prop-blocks tbody");
  tbody.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const b of blocks) {
    const tr = document.createElement("tr");
    tr.dataset.hash = b.hash;
    const p50 = (net) => b.networks?.[net]?.p50 ?? "—";
    const cells = [
      b.height_estimate != null ? fmt.format(b.height_estimate) : "—",
      shortHash(b.hash),
      fmt.format(b.count),
      String(p50("ipv4")), String(p50("tor")), String(p50("i2p")),
    ];
    for (const [i, text] of cells.entries()) {
      const td = document.createElement("td");
      td.textContent = text;
      if (i === 1) td.className = "hash";
      tr.appendChild(td);
    }
    tr.addEventListener("click", () => selectBlock(b.hash));
    frag.appendChild(tr);
  }
  tbody.appendChild(frag);
}

function markSelectedRow() {
  document.querySelectorAll("#prop-blocks tbody tr").forEach((tr) => {
    tr.classList.toggle("selected", tr.dataset.hash === propSelected);
  });
}

async function selectBlock(hash) {
  try {
    const doc = await fetchJSON(`/api/propagation/block/${hash}`);
    propSelected = hash;
    markSelectedRow();
    document.getElementById("prop-aggregate").hidden = false;
    const nets = Object.fromEntries(
      NETWORKS.map((n) => [n, doc.networks?.[n]?.ecdf || []]));
    renderPropagationChart(nets, `Block ${shortHash(hash)} — ${fmt.format(doc.count)} announcers. ${propAggregate.definition}`);
  } catch (e) {
    /* block file rotated away — keep current view */
  }
}

function showAggregate() {
  propSelected = null;
  markSelectedRow();
  document.getElementById("prop-aggregate").hidden = true;
  renderPropagationChart(
    propAggregate.ecdf,
    `Median across the last ${propAggregate.blocks.length} collected blocks (equal weight per block). ${propAggregate.definition}`,
    "fraction of announcers (median block)");
}

async function loadPropagation() {
  try {
    propAggregate = await fetchJSON("/api/propagation");
  } catch (e) {
    note("prop-note", "propagation data unavailable: " + e.message);
    return;
  }
  if (!propAggregate.blocks.length) {
    note("prop-note", "No propagation data collected yet — the collector persists each block ~30 minutes after its first announcement.");
    return;
  }
  document.getElementById("prop-aggregate").addEventListener("click", showAggregate);
  renderBlockTable(propAggregate.blocks);
  showAggregate();
}

// --- Section 2: services adoption -----------------------------------------

let servicesPayload = null;
let servicesByNetwork = false;

function renderServicesBars() {
  const el = document.getElementById("chart-services");
  const tok = themeTokens();
  const colors = networkColors();
  const latest = servicesPayload.latest;
  const flags = [...latest.flags].sort((a, b) => b.pct - a.pct);
  let chart;
  if (!servicesByNetwork) {
    const data = flags.map((f) => ({ flag: f.flag, pct: f.pct, count: f.count, bit: f.bit }));
    if (latest.other.count) {
      data.push({ flag: "other bits", pct: latest.other.pct, count: latest.other.count, bit: null });
    }
    chart = Plot.plot({
      width: el.clientWidth || 900,
      height: data.length * 34 + 50,
      marginLeft: 190,
      style: { background: "transparent", color: tok.text, fontSize: "12px", fontFamily: MONO_FONT_STACK },
      x: { domain: [0, 100], grid: true, label: "% of reachable nodes" },
      y: { label: null },
      marks: [
        Plot.barX(data, { x: "pct", y: "flag", fill: tok.primary, sort: { y: "x", reverse: true } }),
        Plot.tip(data, Plot.pointerY({
          x: "pct", y: "flag",
          title: (d) => `${d.flag}${d.bit != null ? ` (bit ${d.bit})` : ""}\n${fmt.format(d.count)} nodes — ${d.pct}%`,
          fill: tok.surface, stroke: tok.border,
        })),
      ],
    });
  } else {
    const total = latest.total || 1;
    const data = [];
    for (const f of flags) {
      for (const net of NETWORKS) {
        data.push({ flag: f.flag, net, count: f.by_network[net] });
      }
    }
    chart = Plot.plot({
      width: el.clientWidth || 900,
      height: flags.length * 90 + 60,
      marginLeft: 190,
      style: { background: "transparent", color: tok.text, fontSize: "12px", fontFamily: MONO_FONT_STACK },
      x: { grid: true, label: "nodes" },
      y: { label: null },
      fy: { label: null },
      color: { domain: NETWORKS, range: NETWORKS.map((n) => colors[n]), legend: true },
      marks: [
        Plot.barX(data, { x: "count", y: "net", fy: "flag", fill: "net" }),
        Plot.tip(data, Plot.pointer({
          x: "count", y: "net", fy: "flag",
          title: (d) => `${d.flag} — ${d.net}\n${fmt.format(d.count)} nodes (${(100 * d.count / total).toFixed(1)}% of all)`,
          fill: tok.surface, stroke: tok.border,
        })),
      ],
    });
  }
  el.replaceChildren(chart);
}

function renderServicesHistory() {
  const el = document.getElementById("chart-services-history");
  const days = servicesPayload.series.days;
  if (days.length < 2) {
    el.replaceChildren();
    note("services-note", "Adoption-over-time appears once the daily series has at least two days.");
    return;
  }
  const tok = themeTokens();
  const data = [];
  for (const d of days) {
    for (const [flag, pct] of Object.entries(d.flags)) {
      data.push({ date: new Date(d.date), flag, pct });
    }
  }
  const chart = Plot.plot({
    width: el.clientWidth || 900,
    height: 420,
    style: { background: "transparent", color: tok.text, fontSize: "11px", fontFamily: MONO_FONT_STACK },
    x: { label: null },
    y: { domain: [0, 100], grid: true, label: "%" },
    fy: { label: null },
    marks: [
      Plot.line(data, { x: "date", y: "pct", fy: "flag", stroke: tok.primary, strokeWidth: 1.5 }),
      Plot.tip(data, Plot.pointer({
        x: "date", y: "pct", fy: "flag",
        title: (d) => `${d.flag}\n${d.date.toISOString().slice(0, 10)} — ${d.pct}%`,
        fill: tok.surface, stroke: tok.border,
      })),
    ],
  });
  el.replaceChildren(chart);
}

async function loadServices() {
  try {
    servicesPayload = await fetchJSON("/api/services");
  } catch (e) {
    note("services-note", "services data unavailable: " + e.message);
    return;
  }
  if (!servicesPayload.latest) {
    note("services-note", "No snapshot available yet.");
    return;
  }
  const toggle = document.getElementById("services-toggle");
  toggle.hidden = false;
  toggle.addEventListener("click", () => {
    servicesByNetwork = !servicesByNetwork;
    toggle.textContent = servicesByNetwork ? "Totals" : "By network";
    renderServicesBars();
  });
  renderServicesBars();
  renderServicesHistory();
}

// --- Section 3: unique-node composition ------------------------------------

let uniquePayload = null;

function renderComposition() {
  const el = document.getElementById("chart-composition");
  const tok = themeTokens();
  const colors = networkColors();
  const c = uniquePayload.composition;
  const data = [
    { k: "1 network type", v: c.n1, color: colors.ipv4 },
    { k: "2 network types", v: c.n2, color: colors.tor },
    { k: "3+ network types", v: c.n3plus, color: colors.i2p },
  ].filter((d) => d.v > 0);
  const total = data.reduce((s, d) => s + d.v, 0) || 1;
  const chart = Plot.plot({
    width: el.clientWidth || 900,
    height: 90,
    style: { background: "transparent", color: tok.text, fontSize: "12px", fontFamily: MONO_FONT_STACK },
    x: { label: "reachable addresses", grid: true },
    color: { domain: data.map((d) => d.k), range: data.map((d) => d.color), legend: true },
    marks: [
      Plot.barX(data, { x: "v", fill: "k" }),
      Plot.tip(data, Plot.pointerX(Plot.stackX({
        x: "v",
        title: (d) => `${d.k}\n${fmt.format(d.v)} addresses (${(100 * d.v / total).toFixed(1)}%)`,
        fill: tok.surface, stroke: tok.border,
      }))),
    ],
  });
  el.replaceChildren(chart);
}

async function loadUnique() {
  try {
    uniquePayload = await fetchJSON("/api/unique-nodes");
  } catch (e) {
    document.getElementById("unique-method").textContent = "unique-nodes data unavailable: " + e.message;
    return;
  }
  document.getElementById("unique-method").textContent = uniquePayload.method;
  if (uniquePayload.estimate == null) {
    document.getElementById("unique-numbers").textContent =
      "No estimate computed yet — the collector produces it every 10 minutes.";
    return;
  }
  document.getElementById("unique-numbers").textContent =
    `${fmt.format(uniquePayload.reachable)} reachable addresses → ` +
    `≈${fmt.format(uniquePayload.estimate)} unique nodes ` +
    `(clearnet ${fmt.format(uniquePayload.clearnet)}, tor ${fmt.format(uniquePayload.tor)}, i2p ${fmt.format(uniquePayload.i2p)})`;
  renderComposition();
}

// --- Theme toggle (same behaviour as the overview page) --------------------

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "light"
    ? "light" : "dark";
}

function rerenderAll() {
  if (propAggregate?.blocks?.length) {
    propSelected ? selectBlock(propSelected) : showAggregate();
  }
  if (servicesPayload?.latest) {
    renderServicesBars();
    renderServicesHistory();
  }
  if (uniquePayload?.estimate != null) renderComposition();
}

function initTheme() {
  const btn = document.getElementById("theme-toggle");
  btn.textContent = currentTheme().toUpperCase();
  btn.addEventListener("click", () => {
    const next = currentTheme() === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("pesquisa:theme", next); } catch (e) { /* session-only */ }
    btn.textContent = next.toUpperCase();
    rerenderAll();
  });
}

initTheme();
// Independent, lazy sections.
loadPropagation();
loadServices();
loadUnique();
