const fmt = new Intl.NumberFormat("en-US");
let map, markers, charts = {};
let currentNodes = [];

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function initMap() {
  map = L.map("map", { worldCopyJump: true }).setView([20, 0], 2);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: "© OpenStreetMap, © CARTO",
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(map);
  markers = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 50 });
  map.addLayer(markers);
}

function updateMap(nodes) {
  markers.clearLayers();
  const batch = [];
  for (const n of nodes) {
    if (n.latitude == null || n.longitude == null) continue;
    const m = L.circleMarker([n.latitude, n.longitude], {
      radius: 4, color: "#f7931a", weight: 1, fillOpacity: 0.6,
    }).bindPopup(
      `<b>${n.address}:${n.port}</b><br>${n.user_agent || ""}<br>${n.city || ""}, ${n.country || ""}<br>${n.asn || ""} ${n.asn_name || ""}<br>height: ${n.height}`
    );
    batch.push(m);
  }
  markers.addLayers(batch);
}

function makeBarChart(canvasId, labels, values, label) {
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(document.getElementById(canvasId), {
    type: "bar",
    data: { labels, datasets: [{ label, data: values, backgroundColor: "#f7931a" }] },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8b949e" }, grid: { color: "#2d333b" } },
        y: { ticks: { color: "#e6edf3" }, grid: { display: false } },
      },
    },
  });
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
  const [snap, stats] = await Promise.all([
    fetchJSON(`/api/snapshot/${ts}`),
    fetchJSON(`/api/snapshot/${ts}/stats`),
  ]);
  currentNodes = snap.nodes;
  document.getElementById("kpi-total").textContent = fmt.format(stats.total);
  document.getElementById("kpi-countries").textContent = fmt.format(stats.countries_total);
  document.getElementById("kpi-asns").textContent = fmt.format(stats.asns_total);
  document.getElementById("kpi-height").textContent = stats.median_height ?? "—";
  document.getElementById("snapshot-meta").textContent =
    new Date(ts * 1000).toISOString().replace("T", " ").slice(0, 19) + " UTC";

  makeBarChart("chart-countries",
    stats.top_countries.map(([k]) => k),
    stats.top_countries.map(([, v]) => v),
    "nodes");
  makeBarChart("chart-uas",
    stats.top_user_agents.map(([k]) => k.length > 32 ? k.slice(0, 30) + "…" : k),
    stats.top_user_agents.map(([, v]) => v),
    "nodes");
  makeBarChart("chart-asns",
    stats.top_asns.map(([k]) => k.length > 32 ? k.slice(0, 30) + "…" : k),
    stats.top_asns.map(([, v]) => v),
    "nodes");

  updateMap(currentNodes);
  updateTable(currentNodes);
  setTimeout(() => map.invalidateSize(), 50);
}

async function init() {
  initMap();
  const { timestamps } = await fetchJSON("/api/snapshots");
  const select = document.getElementById("snapshot-select");
  for (const ts of [...timestamps].reverse()) {
    const opt = document.createElement("option");
    opt.value = ts;
    opt.textContent = new Date(ts * 1000).toISOString().replace("T", " ").slice(0, 19);
    select.appendChild(opt);
  }
  select.addEventListener("change", e => loadSnapshot(parseInt(e.target.value)));
  document.getElementById("filter").addEventListener("input", applyFilter);

  if (timestamps.length) {
    select.value = timestamps[timestamps.length - 1];
    await loadSnapshot(timestamps[timestamps.length - 1]);
  }
}

init().catch(err => {
  console.error(err);
  document.getElementById("snapshot-meta").textContent = "error: " + err.message;
});
