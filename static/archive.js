const TIER_LABELS = {
  daily: "Daily — last 7 days",
  weekly: "Weekly — last of each ISO week",
  monthly: "Monthly — last of each month",
};

function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("pesquisa:theme", t); } catch (e) { /* private mode */ }
}

function initThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  const render = () => {
    btn.textContent = document.documentElement.getAttribute("data-theme") === "dark" ? "☀" : "☾";
  };
  btn.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    applyTheme(cur === "dark" ? "light" : "dark");
    render();
  });
  render();
}

function fmtSize(bytes) {
  if (bytes >= 1 << 20) return (bytes / (1 << 20)).toFixed(1) + " MB";
  if (bytes >= 1 << 10) return (bytes / (1 << 10)).toFixed(0) + " KB";
  return bytes + " B";
}

function renderTier(tier, entries) {
  const wrap = document.createElement("div");
  const h = document.createElement("h2");
  h.textContent = TIER_LABELS[tier] || tier;
  wrap.appendChild(h);

  const scroller = document.createElement("div");
  scroller.className = "table-wrap";
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const label of ["Date (UTC)", "Nodes", "CSV", "Parquet"]) {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const e of entries) {
    const tr = document.createElement("tr");
    for (const text of [e.date, String(e.total_nodes ?? "—")]) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    }
    for (const fmt of ["csv", "parquet"]) {
      const td = document.createElement("td");
      const f = e.formats[fmt];
      if (f) {
        const a = document.createElement("a");
        a.href = f.url;
        a.textContent = fmtSize(f.size);
        td.appendChild(a);
      } else {
        td.textContent = "—";
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  scroller.appendChild(table);
  wrap.appendChild(scroller);
  return wrap;
}

async function main() {
  initThemeToggle();
  const container = document.getElementById("archive-tiers");
  const empty = document.getElementById("archive-empty");
  let data;
  try {
    const res = await fetch("/api/v1/archives/");
    data = await res.json();
  } catch (e) {
    empty.hidden = false;
    return;
  }
  if (!data.results || data.results.length === 0) {
    empty.hidden = false;
    return;
  }
  for (const tier of ["daily", "weekly", "monthly"]) {
    const entries = data.results.filter((e) => e.tier === tier);
    if (entries.length) container.appendChild(renderTier(tier, entries));
  }
}

main();
